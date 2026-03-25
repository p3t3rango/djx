import time
from typing import List, Optional

from soundcloud import SoundCloud

from core.config import get_float_setting
from core.database import Database
from core.models import Track, CuratedAccount
from core.trending import compute_trending_score


class SearchService:
    def __init__(self, sc: SoundCloud, db: Database):
        self.sc = sc
        self.db = db

    def search_tracks(self, query: str, limit: int = 50) -> List[Track]:
        tracks = []
        seen = set()
        try:
            results = self.sc.search_tracks(query)
            count = 0
            for track in results:
                if count >= limit * 2:
                    break
                t = Track.from_sc_track(track, source="search")
                if t and t.track_id not in seen and t.permalink_url:
                    t.trending_score = compute_trending_score(t)
                    seen.add(t.track_id)
                    tracks.append(t)
                count += 1
        except Exception:
            pass
        tracks.sort(key=lambda t: t.trending_score, reverse=True)
        return tracks[:limit]

    def search_artists(self, query: str, limit: int = 20) -> List[CuratedAccount]:
        artists = []
        try:
            results = self.sc.search_users(query)
            count = 0
            for user in results:
                if count >= limit:
                    break
                a = CuratedAccount.from_sc_user(user, genre="", reason=f"Search: {query}")
                if a:
                    artists.append(a)
                count += 1
        except Exception:
            pass
        return artists

    def get_artist_tracks(self, user_id: int, sort: str = "popular", limit: int = 50) -> List[Track]:
        tracks = []
        seen = set()
        delay = get_float_setting("api_delay", self.db)
        try:
            if sort == "popular":
                results = self.sc.get_user_popular_tracks(user_id)
            else:
                results = self.sc.get_user_tracks(user_id)
            count = 0
            for track in results:
                if count >= limit:
                    break
                t = Track.from_sc_track(track, source="artist")
                if t and t.track_id not in seen and t.permalink_url:
                    t.trending_score = compute_trending_score(t)
                    seen.add(t.track_id)
                    tracks.append(t)
                count += 1
        except Exception:
            pass
        tracks.sort(key=lambda t: t.trending_score, reverse=True)
        return tracks[:limit]
