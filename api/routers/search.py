import asyncio
from typing import Optional

from fastapi import APIRouter, Depends

from api.dependencies import get_db, get_sc
from core.search_service import SearchService

router = APIRouter()


@router.get("/tracks")
async def search_tracks(q: str, limit: int = 50, db=Depends(get_db), sc=Depends(get_sc)):
    svc = SearchService(sc, db)
    tracks = await asyncio.to_thread(svc.search_tracks, q, limit)
    return [t.model_dump() for t in tracks]


@router.get("/artists")
async def search_artists(q: str, limit: int = 20, db=Depends(get_db), sc=Depends(get_sc)):
    svc = SearchService(sc, db)
    artists = await asyncio.to_thread(svc.search_artists, q, limit)
    return [a.model_dump() for a in artists]


@router.get("/artists/{user_id}/tracks")
async def artist_tracks(user_id: int, sort: str = "popular", limit: int = 50,
                        db=Depends(get_db), sc=Depends(get_sc)):
    svc = SearchService(sc, db)
    tracks = await asyncio.to_thread(svc.get_artist_tracks, user_id, sort, limit)
    return [t.model_dump() for t in tracks]
