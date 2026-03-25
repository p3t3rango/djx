import asyncio
import threading
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import get_db, get_sc
from api.tasks import create_task, get_task
from core.account_service import AccountService

router = APIRouter()


class SuggestRequest(BaseModel):
    genre: str
    limit: int = 10


class TastemakerRequest(BaseModel):
    sample_size: int = 20
    min_overlap: int = 2
    track_ids: Optional[list] = None  # specific tracks to scan, overrides sample_size


@router.get("/")
def list_accounts(genre: Optional[str] = None, status: Optional[str] = None,
                  db=Depends(get_db)):
    svc = AccountService(None, db)
    return svc.get_accounts(genre=genre, status=status)


@router.post("/suggest")
async def suggest_accounts(req: SuggestRequest, db=Depends(get_db), sc=Depends(get_sc)):
    svc = AccountService(sc, db)
    accounts = await asyncio.to_thread(svc.suggest_accounts, req.genre, req.limit)
    return [a.model_dump() for a in accounts]


@router.put("/{user_id}/approve")
def approve_account(user_id: int, db=Depends(get_db)):
    svc = AccountService(None, db)
    svc.approve_account(user_id)
    return {"status": "approved"}


@router.put("/{user_id}/reject")
def reject_account(user_id: int, db=Depends(get_db)):
    svc = AccountService(None, db)
    svc.reject_account(user_id)
    return {"status": "rejected"}


@router.get("/{user_id}/tracks")
async def account_tracks(user_id: int, limit: int = 30,
                         db=Depends(get_db), sc=Depends(get_sc)):
    svc = AccountService(sc, db)
    tracks = await asyncio.to_thread(svc.get_account_tracks, user_id, limit)
    return [t.model_dump() for t in tracks]


def _run_tastemaker(task, sc, db_path, sample_size, min_overlap, track_ids=None):
    from core.database import Database
    from core.account_service import AccountService
    task.status = "running"
    try:
        thread_db = Database(db_path)
        svc = AccountService(sc, thread_db)
        results = svc.find_tastemakers(
            sample_size=sample_size,
            min_overlap=min_overlap,
            track_ids=track_ids,
            on_progress=lambda msg: setattr(task, 'message', msg),
        )
        task.result = {"found": len(results), "accounts": [a.model_dump() for a in results]}
        task.message = f"Found {len(results)} tastemakers"
        task.status = "completed"
        thread_db.close()
    except Exception as e:
        task.error = str(e)
        task.status = "failed"


@router.post("/tastemakers")
def find_tastemakers(req: TastemakerRequest, db=Depends(get_db), sc=Depends(get_sc)):
    """Find users who liked/reposted multiple tracks in your library."""
    task = create_task()
    t = threading.Thread(
        target=_run_tastemaker,
        args=(task, sc, db.db_path, req.sample_size, req.min_overlap, req.track_ids),
        daemon=True
    )
    t.start()
    return {"task_id": task.id}


@router.get("/tastemakers/status/{task_id}")
def tastemaker_status(task_id: str):
    task = get_task(task_id)
    if not task:
        return {"error": "Task not found"}
    return {
        "id": task.id, "status": task.status, "message": task.message,
        "result": task.result, "error": task.error,
    }


def _run_related_artists(task, sc, db_path):
    from core.database import Database
    from core.account_service import AccountService
    task.status = "running"
    try:
        thread_db = Database(db_path)
        svc = AccountService(sc, thread_db)
        results = svc.find_related_artists(
            on_progress=lambda msg: setattr(task, 'message', msg),
        )
        task.result = {"found": len(results), "accounts": [a.model_dump() for a in results]}
        task.message = f"Found {len(results)} related artists"
        task.status = "completed"
        thread_db.close()
    except Exception as e:
        task.error = str(e)
        task.status = "failed"


@router.post("/related-artists")
def find_related_artists(db=Depends(get_db), sc=Depends(get_sc)):
    """Find artists related to artists in your library."""
    task = create_task()
    t = threading.Thread(
        target=_run_related_artists,
        args=(task, sc, db.db_path),
        daemon=True
    )
    t.start()
    return {"task_id": task.id}


@router.delete("/{user_id}")
def delete_account(user_id: int, db=Depends(get_db)):
    svc = AccountService(None, db)
    svc.delete_account(user_id)
    return {"deleted": True}
