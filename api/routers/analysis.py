import threading
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import get_db
from api.tasks import create_task, get_task

router = APIRouter()


class AnalyzeRequest(BaseModel):
    track_ids: Optional[List[int]] = None
    genre_folder: Optional[str] = None
    all_unanalyzed: bool = False


def _run_analysis(task, db_path, track_ids=None, genre_folder=None, all_unanalyzed=False):
    from core.database import Database
    from core.analysis_service import AnalysisService

    task.status = "running"
    try:
        thread_db = Database(db_path)
        svc = AnalysisService(thread_db)

        # Determine which tracks to analyze
        if all_unanalyzed:
            items = svc.get_unanalyzed_tracks()
            pairs = [(r["track_id"], r["file_path"]) for r in items]
        elif track_ids:
            pairs = []
            for tid in track_ids:
                row = thread_db.conn.execute(
                    "SELECT d.file_path FROM downloads d WHERE d.track_id = ? AND d.file_path IS NOT NULL LIMIT 1",
                    (tid,)
                ).fetchone()
                if row:
                    pairs.append((tid, row["file_path"]))
        elif genre_folder:
            rows = thread_db.conn.execute("""
                SELECT t.track_id, d.file_path FROM tracks t
                JOIN downloads d ON t.track_id = d.track_id
                WHERE d.genre_folder = ? AND d.file_path IS NOT NULL AND t.bpm IS NULL
            """, (genre_folder,)).fetchall()
            pairs = [(r["track_id"], r["file_path"]) for r in rows]
        else:
            pairs = []

        task.message = f"Analyzing {len(pairs)} tracks..."

        result = svc.analyze_batch(
            pairs,
            on_progress=lambda i, total, fp: setattr(
                task, 'message', f"Analyzing {i+1}/{total}: {fp.split('/')[-1][:40]}"
            ),
        )
        task.result = result
        task.status = "completed"
        task.message = f"Done: {result['success']} analyzed, {result['failed']} failed"
        thread_db.close()
    except Exception as e:
        task.error = str(e)
        task.status = "failed"


@router.post("/analyze")
def analyze_tracks(req: AnalyzeRequest, db=Depends(get_db)):
    task = create_task()
    t = threading.Thread(
        target=_run_analysis,
        args=(task, db.db_path, req.track_ids, req.genre_folder, req.all_unanalyzed),
        daemon=True
    )
    t.start()
    return {"task_id": task.id}


@router.get("/status/{task_id}")
def analysis_status(task_id: str):
    task = get_task(task_id)
    if not task:
        return {"error": "Task not found"}
    return {
        "id": task.id, "status": task.status, "message": task.message,
        "result": task.result, "error": task.error,
    }


@router.get("/stats")
def analysis_stats(db=Depends(get_db)):
    from core.analysis_service import AnalysisService
    svc = AnalysisService(db)
    return svc.get_analysis_stats()


@router.get("/tracks")
def analyzed_tracks(analyzed: Optional[bool] = None, limit: int = 100, offset: int = 0,
                    db=Depends(get_db)):
    """Get tracks with analysis data."""
    if analyzed is True:
        query = """
            SELECT t.*, d.file_path, d.genre_folder, d.file_size_bytes FROM tracks t
            JOIN downloads d ON t.track_id = d.track_id
            WHERE t.bpm IS NOT NULL AND d.status = 'completed'
            ORDER BY t.analyzed_at DESC LIMIT ? OFFSET ?
        """
    elif analyzed is False:
        query = """
            SELECT t.*, d.file_path, d.genre_folder, d.file_size_bytes FROM tracks t
            JOIN downloads d ON t.track_id = d.track_id
            WHERE t.bpm IS NULL AND d.file_path IS NOT NULL AND d.status = 'completed'
            ORDER BY t.title LIMIT ? OFFSET ?
        """
    else:
        query = """
            SELECT t.*, d.file_path, d.genre_folder, d.file_size_bytes FROM tracks t
            JOIN downloads d ON t.track_id = d.track_id
            WHERE d.file_path IS NOT NULL AND d.status = 'completed'
            ORDER BY t.bpm IS NULL, t.analyzed_at DESC LIMIT ? OFFSET ?
        """
    rows = db.conn.execute(query, (limit, offset)).fetchall()
    return [dict(r) for r in rows]


class ExportRequest(BaseModel):
    track_ids: Optional[List[int]] = None
    playlist_name: Optional[str] = None


@router.post("/export-rekordbox")
def export_rekordbox(req: ExportRequest, db=Depends(get_db)):
    """Export analyzed tracks to Rekordbox XML."""
    from core.rekordbox_service import RekordboxService
    svc = RekordboxService(db)

    if req.playlist_name and req.track_ids:
        return svc.create_playlist_xml(req.playlist_name, req.track_ids)
    else:
        return svc.export_to_rekordbox_xml(req.track_ids)


class USBExportRequest(BaseModel):
    target_path: str
    track_ids: Optional[List[int]] = None
    playlist_name: Optional[str] = None


def _run_usb_export(task, db_path, target_path, track_ids, playlist_name):
    from core.database import Database
    from core.usb_export import USBExporter
    task.status = "running"
    try:
        thread_db = Database(db_path)
        exporter = USBExporter(thread_db, target_path)
        result = exporter.export(
            track_ids=track_ids,
            playlist_name=playlist_name,
            on_progress=lambda msg: setattr(task, 'message', msg),
        )
        task.result = result
        task.message = f"Exported {result.get('exported', 0)} tracks to {target_path}"
        task.status = "completed"
        thread_db.close()
    except Exception as e:
        task.error = str(e)
        task.status = "failed"


@router.post("/export-usb")
def export_usb(req: USBExportRequest, db=Depends(get_db)):
    """Export tracks to CDJ-ready USB drive (Pioneer .pdb format)."""
    task = create_task()
    t = threading.Thread(
        target=_run_usb_export,
        args=(task, db.db_path, req.target_path, req.track_ids, req.playlist_name),
        daemon=True
    )
    t.start()
    return {"task_id": task.id}


# --- Cue Points ---

class CuePoint(BaseModel):
    name: str = ""
    type: str = "cue"  # "cue" or "loop"
    start: float = 0.0
    end: Optional[float] = None
    num: int = 0  # hot cue number (0-7)
    color: Optional[str] = None


class SetCuesRequest(BaseModel):
    track_id: int
    cues: List[CuePoint]


@router.post("/cues")
def set_cues(req: SetCuesRequest, db=Depends(get_db)):
    """Set hot cues / memory cues / loops for a track."""
    import json
    cues_data = [c.dict() for c in req.cues]
    db.conn.execute(
        "UPDATE tracks SET cues_json = ? WHERE track_id = ?",
        (json.dumps(cues_data), req.track_id)
    )
    db.conn.commit()
    return {"saved": len(cues_data)}


@router.get("/cues/{track_id}")
def get_cues(track_id: int, db=Depends(get_db)):
    """Get cue points for a track."""
    import json
    row = db.conn.execute("SELECT cues_json FROM tracks WHERE track_id = ?", (track_id,)).fetchone()
    if row and row["cues_json"]:
        return json.loads(row["cues_json"])
    return []


# --- File Upload / Import ---

@router.post("/import")
async def import_files(db=Depends(get_db)):
    """Import audio files from a local folder path."""
    # This is triggered from the UI with a folder path
    # The actual file scanning happens server-side
    return {"error": "Use /import-folder with a folder path"}


class ImportFolderRequest(BaseModel):
    folder_path: str
    genre_folder: str = "imported"


@router.post("/import-folder")
def import_folder(req: ImportFolderRequest, db=Depends(get_db)):
    """Scan a folder for audio files and add them to the library."""
    import os
    import hashlib
    from core.utils import ensure_directory

    folder = os.path.expanduser(req.folder_path)
    if not os.path.isdir(folder):
        return {"error": f"Folder not found: {folder}"}

    download_dir = db.get_setting("download_dir") or "downloads"
    target_dir = os.path.join(download_dir, req.genre_folder)
    ensure_directory(target_dir)

    imported = 0
    skipped = 0
    for f in os.listdir(folder):
        if not f.lower().endswith(('.mp3', '.m4a', '.wav', '.flac', '.aac', '.ogg')):
            continue

        src = os.path.join(folder, f)
        # Parse artist - title from filename
        name = f.rsplit('.', 1)[0]
        parts = name.split(' - ', 1)
        artist = parts[0].strip() if len(parts) > 1 else ""
        title = parts[1].strip() if len(parts) > 1 else name.strip()

        # Generate a fake track_id from filename hash (negative to avoid SC ID collision)
        track_id = -abs(int(hashlib.md5(f.encode()).hexdigest()[:8], 16))

        # Check if already imported
        existing = db.conn.execute("SELECT 1 FROM tracks WHERE track_id = ?", (track_id,)).fetchone()
        if existing:
            skipped += 1
            continue

        # Copy file to library
        import shutil
        dest = os.path.join(target_dir, f)
        if not os.path.exists(dest):
            shutil.copy2(src, dest)

        file_size = os.path.getsize(dest)

        # Read ID3 tags if available
        try:
            from mutagen.id3 import ID3
            tags = ID3(dest)
            if not title and tags.get("TIT2"):
                title = str(tags["TIT2"])
            if not artist and tags.get("TPE1"):
                artist = str(tags["TPE1"])
        except Exception:
            pass

        # Insert into DB
        db.conn.execute("""
            INSERT OR IGNORE INTO tracks (track_id, title, artist, permalink_url, genre, discovery_source)
            VALUES (?, ?, ?, '', ?, 'imported')
        """, (track_id, title or f, artist or "", req.genre_folder))

        db.conn.execute("""
            INSERT OR IGNORE INTO downloads (track_id, genre_folder, file_path, file_size_bytes, status, download_method)
            VALUES (?, ?, ?, ?, 'completed', 'imported')
        """, (track_id, req.genre_folder, dest, file_size))

        imported += 1

    db.conn.commit()
    return {"imported": imported, "skipped": skipped}


# --- Waveform ---

@router.get("/waveform/{track_id}")
def get_waveform(track_id: int, db=Depends(get_db)):
    """Generate waveform data for a track."""
    row = db.conn.execute(
        "SELECT d.file_path FROM downloads d WHERE d.track_id = ? AND d.file_path IS NOT NULL LIMIT 1",
        (track_id,)
    ).fetchone()
    if not row or not row["file_path"]:
        return {"error": "File not found"}

    import os
    if not os.path.exists(row["file_path"]):
        return {"error": "File not found on disk"}

    from core.waveform_service import generate_waveform
    return generate_waveform(row["file_path"])


# --- Beat Grid ---

class BeatGridRequest(BaseModel):
    track_id: int
    beats: List[float]  # beat positions in seconds
    bpm: Optional[float] = None


@router.post("/beatgrid")
def set_beatgrid(req: BeatGridRequest, db=Depends(get_db)):
    """Save corrected beat grid."""
    import json
    updates = {"beats_json": json.dumps(req.beats)}
    if req.bpm:
        updates["bpm"] = req.bpm

    for key, val in updates.items():
        db.conn.execute(f"UPDATE tracks SET {key} = ? WHERE track_id = ?", (val, req.track_id))
    db.conn.commit()
    return {"saved": True, "beats": len(req.beats)}


@router.get("/beatgrid/{track_id}")
def get_beatgrid(track_id: int, db=Depends(get_db)):
    """Get beat grid for a track."""
    import json
    row = db.conn.execute(
        "SELECT beats_json, bpm FROM tracks WHERE track_id = ?", (track_id,)
    ).fetchone()
    if not row:
        return {"beats": [], "bpm": None}
    beats = json.loads(row["beats_json"]) if row["beats_json"] else []
    return {"beats": beats, "bpm": row["bpm"]}
