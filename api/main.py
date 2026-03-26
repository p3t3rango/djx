import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from core.database import Database
from api.dependencies import get_db, get_sc
from api.routers import discovery, downloads, search, accounts, settings, analysis

logger = logging.getLogger("djx")


def _safe_error(msg: str = "An error occurred") -> dict:
    """Return a generic error message to the client."""
    return {"error": msg}


def _validate_file_in_downloads(file_path: str, db) -> bool:
    """Validate that a file path is within the configured download directory."""
    download_dir = db.get_setting("download_dir") or "downloads"
    abs_download = os.path.abspath(download_dir)
    abs_file = os.path.abspath(file_path)
    return abs_file.startswith(abs_download + os.sep) or abs_file.startswith(abs_download)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state._sc = None
    db_path = os.environ.get("DJX_DB_PATH", "sc_discover.db")
    download_dir = os.environ.get("DJX_DOWNLOAD_DIR", "downloads")
    startup_db = Database(db_path)
    startup_db.migrate_manifests(
        startup_db.get_setting("download_dir") or download_dir
    )
    # Set default download dir if not set
    if not startup_db.get_setting("download_dir"):
        startup_db.set_setting("download_dir", download_dir)
    startup_db.close()
    yield


app = FastAPI(title="DJX", version="1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SecurityHeadersMiddleware)

app.include_router(discovery.router, prefix="/api/discovery", tags=["discovery"])
app.include_router(downloads.router, prefix="/api/downloads", tags=["downloads"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/pick-folder")
def pick_folder():
    """Open native macOS folder picker dialog."""
    import subprocess
    try:
        result = subprocess.run(
            ["osascript", "-e", 'POSIX path of (choose folder with prompt "Select export folder")'],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return {"path": result.stdout.strip()}
        return {"path": None, "cancelled": True}
    except subprocess.TimeoutExpired:
        return {"path": None, "cancelled": True}
    except Exception as e:
        logger.exception("pick-folder error")
        return _safe_error("Failed to open folder picker")


@app.get("/api/stream/{track_id}")
def stream_track(track_id: int, db=Depends(get_db), sc=Depends(get_sc)):
    """Stream a track — prefer local file, fall back to SoundCloud."""
    # Priority 0: Local file on disk (already downloaded)
    row = db.conn.execute(
        "SELECT file_path FROM downloads WHERE track_id = ? AND file_path IS NOT NULL LIMIT 1",
        (track_id,)
    ).fetchone()
    if row and row["file_path"] and os.path.exists(row["file_path"]):
        if not _validate_file_in_downloads(row["file_path"], db):
            return _safe_error("Invalid file path")
        return FileResponse(row["file_path"], media_type="audio/mpeg")

    import requests as req
    try:
        track = sc.get_track(track_id)
        if not track or not hasattr(track, "media") or not track.media:
            return {"error": "Track not found"}

        transcodings = track.media.transcodings or []

        # Priority 1: Progressive MP3 (direct play in browser)
        for t in transcodings:
            if not t.url or not t.format:
                continue
            protocol = getattr(t.format, "protocol", "")
            mime = getattr(t.format, "mime_type", "")
            if protocol == "progressive" and "mpeg" in mime:
                sep = "&" if "?" in t.url else "?"
                resp = req.get(f"{t.url}{sep}client_id={sc.client_id}", timeout=10)
                if resp.status_code == 200:
                    url = resp.json().get("url")
                    if url:
                        return {"url": url, "type": "mp3"}

        # Priority 2: HLS MP3 stream (browser can sometimes play the m3u8)
        for t in transcodings:
            if not t.url or not t.format:
                continue
            mime = getattr(t.format, "mime_type", "")
            if "mpeg" in mime:
                sep = "&" if "?" in t.url else "?"
                resp = req.get(f"{t.url}{sep}client_id={sc.client_id}", timeout=10)
                if resp.status_code == 200:
                    url = resp.json().get("url")
                    if url:
                        return {"url": url, "type": "hls"}

        # Priority 3: Any transcoding
        for t in transcodings:
            if not t.url:
                continue
            sep = "&" if "?" in t.url else "?"
            resp = req.get(f"{t.url}{sep}client_id={sc.client_id}", timeout=10)
            if resp.status_code == 200:
                url = resp.json().get("url")
                if url:
                    return {"url": url, "type": "hls"}

        # Priority 4: Return SoundCloud permalink for iframe embed
        permalink = getattr(track, "permalink_url", "")
        if permalink:
            return {"permalink": permalink, "type": "embed"}

        return {"error": "No streamable URL found"}
    except Exception as e:
        logger.exception("stream error for track %s", track_id)
        return _safe_error("Failed to stream track")


# Serve React frontend — check env var first (Electron), then default path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend_dist = os.environ.get("DJX_FRONTEND_DIR", os.path.join(_project_root, "frontend", "dist"))
if os.path.isdir(frontend_dist):
    # Serve static assets (JS, CSS, images) directly
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        """Serve index.html for all non-API routes (SPA catch-all)."""
        # Try to serve the exact file first (favicon, etc.)
        file_path = os.path.join(frontend_dist, path)
        if path and os.path.isfile(file_path):
            return FileResponse(file_path)
        # Otherwise serve index.html for client-side routing
        return FileResponse(os.path.join(frontend_dist, "index.html"))
