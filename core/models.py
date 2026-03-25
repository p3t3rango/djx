from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from core.utils import sanitize_filename


class Track(BaseModel):
    track_id: int
    title: str
    artist: str
    permalink_url: str
    playback_count: int = 0
    likes_count: int = 0
    repost_count: int = 0
    genre: str = ""
    tags: str = ""
    duration_seconds: int = 0
    is_downloadable: bool = False
    artwork_url: Optional[str] = None
    created_at: Optional[str] = None
    trending_score: float = 0.0
    discovery_source: Optional[str] = None
    source_genre: Optional[str] = None

    @property
    def safe_filename(self) -> str:
        return sanitize_filename(f"{self.artist} - {self.title}")

    @classmethod
    def from_sc_track(cls, track, source: str = "search", genre: str = None) -> Optional["Track"]:
        try:
            created = None
            if hasattr(track, "created_at") and track.created_at:
                created = str(track.created_at)

            tag_list = ""
            if hasattr(track, "tag_list") and track.tag_list:
                tag_list = track.tag_list

            return cls(
                track_id=track.id,
                title=track.title or "Unknown",
                artist=getattr(track.user, "username", "Unknown") if track.user else "Unknown",
                permalink_url=track.permalink_url or "",
                playback_count=track.playback_count or 0,
                likes_count=track.likes_count or 0,
                repost_count=getattr(track, "reposts_count", 0) or 0,
                genre=track.genre or "",
                tags=tag_list,
                duration_seconds=(track.duration or 0) // 1000,
                is_downloadable=bool(track.downloadable),
                artwork_url=track.artwork_url,
                created_at=created,
                discovery_source=source,
                source_genre=genre,
            )
        except Exception:
            return None

    @classmethod
    def from_db_row(cls, row: dict) -> "Track":
        return cls(**{k: v for k, v in row.items() if k in cls.model_fields})

    def to_db_dict(self) -> dict:
        return self.model_dump()


class CuratedAccount(BaseModel):
    user_id: int
    username: str
    permalink_url: str = ""
    avatar_url: Optional[str] = None
    description: str = ""
    follower_count: int = 0
    track_count: int = 0
    genre: str = ""
    status: str = "suggested"
    suggested_reason: str = ""

    @classmethod
    def from_sc_user(cls, user, genre: str, reason: str = "") -> Optional["CuratedAccount"]:
        try:
            return cls(
                user_id=user.id,
                username=user.username or "Unknown",
                permalink_url=user.permalink_url or "",
                avatar_url=user.avatar_url,
                description=getattr(user, "description", "") or "",
                follower_count=getattr(user, "followers_count", 0) or 0,
                track_count=getattr(user, "track_count", 0) or 0,
                genre=genre,
                suggested_reason=reason,
            )
        except Exception:
            return None


class DownloadResult(BaseModel):
    track_id: int
    title: str
    artist: str
    status: str  # "downloaded", "skipped", "failed"
    method: Optional[str] = None
    error: Optional[str] = None
    file_path: Optional[str] = None


class DownloadReport(BaseModel):
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[DownloadResult] = Field(default_factory=list)
