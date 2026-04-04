import threading
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import get_db, get_sc
from api.tasks import create_task, get_task
from core.config import GENRES

router = APIRouter()


class DiscoverRequest(BaseModel):
    genre: str
    count: int = 50
    include_remixes: bool = False
    include_curated: bool = True
    sort: str = "trending"  # trending, popular, fresh
    analyze_on_discover: bool = False


class RelatedRequest(BaseModel):
    track_id: int
    limit: int = 50


def _run_discover(task, sc, db_path, genre, count, include_remixes, include_curated, sort, analyze_on_discover=False):
    from core.database import Database
    from core.discovery_service import DiscoveryService
    task.status = "running"
    try:
        thread_db = Database(db_path)
        svc = DiscoveryService(sc, thread_db)
        tracks = svc.discover_genre(
            genre, count, include_curated, sort=sort,
            on_progress=lambda msg: setattr(task, 'message', msg)
        )
        # Enrich with existing DB analysis data (BPM, key, energy, quality)
        def enrich(track_list):
            enriched = []
            for t in track_list:
                d = t.model_dump()
                row = thread_db.conn.execute("""
                    SELECT t.bpm, t.musical_key, t.camelot_key, t.energy,
                           dl.bitrate, dl.audio_format, dl.file_path
                    FROM tracks t
                    LEFT JOIN downloads dl ON t.track_id = dl.track_id
                    WHERE t.track_id = ?
                """, (t.track_id,)).fetchone()
                if row:
                    d["bpm"] = row["bpm"]
                    d["musical_key"] = row["musical_key"]
                    d["camelot_key"] = row["camelot_key"]
                    d["energy"] = row["energy"]
                    d["bitrate"] = row["bitrate"]
                    d["audio_format"] = row["audio_format"]
                    d["downloaded"] = row["file_path"] is not None
                enriched.append(d)
            return enriched

        # Analyze on discover: stream preview + quick BPM/key/energy detection
        if analyze_on_discover:
            import tempfile, os, requests as req
            from core.analysis_service import analyze_track

            for i, t in enumerate(tracks):
                # Skip if already analyzed in DB
                row = thread_db.conn.execute(
                    "SELECT bpm FROM tracks WHERE track_id = ? AND bpm IS NOT NULL", (t.track_id,)
                ).fetchone()
                if row:
                    continue

                task.message = f"Analyzing {i+1}/{len(tracks)}: {t.title[:30]}..."

                # Get stream URL
                try:
                    sc_track = sc.get_track(t.track_id)
                    if not sc_track or not hasattr(sc_track, 'media') or not sc_track.media:
                        continue
                    stream_url = None
                    for tc in (sc_track.media.transcodings or []):
                        if not tc.url:
                            continue
                        protocol = getattr(tc.format, 'protocol', '') if tc.format else ''
                        if protocol == 'progressive':
                            sep = '&' if '?' in tc.url else '?'
                            resp = req.get(f"{tc.url}{sep}client_id={sc.client_id}", timeout=10)
                            if resp.status_code == 200:
                                stream_url = resp.json().get('url')
                                break
                    if not stream_url:
                        continue

                    # Download to temp file (first 30 seconds worth)
                    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
                        tmp_path = tmp.name
                        resp = req.get(stream_url, stream=True, timeout=30)
                        downloaded = 0
                        for chunk in resp.iter_content(8192):
                            tmp.write(chunk)
                            downloaded += len(chunk)
                            if downloaded > 2_000_000:  # ~2MB = ~30sec of 128kbps
                                break

                    # Quick analysis
                    result_a = analyze_track(tmp_path)
                    if result_a.success:
                        thread_db.conn.execute("""
                            UPDATE tracks SET bpm = ?, musical_key = ?, camelot_key = ?,
                                energy = ?, analyzed_at = datetime('now')
                            WHERE track_id = ? AND bpm IS NULL
                        """, (result_a.bpm, result_a.musical_key, result_a.camelot_key,
                              result_a.energy, t.track_id))
                        thread_db.conn.commit()

                    os.unlink(tmp_path)
                except Exception:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
                    continue

        result = {"tracks": enrich(tracks)}

        if include_remixes:
            task.message = "Discovering remixes..."
            remix_tracks = svc.discover_remixes(
                genre, count,
                on_progress=lambda msg: setattr(task, 'message', msg)
            )
            result["remix_tracks"] = enrich(remix_tracks)

        task.result = result
        task.status = "completed"
        thread_db.close()
    except Exception as e:
        task.error = str(e)
        task.status = "failed"


def _run_related(task, sc, db_path, track_id, limit):
    from core.database import Database
    from core.discovery_service import DiscoveryService
    task.status = "running"
    try:
        thread_db = Database(db_path)
        svc = DiscoveryService(sc, thread_db)
        tracks = svc.discover_related(
            track_id, limit,
            on_progress=lambda msg: setattr(task, 'message', msg)
        )
        task.result = {"tracks": [t.model_dump() for t in tracks]}
        task.status = "completed"
        thread_db.close()
    except Exception as e:
        task.error = str(e)
        task.status = "failed"


@router.get("/genres")
def list_genres():
    return {k: {"display_name": v["display_name"], "folder": v["folder"]} for k, v in GENRES.items()}


@router.post("/discover")
def discover(req: DiscoverRequest, db=Depends(get_db), sc=Depends(get_sc)):
    if req.genre not in GENRES:
        return {"error": f"Unknown genre: {req.genre}"}

    task = create_task()
    t = threading.Thread(
        target=_run_discover,
        args=(task, sc, db.db_path, req.genre, req.count,
              req.include_remixes, req.include_curated, req.sort, req.analyze_on_discover),
        daemon=True
    )
    t.start()
    return {"task_id": task.id}


@router.post("/related")
def discover_related(req: RelatedRequest, db=Depends(get_db), sc=Depends(get_sc)):
    task = create_task()
    t = threading.Thread(
        target=_run_related,
        args=(task, sc, db.db_path, req.track_id, req.limit),
        daemon=True
    )
    t.start()
    return {"task_id": task.id}


@router.get("/top")
def get_top_tracks(limit: int = 10, db=Depends(get_db)):
    rows = db.conn.execute(
        "SELECT * FROM tracks WHERE trending_score > 0 ORDER BY trending_score DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/status/{task_id}")
def discovery_status(task_id: str):
    task = get_task(task_id)
    if not task:
        return {"error": "Task not found"}
    return {
        "id": task.id,
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
        "result": task.result,
        "error": task.error,
    }
