import logging
import time
from typing import List, Set, Optional, Callable

from soundcloud import SoundCloud

from core.config import GENRES, REMIX_SUFFIXES, get_int_setting, get_float_setting
from core.database import Database
from core.models import Track
from core.trending import compute_trending_score

logger = logging.getLogger(__name__)


class DiscoveryService:
    def __init__(self, sc: SoundCloud, db: Database):
        self.sc = sc
        self.db = db

    def discover_genre(self, genre_key: str, target: int = None,
                       include_curated: bool = True,
                       sort: str = "trending",
                       on_progress: Optional[Callable] = None) -> List[Track]:
        genre = GENRES[genre_key]
        if target is None:
            target = get_int_setting("tracks_per_genre", self.db)
        delay = get_float_setting("api_delay", self.db)

        seen: Set[int] = set()
        tracks: List[Track] = []

        def progress(msg):
            logger.info(msg)
            if on_progress:
                on_progress(msg)

        # Strategy 1: Tag recent (best for finding genre-correct tracks)
        progress("Fetching recent tagged tracks...")
        tag_tracks = self._search_by_tags(genre["tags"], target * 2, seen, genre_key, delay)
        tracks.extend(tag_tracks)

        # Strategy 2: Curated account tracks
        if include_curated:
            approved = self.db.get_accounts(genre=genre_key, status="approved")
            if approved:
                progress(f"Checking {len(approved)} curated accounts...")
                acct_tracks = self._from_curated_accounts(approved, target, seen, genre_key, delay)
                tracks.extend(acct_tracks)

        # Strategy 3: Genre-filtered search (checks genre field + tags + title)
        if len(tracks) < target:
            progress("Searching with genre filter...")
            search_tracks = self._search_tracks(
                genre["search_queries"], target * 2, seen, genre_key,
                genre["accepted_genres"], genre["tags"], delay
            )
            tracks.extend(search_tracks)

        # Strategy 4: Related expansion
        if tracks and len(tracks) < target:
            progress("Expanding via related tracks...")
            remaining = target - len(tracks)
            related = self._related_expansion(tracks[:5], remaining, seen, genre_key, delay)
            tracks.extend(related)

        # Score all tracks
        for t in tracks:
            t.trending_score = compute_trending_score(t)

        # Sort based on mode
        if sort == "popular":
            tracks.sort(key=lambda t: t.playback_count, reverse=True)
        elif sort == "fresh":
            tracks.sort(key=lambda t: t.created_at or "", reverse=True)
        else:  # "trending"
            tracks.sort(key=lambda t: t.trending_score, reverse=True)

        result = tracks[:target]

        # Store in DB
        for t in result:
            self.db.upsert_track(t.to_db_dict())

        progress(f"Found {len(result)} tracks")
        return result

    def discover_related(self, track_id: int, limit: int = 50,
                         on_progress: Optional[Callable] = None) -> List[Track]:
        """Find tracks related to a given track."""
        def progress(msg):
            logger.info(msg)
            if on_progress:
                on_progress(msg)

        delay = get_float_setting("api_delay", self.db)
        seen: Set[int] = {track_id}
        tracks: List[Track] = []

        progress("Finding related tracks...")
        try:
            results = self.sc.get_track_related(track_id)
            count = 0
            for track in results:
                if count >= limit * 2:
                    break
                t = Track.from_sc_track(track, source="related")
                if t and t.track_id not in seen and t.permalink_url:
                    t.trending_score = compute_trending_score(t)
                    seen.add(t.track_id)
                    tracks.append(t)
                count += 1
        except Exception as e:
            logger.warning(f"Related tracks error: {e}")

        tracks.sort(key=lambda t: t.trending_score, reverse=True)
        result = tracks[:limit]

        for t in result:
            self.db.upsert_track(t.to_db_dict())

        progress(f"Found {len(result)} related tracks")
        return result

    def discover_remixes(self, genre_key: str, target: int = None,
                         on_progress: Optional[Callable] = None) -> List[Track]:
        genre = GENRES[genre_key]
        if target is None:
            target = get_int_setting("tracks_per_genre", self.db)
        delay = get_float_setting("api_delay", self.db)

        seen: Set[int] = set()
        tracks: List[Track] = []

        def progress(msg):
            logger.info(msg)
            if on_progress:
                on_progress(msg)

        remix_queries = []
        for q in genre["search_queries"]:
            for suffix in REMIX_SUFFIXES:
                remix_queries.append(f"{q} {suffix}")

        progress("Searching for remixes...")
        search_tracks = self._search_tracks(remix_queries, target * 2, seen, genre_key, delay=delay)
        tracks.extend(search_tracks)

        if tracks and len(tracks) < target:
            progress("Expanding via related tracks...")
            remaining = target - len(tracks)
            related = self._related_expansion(tracks[:5], remaining, seen, genre_key, delay)
            tracks.extend(related)

        for t in tracks:
            t.trending_score = compute_trending_score(t)

        tracks.sort(key=lambda t: t.trending_score, reverse=True)
        result = tracks[:target]

        for t in result:
            self.db.upsert_track(t.to_db_dict())

        progress(f"Found {len(result)} remix tracks")
        return result

    def _search_by_tags(self, tags: List[str], limit: int, seen: Set[int],
                        genre_key: str, delay: float) -> List[Track]:
        all_tracks = []
        for tag in tags:
            try:
                results = self.sc.get_tag_tracks_recent(tag)
                count = 0
                for track in results:
                    if count >= 200:
                        break
                    t = Track.from_sc_track(track, source="tag_recent", genre=genre_key)
                    if t and self._passes_filter(t) and t.track_id not in seen:
                        seen.add(t.track_id)
                        all_tracks.append(t)
                    count += 1
                time.sleep(delay)
            except Exception as e:
                logger.warning(f"Tag search error for '{tag}': {e}")
        return all_tracks

    def _search_tracks(self, queries: List[str], limit: int, seen: Set[int],
                       genre_key: str, accepted_genres: List[str] = None,
                       genre_tags: List[str] = None, delay: float = 0.5) -> List[Track]:
        all_tracks = []
        for query in queries:
            if len(all_tracks) >= limit:
                break
            try:
                results = self.sc.search_tracks(query)
                count = 0
                for track in results:
                    if count >= 200:
                        break
                    t = Track.from_sc_track(track, source="search", genre=genre_key)
                    if t and self._passes_filter(t) and t.track_id not in seen:
                        if accepted_genres and not self._matches_genre(t, accepted_genres, genre_tags):
                            count += 1
                            continue
                        seen.add(t.track_id)
                        all_tracks.append(t)
                    count += 1
                time.sleep(delay)
            except Exception as e:
                logger.warning(f"Search error for '{query}': {e}")
        return all_tracks

    def _from_curated_accounts(self, accounts: List[dict], limit: int, seen: Set[int],
                                genre_key: str, delay: float) -> List[Track]:
        all_tracks = []
        for acct in accounts:
            if len(all_tracks) >= limit:
                break
            try:
                results = self.sc.get_user_tracks(acct["user_id"])
                count = 0
                for track in results:
                    if count >= 50:
                        break
                    t = Track.from_sc_track(track, source="curated_account", genre=genre_key)
                    if t and self._passes_filter(t) and t.track_id not in seen:
                        seen.add(t.track_id)
                        all_tracks.append(t)
                    count += 1
                time.sleep(delay)
            except Exception as e:
                logger.warning(f"Curated account error for '{acct.get('username', '')}': {e}")
        return all_tracks

    def _related_expansion(self, seed_tracks: List[Track], limit: int, seen: Set[int],
                           genre_key: str, delay: float) -> List[Track]:
        related = []
        for seed in seed_tracks:
            if len(related) >= limit:
                break
            try:
                results = self.sc.get_track_related(seed.track_id)
                count = 0
                for track in results:
                    if count >= 50:
                        break
                    t = Track.from_sc_track(track, source="related", genre=genre_key)
                    if t and self._passes_filter(t) and t.track_id not in seen:
                        seen.add(t.track_id)
                        related.append(t)
                    count += 1
                time.sleep(delay)
            except Exception as e:
                logger.warning(f"Related tracks error: {e}")
        return related

    def _matches_genre(self, track: Track, accepted: List[str], genre_tags: List[str] = None) -> bool:
        # Check 1: SC genre field
        if track.genre:
            lower = track.genre.lower().strip()
            if any(a.lower() == lower for a in accepted):
                return True

        # Check 2: Track's tag_list
        if track.tags and genre_tags:
            tags_lower = track.tags.lower()
            for tag in genre_tags:
                if tag.lower() in tags_lower:
                    return True

        # Check 3: Title keywords (last resort)
        if genre_tags:
            title_lower = track.title.lower()
            for tag in genre_tags:
                if tag.lower() in title_lower:
                    return True

        return False

    def _passes_filter(self, track: Track) -> bool:
        min_plays = get_int_setting("min_playback_count", self.db)
        min_dur = get_int_setting("min_duration_sec", self.db)
        max_dur = get_int_setting("max_duration_sec", self.db)

        if track.playback_count < min_plays:
            return False
        if track.duration_seconds < min_dur:
            return False
        if track.duration_seconds > max_dur:
            return False
        if not track.permalink_url:
            return False
        return True
