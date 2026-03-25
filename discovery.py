import time
from typing import List, Set

from rich.console import Console
from soundcloud import SoundCloud

from config import (
    GENRES, REMIX_SUFFIXES, MIN_PLAYBACK_COUNT,
    MIN_DURATION_SEC, MAX_DURATION_SEC, API_DELAY,
)
from models import DiscoveredTrack

console = Console()


class TrackDiscoverer:
    def __init__(self):
        console.print("[dim]Connecting to SoundCloud...[/dim]")
        self.sc = SoundCloud()
        console.print("[green]Connected.[/green]")

    def discover_genre(self, genre_key: str, target: int = 50) -> List[DiscoveredTrack]:
        genre = GENRES[genre_key]
        accepted = genre.get("accepted_genres", [])
        seen: Set[int] = set()
        tracks: List[DiscoveredTrack] = []

        # Strategy 1: Genre-filtered search
        console.print(f"  [dim]Searching with genre filter...[/dim]")
        search_tracks = self._try_search(
            genre["search_queries"], target, seen,
            accepted_genres=accepted,
        )
        tracks.extend(search_tracks)
        if len(tracks) >= target:
            return sorted(tracks, key=lambda t: t.sort_key, reverse=True)[:target]

        # Strategy 2: Tag recent
        console.print(f"  [dim]Fetching recent tagged tracks...[/dim]")
        remaining = target - len(tracks)
        tag_tracks = self._try_tag_recent(genre["tags"], remaining, seen)
        tracks.extend(tag_tracks)
        if len(tracks) >= target:
            return sorted(tracks, key=lambda t: t.sort_key, reverse=True)[:target]

        # Strategy 3: Broader search (no genre filter, for hard-to-find genres)
        console.print(f"  [dim]Broadening search...[/dim]")
        remaining = target - len(tracks)
        broad_tracks = self._try_search(genre["search_queries"], remaining, seen)
        tracks.extend(broad_tracks)
        if len(tracks) >= target:
            return sorted(tracks, key=lambda t: t.sort_key, reverse=True)[:target]

        # Strategy 4: Related expansion
        if tracks and len(tracks) < target:
            console.print(f"  [dim]Expanding via related tracks...[/dim]")
            remaining = target - len(tracks)
            related = self._try_related(tracks[:5], remaining, seen)
            tracks.extend(related)

        return sorted(tracks, key=lambda t: t.sort_key, reverse=True)[:target]

    def discover_remixes(self, genre_key: str, target: int = 50) -> List[DiscoveredTrack]:
        genre = GENRES[genre_key]
        seen: Set[int] = set()
        tracks: List[DiscoveredTrack] = []

        remix_queries = []
        for q in genre["search_queries"]:
            for suffix in REMIX_SUFFIXES:
                remix_queries.append(f"{q} {suffix}")

        console.print(f"  [dim]Searching for remixes...[/dim]")
        search_tracks = self._try_search(remix_queries, target, seen)
        tracks.extend(search_tracks)

        if tracks and len(tracks) < target:
            console.print(f"  [dim]Expanding via related tracks...[/dim]")
            remaining = target - len(tracks)
            related = self._try_related(tracks[:5], remaining, seen)
            tracks.extend(related)

        return sorted(tracks, key=lambda t: t.sort_key, reverse=True)[:target]

    def _try_search(self, queries: List[str], limit: int, seen: Set[int],
                    accepted_genres: List[str] = None) -> List[DiscoveredTrack]:
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
                    dt = DiscoveredTrack.from_sc_track(track)
                    if dt and self._passes_filter(dt) and dt.track_id not in seen:
                        if accepted_genres and not self._genre_matches(dt.genre, accepted_genres):
                            count += 1
                            continue
                        seen.add(dt.track_id)
                        all_tracks.append(dt)
                    count += 1
                time.sleep(API_DELAY)
            except Exception as e:
                console.print(f"  [yellow]Search error for '{query}': {e}[/yellow]")
        console.print(f"  [dim]Search: found {len(all_tracks)} tracks[/dim]")
        return sorted(all_tracks, key=lambda t: t.sort_key, reverse=True)[:limit]

    @staticmethod
    def _genre_matches(track_genre: str, accepted: List[str]) -> bool:
        if not track_genre:
            return False
        lower = track_genre.lower().strip()
        return any(a.lower() == lower for a in accepted)

    def _try_tag_recent(self, tags: List[str], limit: int, seen: Set[int]) -> List[DiscoveredTrack]:
        all_tracks = []
        for tag in tags:
            try:
                results = self.sc.get_tag_tracks_recent(tag)
                count = 0
                for track in results:
                    if count >= 200:
                        break
                    dt = DiscoveredTrack.from_sc_track(track)
                    if dt and self._passes_filter(dt) and dt.track_id not in seen:
                        seen.add(dt.track_id)
                        all_tracks.append(dt)
                    count += 1
                time.sleep(API_DELAY)
            except Exception as e:
                console.print(f"  [yellow]Tag recent error for '{tag}': {e}[/yellow]")
        console.print(f"  [dim]Tag recent: found {len(all_tracks)} tracks[/dim]")
        return sorted(all_tracks, key=lambda t: t.sort_key, reverse=True)[:limit]

    def _try_related(self, seed_tracks: List[DiscoveredTrack], limit: int, seen: Set[int]) -> List[DiscoveredTrack]:
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
                    dt = DiscoveredTrack.from_sc_track(track)
                    if dt and self._passes_filter(dt) and dt.track_id not in seen:
                        seen.add(dt.track_id)
                        related.append(dt)
                    count += 1
                time.sleep(API_DELAY)
            except Exception as e:
                console.print(f"  [yellow]Related tracks error: {e}[/yellow]")
        console.print(f"  [dim]Related: found {len(related)} tracks[/dim]")
        return sorted(related, key=lambda t: t.sort_key, reverse=True)[:limit]

    def _passes_filter(self, track: DiscoveredTrack) -> bool:
        if track.playback_count < MIN_PLAYBACK_COUNT:
            return False
        if track.duration_seconds < MIN_DURATION_SEC:
            return False
        if track.duration_seconds > MAX_DURATION_SEC:
            return False
        if not track.permalink_url:
            return False
        return True
