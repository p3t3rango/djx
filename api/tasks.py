import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class BackgroundTask:
    id: str
    status: str = "pending"  # pending, running, completed, failed
    progress: int = 0
    message: str = ""
    result: Any = None
    error: Optional[str] = None


_tasks: dict = {}


def create_task() -> BackgroundTask:
    task = BackgroundTask(id=str(uuid.uuid4()))
    _tasks[task.id] = task
    return task


def get_task(task_id: str) -> Optional[BackgroundTask]:
    return _tasks.get(task_id)


def cleanup_old_tasks(max_tasks: int = 100):
    if len(_tasks) > max_tasks:
        completed = [k for k, v in _tasks.items() if v.status in ("completed", "failed")]
        for k in completed[:len(_tasks) - max_tasks]:
            del _tasks[k]
