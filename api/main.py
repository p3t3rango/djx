import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.database import Database
from api.dependencies import get_sc
from api.routers import discovery, downloads, search, accounts, settings, analysis


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state._sc = None  # Lazy init via get_sc dependency
    # Migrate legacy manifests on startup
    startup_db = Database("sc_discover.db")
    startup_db.migrate_manifests(
        startup_db.get_setting("download_dir") or "downloads"
    )
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
def stream_track(track_id: int, sc=Depends(get_sc)):
    """Get a streamable URL for a SoundCloud track."""
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
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend_dist = os.path.join(_project_root, "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
