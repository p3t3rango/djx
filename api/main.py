import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.database import Database
from api.dependencies import get_db, get_sc
from api.routers import discovery, downloads, search, accounts, settings, analysis


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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        return {"error": str(e)}


@app.get("/api/stream/{track_id}")
def stream_track(track_id: int, db=Depends(get_db), sc=Depends(get_sc)):
    """Stream a track — prefer local file, fall back to SoundCloud."""
    # Priority 0: Local file on disk (already downloaded)
    row = db.conn.execute(
        "SELECT file_path FROM downloads WHERE track_id = ? AND file_path IS NOT NULL LIMIT 1",
        (track_id,)
    ).fetchone()
    if row and row["file_path"] and os.path.exists(row["file_path"]):
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
        return {"error": str(e)}


# Serve React frontend if built
# Serve React frontend — check env var first (Electron), then default path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend_dist = os.environ.get("DJX_FRONTEND_DIR", os.path.join(_project_root, "frontend", "dist"))
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
