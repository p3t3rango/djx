import threading
from fastapi import Request
from soundcloud import SoundCloud
from core.database import Database

_sc_lock = threading.Lock()
_db_path = "sc_discover.db"


def get_db(request: Request) -> Database:
    # Each request gets its own DB connection to avoid SQLite thread-safety segfaults
    if not hasattr(request.state, '_db'):
        request.state._db = Database(_db_path)
    return request.state._db


def get_sc(request: Request) -> SoundCloud:
    if not hasattr(request.app.state, '_sc') or request.app.state._sc is None:
        with _sc_lock:
            if not hasattr(request.app.state, '_sc') or request.app.state._sc is None:
                request.app.state._sc = SoundCloud()
    return request.app.state._sc
