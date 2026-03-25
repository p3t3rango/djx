import time
from typing import List, Optional, Callable

from soundcloud import SoundCloud

from core.config import GENRES, get_float_setting
from core.database import Database
from core.models import Track, CuratedAccount
from core.trending import compute_trending_score


class AccountService:
    def __init__(self, sc: SoundCloud, db: Database):
        self.sc = sc
        self.db = db

    def suggest_accounts(self, genre_key: str, limit: int = 10) -> List[CuratedAccount]:
        genre = GENRES[genre_key]
        delay = get_float_setting("api_delay", self.db)
        suggestions = []
        seen_ids = set()

        # Get existing account IDs to avoid re-suggesting
        existing = self.db.get_accounts(genre=genre_key)
        for a in existing:
            seen_ids.add(a["user_id"])

        for query in genre["search_queries"]:
            if len(suggestions) >= limit:
                break
            try:
                results = self.sc.search_users(query)
                count = 0
                for user in results:
                    if count >= 30:
                        break
                    acct = CuratedAccount.from_sc_user(
                        user, genre=genre_key,
                        reason=f"Found via search: '{query}'"
                    )
                    if (acct and acct.user_id not in seen_ids
                            and acct.track_count >= 5
                            and acct.follower_count >= 100):
                        seen_ids.add(acct.user_id)
                        acct.status = "suggested"
                        self.db.upsert_account(acct.model_dump())
                        suggestions.append(acct)
                    count += 1
                time.sleep(delay)
            except Exception:
                pass

        return suggestions[:limit]

    def approve_account(self, user_id: int):
        self.db.update_account_status(user_id, "approved")

    def reject_account(self, user_id: int):
        self.db.update_account_status(user_id, "rejected")

    def get_accounts(self, genre: str = None, status: str = None) -> List[dict]:
        return self.db.get_accounts(genre=genre, status=status)

    def get_account_tracks(self, user_id: int, limit: int = 30) -> List[Track]:
        tracks = []
        delay = get_float_setting("api_delay", self.db)
        try:
            results = self.sc.get_user_tracks(user_id)
            count = 0
            for track in results:
                if count >= limit:
                    break
                t = Track.from_sc_track(track, source="curated_account")
                if t and t.permalink_url:
                    t.trending_score = compute_trending_score(t)
                    tracks.append(t)
                count += 1
        except Exception:
            pass
        tracks.sort(key=lambda t: t.trending_score, reverse=True)
        return tracks

    def find_tastemakers(self, sample_size: int = 20, min_overlap: int = 2,
                         track_ids: list = None,
                         on_progress: Optional[Callable] = None) -> List[CuratedAccount]:
        """Find users who liked/reposted multiple tracks in your library."""
        import logging
        logger = logging.getLogger(__name__)
        delay = get_float_setting("api_delay", self.db)

        if track_ids:
            # Use specific tracks provided by user
            placeholders = ",".join("?" * len(track_ids))
            rows = self.db.conn.execute(f"""
                SELECT t.track_id, t.title, t.playback_count FROM tracks t
                WHERE t.track_id IN ({placeholders}) AND t.title != ''
            """, track_ids).fetchall()
        else:
            # Auto-sample top tracks from library
            rows = self.db.conn.execute("""
                SELECT t.track_id, t.title, t.playback_count FROM tracks t
                JOIN downloads d ON t.track_id = d.track_id
                WHERE d.status = 'completed' AND t.title != ''
                ORDER BY t.playback_count DESC
                LIMIT ?
            """, (sample_size,)).fetchall()

        if not rows:
            return []

        # Count how many times each user appears across likers/reposters
        user_counts: dict = {}  # user_id -> {count, user_obj, tracks}
        existing_ids = set(a["user_id"] for a in self.db.get_accounts())

        for i, row in enumerate(rows):
            if on_progress:
                on_progress(f"Scanning likers for {i+1}/{len(rows)}: {row['title'][:30]}")

            # Get likers
            try:
                likers = self.sc.get_track_likers(row["track_id"])
                count = 0
                for user in likers:
                    if count >= 50:
                        break
                    uid = user.id
                    if uid in existing_ids:
                        count += 1
                        continue
                    if uid not in user_counts:
                        user_counts[uid] = {"count": 0, "user": user, "tracks": []}
                    user_counts[uid]["count"] += 1
                    user_counts[uid]["tracks"].append(row["title"])
                    count += 1
                time.sleep(delay)
            except Exception as e:
                logger.debug(f"Likers error for {row['track_id']}: {e}")

            # Get reposters
            try:
                reposters = self.sc.get_track_reposters(row["track_id"])
                count = 0
                for user in reposters:
                    if count >= 50:
                        break
                    uid = user.id
                    if uid in existing_ids:
                        count += 1
                        continue
                    if uid not in user_counts:
                        user_counts[uid] = {"count": 0, "user": user, "tracks": []}
                    user_counts[uid]["count"] += 1
                    if row["title"] not in user_counts[uid]["tracks"]:
                        user_counts[uid]["tracks"].append(row["title"])
                    count += 1
                time.sleep(delay)
            except Exception as e:
                logger.debug(f"Reposters error for {row['track_id']}: {e}")

        # Filter to users with min_overlap matches, sort by count
        matches = [(uid, data) for uid, data in user_counts.items()
                    if data["count"] >= min_overlap]
        matches.sort(key=lambda x: x[1]["count"], reverse=True)

        # Convert to CuratedAccount objects
        results = []
        for uid, data in matches[:20]:  # Top 20
            user = data["user"]
            track_names = data["tracks"][:5]
            reason = f"Liked {data['count']} tracks in your library: {', '.join(track_names)}"
            acct = CuratedAccount.from_sc_user(user, genre="", reason=reason)
            if acct and acct.track_count >= 3:
                acct.status = "suggested"
                self.db.upsert_account(acct.model_dump())
                results.append(acct)

        if on_progress:
            on_progress(f"Found {len(results)} tastemakers")

        return results

    def find_related_artists(self, on_progress: Optional[Callable] = None) -> List[CuratedAccount]:
        """Find artists related to artists in your library via SoundCloud's algorithm."""
        import logging
        logger = logging.getLogger(__name__)
        delay = get_float_setting("api_delay", self.db)

        # Get unique artists from your downloads
        rows = self.db.conn.execute("""
            SELECT DISTINCT t.artist, t.track_id FROM tracks t
            JOIN downloads d ON t.track_id = d.track_id
            WHERE d.status = 'completed' AND t.title != '' AND t.artist != ''
            ORDER BY t.playback_count DESC
            LIMIT 30
        """).fetchall()

        if not rows:
            return []

        existing_ids = set(a["user_id"] for a in self.db.get_accounts())
        seen_artists = set()
        results = []

        # For each artist, find their user_id then get related artists
        for i, row in enumerate(rows):
            if on_progress:
                on_progress(f"Finding artists related to {row['artist'][:25]} ({i+1}/{len(rows)})")

            try:
                # Search for the artist to get their user_id
                users = self.sc.search_users(row["artist"])
                artist_user = None
                count = 0
                for u in users:
                    if count >= 3:
                        break
                    # Match by name similarity
                    if u.username and row["artist"].lower() in u.username.lower():
                        artist_user = u
                        break
                    count += 1

                if not artist_user:
                    time.sleep(delay)
                    continue

                if artist_user.id in seen_artists:
                    continue
                seen_artists.add(artist_user.id)

                # Get related artists
                related = self.sc.get_user_related_artists(artist_user.id)
                rel_count = 0
                for rel_user in related:
                    if rel_count >= 10:
                        break
                    if rel_user.id in existing_ids or rel_user.id in seen_artists:
                        rel_count += 1
                        continue

                    acct = CuratedAccount.from_sc_user(
                        rel_user, genre="",
                        reason=f"Related to {row['artist']}"
                    )
                    if acct and acct.track_count >= 3:
                        seen_artists.add(rel_user.id)
                        acct.status = "suggested"
                        self.db.upsert_account(acct.model_dump())
                        results.append(acct)
                    rel_count += 1

                time.sleep(delay)
            except Exception as e:
                logger.debug(f"Related artists error for {row['artist']}: {e}")

        if on_progress:
            on_progress(f"Found {len(results)} related artists")

        return results

    def delete_account(self, user_id: int):
        self.db.delete_account(user_id)
