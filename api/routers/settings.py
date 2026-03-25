from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Dict

from api.dependencies import get_db
from core.config import DEFAULTS, GENRES

router = APIRouter()


class SettingsUpdate(BaseModel):
    settings: Dict[str, str]


@router.get("/")
def get_settings(db=Depends(get_db)):
    db_settings = db.get_all_settings()
    # Merge defaults with DB overrides
    result = dict(DEFAULTS)
    result.update(db_settings)
    return result


@router.put("/")
def update_settings(req: SettingsUpdate, db=Depends(get_db)):
    for key, value in req.settings.items():
        db.set_setting(key, value)
    return {"updated": True}


@router.get("/genres")
def get_genres():
    return GENRES
