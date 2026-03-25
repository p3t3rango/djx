"""
CDJ USB Export — creates a Pioneer-compatible USB drive structure.

Writes:
  /PIONEER/rekordbox/export.pdb  (track database)
  /PIONEER/ANLZ/XXXX/ANLZXXXX.DAT  (per-track analysis)
  /Contents/  (audio files)
"""

import json
import logging
import os
import shutil
from typing import List, Optional, Callable

from core.database import Database
from core.pdb_writer import PdbWriter
from core.anlz_writer import write_anlz_dat
from core.utils import sanitize_filename

logger = logging.getLogger(__name__)


class USBExporter:
    def __init__(self, db: Database, target_path: str):
        self.db = db
        self.target = os.path.expanduser(target_path)

    def export(self, track_ids: List[int] = None, playlist_name: str = None,
               on_progress: Optional[Callable] = None) -> dict:
        """Export tracks to a CDJ-ready USB structure."""

        def progress(msg):
            logger.info(msg)
            if on_progress:
                on_progress(msg)

        # Get tracks
        if track_ids:
            placeholders = ",".join("?" * len(track_ids))
            rows = self.db.conn.execute(f"""
                SELECT t.*, d.file_path, d.genre_folder
                FROM tracks t JOIN downloads d ON t.track_id = d.track_id
                WHERE t.track_id IN ({placeholders}) AND d.file_path IS NOT NULL
            """, track_ids).fetchall()
        else:
            rows = self.db.conn.execute("""
                SELECT t.*, d.file_path, d.genre_folder
                FROM tracks t JOIN downloads d ON t.track_id = d.track_id
                WHERE d.file_path IS NOT NULL AND d.status = 'completed'
            """).fetchall()

        tracks = [dict(r) for r in rows]
        if not tracks:
            return {"error": "No tracks to export", "exported": 0}

        progress(f"Exporting {len(tracks)} tracks...")

        # Create folder structure
        pioneer_dir = os.path.join(self.target, "PIONEER")
        rb_dir = os.path.join(pioneer_dir, "rekordbox")
        anlz_dir = os.path.join(pioneer_dir, "ANLZ")
        contents_dir = os.path.join(self.target, "Contents")
        os.makedirs(rb_dir, exist_ok=True)
        os.makedirs(anlz_dir, exist_ok=True)
        os.makedirs(contents_dir, exist_ok=True)

        # Collect unique artists, genres, keys
        artists = {}
        genres = {}
        keys = {}
        artist_counter = 1
        genre_counter = 1
        key_counter = 1

        for t in tracks:
            artist = t.get("artist", "Unknown")
            if artist not in artists:
                artists[artist] = artist_counter
                artist_counter += 1

            genre = t.get("genre") or t.get("genre_folder") or "Unknown"
            if genre not in genres:
                genres[genre] = genre_counter
                genre_counter += 1

            key = t.get("musical_key") or ""
            if key and key not in keys:
                keys[key] = key_counter
                key_counter += 1

        # Build .pdb
        pdb = PdbWriter()

        # Add artists
        for name, aid in artists.items():
            pdb.add_artist(aid, name)

        # Add genres
        for name, gid in genres.items():
            pdb.add_genre(gid, name)

        # Add keys
        for name, kid in keys.items():
            pdb.add_key(kid, name)

        # Process each track
        exported = 0
        for i, t in enumerate(tracks):
            progress(f"Processing {i+1}/{len(tracks)}: {t.get('title', 'Unknown')}")

            src_path = t["file_path"]
            if not os.path.exists(src_path):
                continue

            # Copy audio file
            ext = os.path.splitext(src_path)[1]
            safe_name = sanitize_filename(f"{t.get('artist', 'Unknown')} - {t.get('title', 'Unknown')}")
            dest_filename = f"{safe_name}{ext}"
            dest_path = os.path.join(contents_dir, dest_filename)

            if not os.path.exists(dest_path):
                shutil.copy2(src_path, dest_path)

            file_size = os.path.getsize(dest_path)

            # USB-relative path for the database
            usb_path = f"/Contents/{dest_filename}"

            # Track IDs
            track_id = exported + 1  # Sequential IDs for USB export
            artist_name = t.get("artist", "Unknown")
            genre_name = t.get("genre") or t.get("genre_folder") or "Unknown"
            key_name = t.get("musical_key") or ""

            artist_id = artists.get(artist_name, 0)
            genre_id = genres.get(genre_name, 0)
            key_id = keys.get(key_name, 0)

            bpm = t.get("bpm") or 0
            duration = t.get("duration_seconds") or 0

            # File type
            ext_lower = ext.lower()
            file_type = {'.mp3': 0x01, '.m4a': 0x04, '.flac': 0x05, '.wav': 0x0b, '.aiff': 0x0c}.get(ext_lower, 0x01)

            # ANLZ path
            anlz_num = f"{track_id:04d}"
            anlz_subdir = os.path.join(anlz_dir, anlz_num)
            os.makedirs(anlz_subdir, exist_ok=True)
            anlz_filename = f"ANLZ{anlz_num}.DAT"
            anlz_path = os.path.join(anlz_subdir, anlz_filename)
            anlz_usb_path = f"/PIONEER/ANLZ/{anlz_num}/{anlz_filename}"

            # Parse beats and cues from DB
            beats = []
            if t.get("beats_json"):
                try:
                    beats = json.loads(t["beats_json"])
                except (json.JSONDecodeError, TypeError):
                    pass

            cues = []
            if t.get("cues_json"):
                try:
                    cues = json.loads(t["cues_json"])
                except (json.JSONDecodeError, TypeError):
                    pass

            # Write ANLZ file
            write_anlz_dat(anlz_path, usb_path, bpm, beats, cues)

            # Add track to PDB
            pdb.add_track(
                track_id=track_id,
                title=t.get("title", "Unknown"),
                artist_id=artist_id,
                genre_id=genre_id,
                key_id=key_id,
                bpm=bpm,
                duration=duration,
                file_path=usb_path,
                filename=dest_filename,
                file_size=file_size,
                file_type=file_type,
                analyze_path=anlz_usb_path,
            )

            exported += 1

        # Add playlist if specified
        if playlist_name and exported > 0:
            pdb.add_playlist(playlist_id=1, name=playlist_name, parent_id=0)
            for i in range(exported):
                pdb.add_playlist_entry(i, i + 1, 1)

        # Write .pdb file
        pdb_path = os.path.join(rb_dir, "export.pdb")
        pdb.write(pdb_path)

        progress(f"Export complete: {exported} tracks")

        return {
            "exported": exported,
            "path": self.target,
            "pdb_path": pdb_path,
            "tracks_copied": exported,
        }
