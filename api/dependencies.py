import os
import threading
from typing import Generator
from fastapi import Request, Depends
from soundcloud import SoundCloud
from core.database import Database

_sc_lock = threading.Lock()
_db_path = os.environ.get("DJX_DB_PATH", "sc_discover.db")


def get_db(request: Request) -> Generator[Database, None, None]:
    """Each request gets its own DB connection, closed after the request."""
    db = Database(_db_path)
    try:
        yield db
    finally:
        db.close()


def get_sc(request: Request) -> SoundCloud:
    if not hasattr(request.app.state, '_sc') or request.app.state._sc is None:
        with _sc_lock:
            if not hasattr(request.app.state, '_sc') or request.app.state._sc is None:
                request.app.state._sc = SoundCloud()
    return request.app.state._sc
