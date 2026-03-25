from dataclasses import dataclass
from typing import Optional
from utils import sanitize_filename


@dataclass
class DiscoveredTrack:
    track_id: int
    title: str
    artist: str
    permalink_url: str
    playback_count: int
    likes_count: int
    genre: str
    duration_seconds: int
    is_downloadable: bool
    artwork_url: Optional[str] = None

    @property
    def safe_filename(self) -> str:
        return sanitize_filename(f"{self.artist} - {self.title}")

    @property
    def sort_key(self) -> int:
        return self.playback_count

    @classmethod
    def from_sc_track(cls, track) -> Optional["DiscoveredTrack"]:
        try:
            return cls(
                track_id=track.id,
                title=track.title or "Unknown",
                artist=getattr(track.user, "username", "Unknown") if track.user else "Unknown",
                permalink_url=track.permalink_url or "",
                playback_count=track.playback_count or 0,
                likes_count=track.likes_count or 0,
                genre=track.genre or "",
                duration_seconds=(track.duration or 0) // 1000,
                is_downloadable=bool(track.downloadable),
                artwork_url=track.artwork_url,
            )
        except Exception:
            return None

    @classmethod
    def from_chart_dict(cls, data: dict) -> Optional["DiscoveredTrack"]:
        try:
            track = data.get("track", data)
            user = track.get("user", {})
            return cls(
                track_id=track["id"],
                title=track.get("title", "Unknown"),
                artist=user.get("username", "Unknown"),
                permalink_url=track.get("permalink_url", ""),
                playback_count=track.get("playback_count", 0) or 0,
                likes_count=track.get("likes_count", 0) or 0,
                genre=track.get("genre", ""),
                duration_seconds=(track.get("duration", 0) or 0) // 1000,
                is_downloadable=bool(track.get("downloadable", False)),
                artwork_url=track.get("artwork_url"),
            )
        except (KeyError, TypeError):
            return None
