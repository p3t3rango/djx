import asyncio
import os
import threading
from typing import List, Optional

from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.dependencies import get_db, get_sc
from api.tasks import create_task, get_task
from core.config import GENRES
from core.discovery_service import DiscoveryService
from core.download_service import DownloadService

router = APIRouter()


def _save_manifest(db):
    """Auto-save library manifest after downloads/analysis."""
    try:
        download_dir = db.get_setting("download_dir") or "downloads"
        db.export_library_manifest(download_dir)
    except Exception:
        pass  # non-critical


class DownloadRequest(BaseModel):
    track_ids: List[int]
    genre_folder: str
    analyze_after: bool = False


class BatchDownloadRequest(BaseModel):
    genre: str
    count: int = 50
    include_remixes: bool = False


class UrlDownloadRequest(BaseModel):
    url: str
    genre_folder: str = "downloads"
    analyze_after: bool = False


def _run_download(task, sc, db_path, track_ids, genre_folder, analyze_after=False):
    """Run download in a thread with its own DB connection."""
    from core.database import Database
    from core.models import Track
    task.status = "running"
    try:
        thread_db = Database(db_path)
        svc = DownloadService(sc, thread_db)
        tracks = []
        for tid in track_ids:
            row = thread_db.get_track(tid)
            if row:
                tracks.append(Track.from_db_row(row))

        task.message = f"Downloading {len(tracks)} tracks..."
        report = svc.download_tracks(tracks, genre_folder)
        task.result = report.model_dump()

        if analyze_after and report.downloaded > 0:
            from core.analysis_service import AnalysisService
            task.message = "Analyzing downloaded tracks..."
            analysis_svc = AnalysisService(thread_db)
            pairs = []
            for r in report.results:
                if r.status == "downloaded" and r.file_path:
                    pairs.append((r.track_id, r.file_path))
            if pairs:
                result = analysis_svc.analyze_batch(
                    pairs,
                    on_progress=lambda i, total, fp: setattr(
                        task, 'message', f"Analyzing {i+1}/{total}: {fp.split('/')[-1][:40]}"
                    ),
                )
                task.result["analysis"] = result

        task.status = "completed"
        _save_manifest(thread_db)
        thread_db.close()
    except Exception as e:
        task.error = str(e)
        task.status = "failed"


def _run_batch(task, sc, db_path, genre, count, include_remixes):
    """Run batch discover+download in a thread with its own DB connection."""
    from core.database import Database
    task.status = "running"
    try:
        thread_db = Database(db_path)
        disc = DiscoveryService(sc, thread_db)
        dl = DownloadService(sc, thread_db)

        task.message = f"Discovering {GENRES[genre]['display_name']} tracks..."
        tracks = disc.discover_genre(genre, count)

        task.message = f"Downloading {len(tracks)} tracks..."
        report = dl.download_tracks(tracks, GENRES[genre]["folder"])
        result = {"report": report.model_dump(), "tracks_found": len(tracks)}

        if include_remixes:
            task.message = "Discovering remixes..."
            remix_tracks = disc.discover_remixes(genre, count)
            task.message = f"Downloading {len(remix_tracks)} remixes..."
            remix_report = dl.download_tracks(remix_tracks, f"{GENRES[genre]['folder']}-remixes")
            result["remix_report"] = remix_report.model_dump()
            result["remix_tracks_found"] = len(remix_tracks)

        task.result = result
        task.status = "completed"
        _save_manifest(thread_db)
        thread_db.close()
    except Exception as e:
        task.error = str(e)
        task.status = "failed"



@router.post("/")
def download_tracks(req: DownloadRequest, db=Depends(get_db), sc=Depends(get_sc)):
    task = create_task()
    t = threading.Thread(
        target=_run_download,
        args=(task, sc, db.db_path, req.track_ids, req.genre_folder, req.analyze_after),
        daemon=True
    )
    t.start()
    return {"task_id": task.id}


@router.post("/batch")
def batch_download(req: BatchDownloadRequest, db=Depends(get_db), sc=Depends(get_sc)):
    if req.genre not in GENRES:
        return {"error": f"Unknown genre: {req.genre}"}

    task = create_task()
    t = threading.Thread(
        target=_run_batch,
        args=(task, sc, db.db_path, req.genre, req.count, req.include_remixes),
        daemon=True
    )
    t.start()
    return {"task_id": task.id}


@router.post("/resolve-url")
def resolve_url(req: UrlDownloadRequest, sc=Depends(get_sc)):
    """Resolve a SoundCloud URL to track info without downloading."""
    from core.models import Track
    from core.trending import compute_trending_score
    try:
        sc_track = sc.resolve(req.url)
        if not sc_track or not hasattr(sc_track, 'id'):
            return {"error": "Could not resolve URL"}
        t = Track.from_sc_track(sc_track)
        if not t:
            return {"error": "Could not parse track"}
        t.trending_score = compute_trending_score(t)

        # Detect genre folder from track's genre field
        genre = (t.genre or '').lower().strip()
        suggested_folder = 'downloads'
        genre_map = {
            'house': 'house', 'deep house': 'house', 'tech house': 'tech-house',
            'techhouse': 'tech-house', 'afro house': 'afro-house', 'afrohouse': 'afro-house',
            'amapiano': 'amapiano', 'uk garage': 'uk-garage', 'ukgarage': 'uk-garage',
            'techno': 'techno', 'hard techno': 'techno', 'minimal': 'minimal',
            'disco': 'disco-funk', 'funk': 'disco-funk', 'drum & bass': 'drum-and-bass',
            'dubstep': 'dubstep-bass', 'bass': 'dubstep-bass', 'trance': 'trance',
            'dancehall': 'dancehall-reggaeton', 'reggaeton': 'dancehall-reggaeton',
            'hip-hop & rap': 'hip-hop', 'hip hop': 'hip-hop', 'r&b': 'hip-hop',
            'electronic': 'electronic', 'dance & edm': 'house', 'dance': 'house',
        }
        for key, folder in genre_map.items():
            if key in genre:
                suggested_folder = folder
                break

        return {
            "track_id": t.track_id,
            "title": t.title,
            "artist": t.artist,
            "genre": t.genre,
            "suggested_folder": suggested_folder,
            "playback_count": t.playback_count,
            "duration_seconds": t.duration_seconds,
            "permalink_url": t.permalink_url,
            "trending_score": t.trending_score,
        }
    except Exception as e:
        return {"error": str(e)}


def _run_url_download(task, sc, db_path, url, genre_folder, analyze_after):
    """Resolve a SoundCloud URL and download the track."""
    from core.database import Database
    from core.models import Track
    from core.download_service import DownloadService
    from core.trending import compute_trending_score

    task.status = "running"
    task.message = "Resolving URL..."
    try:
        thread_db = Database(db_path)

        sc_track = sc.resolve(url)
        if not sc_track or not hasattr(sc_track, 'id'):
            task.error = "Could not resolve URL to a track"
            task.status = "failed"
            thread_db.close()
            return

        t = Track.from_sc_track(sc_track, source="url_download")
        if not t:
            task.error = "Could not parse track data"
            task.status = "failed"
            thread_db.close()
            return

        t.trending_score = compute_trending_score(t)
        thread_db.upsert_track(t.to_db_dict())

        task.message = f"Downloading: {t.artist} - {t.title}"
        svc = DownloadService(sc, thread_db)
        report = svc.download_tracks([t], genre_folder)

        # Analyze after download if requested
        if analyze_after and report.downloaded > 0:
            task.message = f"Analyzing: {t.artist} - {t.title}"
            from core.analysis_service import AnalysisService
            asvc = AnalysisService(thread_db)
            # Find the file path
            row = thread_db.conn.execute(
                "SELECT file_path FROM downloads WHERE track_id = ? AND file_path IS NOT NULL",
                (t.track_id,)
            ).fetchone()
            if row and row["file_path"]:
                import os
                if os.path.exists(row["file_path"]):
                    asvc.analyze_and_store(t.track_id, row["file_path"])

        task.result = {
            "title": t.title,
            "artist": t.artist,
            "track_id": t.track_id,
            "downloaded": report.downloaded,
            "skipped": report.skipped,
            "failed": report.failed,
        }
        task.message = f"{'Downloaded' if report.downloaded else 'Skipped (already exists)' if report.skipped else 'Failed'}: {t.artist} - {t.title}"
        if analyze_after and report.downloaded > 0:
            task.message += " (analyzed)"
        task.status = "completed"
        thread_db.close()
    except Exception as e:
        task.error = str(e)
        task.status = "failed"


@router.post("/url")
def download_from_url(req: UrlDownloadRequest, db=Depends(get_db), sc=Depends(get_sc)):
    """Download a track from a SoundCloud URL."""
    task = create_task()
    t = threading.Thread(
        target=_run_url_download,
        args=(task, sc, db.db_path, req.url, req.genre_folder, req.analyze_after),
        daemon=True
    )
    t.start()
    return {"task_id": task.id}


def _run_backfill(task, sc, db_path):
    """Background backfill — won't block the server."""
    from core.database import Database
    from core.models import Track
    from core.trending import compute_trending_score
    import time

    task.status = "running"
    try:
        thread_db = Database(db_path)
        rows = thread_db.conn.execute("SELECT track_id FROM tracks WHERE title = '' OR title IS NULL").fetchall()
        track_ids = [r['track_id'] for r in rows]
        task.message = f"Enriching {len(track_ids)} tracks..."

        success = 0
        failed = 0
        for i, tid in enumerate(track_ids):
            if i % 20 == 0:
                task.message = f"Enriching... {i}/{len(track_ids)}"
            try:
                sc_track = sc.get_track(tid)
                if sc_track:
                    t = Track.from_sc_track(sc_track, source="backfill")
                    if t:
                        t.trending_score = compute_trending_score(t)
                        thread_db.upsert_track(t.to_db_dict())
                        success += 1
                        continue
            except Exception:
                pass
            failed += 1
            time.sleep(0.15)

        task.result = {"success": success, "failed": failed, "total": len(track_ids)}
        task.message = f"Done: {success} enriched, {failed} failed"
        task.status = "completed"
        thread_db.close()
    except Exception as e:
        task.error = str(e)
        task.status = "failed"


@router.post("/backfill")
def backfill_metadata(db=Depends(get_db), sc=Depends(get_sc)):
    task = create_task()
    t = threading.Thread(target=_run_backfill, args=(task, sc, db.db_path), daemon=True)
    t.start()
    return {"task_id": task.id}


@router.get("/status/{task_id}")
def download_status(task_id: str):
    task = get_task(task_id)
    if not task:
        return {"error": "Task not found"}
    return {
        "id": task.id, "status": task.status, "progress": task.progress,
        "message": task.message, "result": task.result, "error": task.error,
    }


@router.get("/")
def list_downloads(genre: Optional[str] = None, status: Optional[str] = None,
                   limit: int = 100, offset: int = 0, db=Depends(get_db)):
    return db.get_downloads(genre=genre, status=status, limit=limit, offset=offset)


@router.get("/stats")
def download_stats(db=Depends(get_db)):
    return db.get_download_stats()


@router.get("/file/{download_id}")
def serve_file(download_id: int, db=Depends(get_db)):
    row = db.conn.execute("SELECT file_path FROM downloads WHERE id = ?", (download_id,)).fetchone()
    if not row or not row["file_path"] or not os.path.exists(row["file_path"]):
        return {"error": "File not found"}
    return FileResponse(row["file_path"], media_type="audio/mpeg")


@router.get("/play/{track_id}")
def play_library_file(track_id: int, db=Depends(get_db)):
    """Stream a file from the library by track_id."""
    row = db.conn.execute(
        "SELECT file_path FROM downloads WHERE track_id = ? AND file_path IS NOT NULL LIMIT 1",
        (track_id,)
    ).fetchone()
    if not row or not os.path.exists(row["file_path"]):
        return {"error": "File not found"}
    return FileResponse(row["file_path"], media_type="audio/mpeg")


class EditMetadataRequest(BaseModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    genre: Optional[str] = None


@router.put("/metadata/{track_id}")
def edit_metadata(track_id: int, req: EditMetadataRequest, db=Depends(get_db)):
    """Edit track metadata in DB and ID3 tags."""
    updates = []
    params = []
    if req.title is not None:
        updates.append("title = ?")
        params.append(req.title)
    if req.artist is not None:
        updates.append("artist = ?")
        params.append(req.artist)
    if req.genre is not None:
        updates.append("genre = ?")
        params.append(req.genre)

    if not updates:
        return {"error": "No fields to update"}

    params.append(track_id)
    db.conn.execute(f"UPDATE tracks SET {', '.join(updates)} WHERE track_id = ?", params)
    db.conn.commit()

    # Also update ID3 tags on the file
    row = db.conn.execute(
        "SELECT file_path FROM downloads WHERE track_id = ? AND file_path IS NOT NULL LIMIT 1",
        (track_id,)
    ).fetchone()
    if row and row["file_path"] and os.path.exists(row["file_path"]):
        try:
            from mutagen.id3 import ID3, TIT2, TPE1, TCON, ID3NoHeaderError
            try:
                tags = ID3(row["file_path"])
            except ID3NoHeaderError:
                tags = ID3()
            if req.title is not None:
                tags.add(TIT2(encoding=3, text=[req.title]))
            if req.artist is not None:
                tags.add(TPE1(encoding=3, text=[req.artist]))
            if req.genre is not None:
                tags.add(TCON(encoding=3, text=[req.genre]))
            tags.save(row["file_path"])
        except Exception:
            pass

    return {"updated": True}


class CreatePlaylistRequest(BaseModel):
    name: str
    track_ids: List[int]
    export_folder: Optional[str] = None


@router.post("/playlists")
def create_playlist(req: CreatePlaylistRequest, db=Depends(get_db)):
    """Create a playlist. Optionally export/copy tracks to a folder."""
    import shutil
    from core.utils import ensure_directory, sanitize_filename

    # Store playlist in DB
    db.conn.execute("""
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            track_ids_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    import json
    db.conn.execute(
        "INSERT INTO playlists (name, track_ids_json) VALUES (?, ?)",
        (req.name, json.dumps(req.track_ids))
    )
    db.conn.commit()

    # Export to folder if requested
    copied = 0
    if req.export_folder:
        folder = os.path.expanduser(req.export_folder)
        ensure_directory(folder)
        for tid in req.track_ids:
            row = db.conn.execute(
                "SELECT d.file_path, t.artist, t.title FROM downloads d JOIN tracks t ON d.track_id = t.track_id WHERE d.track_id = ? AND d.file_path IS NOT NULL",
                (tid,)
            ).fetchone()
            if row and row["file_path"] and os.path.exists(row["file_path"]):
                ext = os.path.splitext(row["file_path"])[1]
                dest_name = sanitize_filename(f"{row['artist']} - {row['title']}") + ext
                dest = os.path.join(folder, dest_name)
                if not os.path.exists(dest):
                    shutil.copy2(row["file_path"], dest)
                    copied += 1

    return {"created": True, "name": req.name, "tracks": len(req.track_ids), "copied": copied}


@router.get("/playlists")
def list_playlists(db=Depends(get_db)):
    db.conn.execute("""
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            track_ids_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    import json
    rows = db.conn.execute("SELECT * FROM playlists ORDER BY created_at DESC").fetchall()
    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "name": r["name"],
            "track_ids": json.loads(r["track_ids_json"]),
            "track_count": len(json.loads(r["track_ids_json"])),
            "created_at": r["created_at"],
        })
    return result


class UpdatePlaylistRequest(BaseModel):
    name: Optional[str] = None
    track_ids: Optional[List[int]] = None


@router.put("/playlists/{playlist_id}")
def update_playlist(playlist_id: int, req: UpdatePlaylistRequest, db=Depends(get_db)):
    import json
    if req.name:
        db.conn.execute("UPDATE playlists SET name = ? WHERE id = ?", (req.name, playlist_id))
    if req.track_ids is not None:
        db.conn.execute("UPDATE playlists SET track_ids_json = ? WHERE id = ?", (json.dumps(req.track_ids), playlist_id))
    db.conn.commit()
    return {"updated": True}


@router.delete("/playlists/{playlist_id}")
def delete_playlist(playlist_id: int, db=Depends(get_db)):
    db.conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
    db.conn.commit()
    return {"deleted": True}


@router.delete("/{download_id}")
def delete_download(download_id: int, db=Depends(get_db)):
    file_path = db.delete_download(download_id)
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
    return {"deleted": True}


# --- Tags ---

class CreateTagRequest(BaseModel):
    name: str
    color: str = '#00ffc8'


class TagTrackRequest(BaseModel):
    track_id: int
    tag_id: int


@router.get("/tags")
def list_tags(db=Depends(get_db)):
    return db.get_tags()


@router.post("/tags")
def create_tag(req: CreateTagRequest, db=Depends(get_db)):
    tag_id = db.create_tag(req.name, req.color)
    return {"id": tag_id, "name": req.name}


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: int, db=Depends(get_db)):
    db.delete_tag(tag_id)
    return {"deleted": True}


@router.post("/tags/assign")
def tag_track(req: TagTrackRequest, db=Depends(get_db)):
    db.tag_track(req.track_id, req.tag_id)
    return {"tagged": True}


@router.post("/tags/remove")
def untag_track(req: TagTrackRequest, db=Depends(get_db)):
    db.untag_track(req.track_id, req.tag_id)
    return {"untagged": True}


@router.get("/tags/track/{track_id}")
def get_track_tags(track_id: int, db=Depends(get_db)):
    return db.get_track_tags(track_id)
