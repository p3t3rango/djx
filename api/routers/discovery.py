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


class RelatedRequest(BaseModel):
    track_id: int
    limit: int = 50


def _run_discover(task, sc, db_path, genre, count, include_remixes, include_curated, sort):
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
        result = {"tracks": [t.model_dump() for t in tracks]}

        if include_remixes:
            task.message = "Discovering remixes..."
            remix_tracks = svc.discover_remixes(
                genre, count,
                on_progress=lambda msg: setattr(task, 'message', msg)
            )
            result["remix_tracks"] = [t.model_dump() for t in remix_tracks]

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
              req.include_remixes, req.include_curated, req.sort),
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
