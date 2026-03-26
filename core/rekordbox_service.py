import hashlib
import json
import logging
import os
from typing import List, Optional

from core.camelot import to_camelot
from core.database import Database

logger = logging.getLogger(__name__)

# Default Rekordbox DB locations on macOS
_RB_DB_PATHS = [
    os.path.expanduser("~/Library/Pioneer/rekordbox/master.db"),
    os.path.expanduser("~/Library/Application Support/Pioneer/rekordbox/master.db"),
]

# Common Rekordbox XML export locations
_RB_XML_PATHS = [
    os.path.expanduser("~/Library/Pioneer/rekordbox/rekordbox.xml"),
    os.path.expanduser("~/Music/rekordbox.xml"),
    os.path.expanduser("~/Desktop/rekordbox.xml"),
]


def find_rekordbox_db() -> Optional[str]:
    """Auto-detect Rekordbox database location."""
    for path in _RB_DB_PATHS:
        if os.path.exists(path):
            return path
    return None


def find_rekordbox_xml() -> Optional[str]:
    """Auto-detect Rekordbox XML export location."""
    for path in _RB_XML_PATHS:
        if os.path.exists(path):
            return path
    return None


class RekordboxService:
    def __init__(self, db: Database):
        self.db = db

    def export_to_rekordbox_xml(self, track_ids: List[int] = None,
                                 output_path: str = "rekordbox_export.xml") -> dict:
        """Export analyzed tracks to Rekordbox XML format.
        This is the safest method — import the XML into Rekordbox manually."""
        try:
            from pyrekordbox import RekordboxXml

            if track_ids:
                placeholders = ",".join("?" * len(track_ids))
                rows = self.db.conn.execute(f"""
                    SELECT t.*, d.file_path FROM tracks t
                    JOIN downloads d ON t.track_id = d.track_id
                    WHERE t.track_id IN ({placeholders})
                    AND t.bpm IS NOT NULL AND d.file_path IS NOT NULL
                """, track_ids).fetchall()
            else:
                rows = self.db.conn.execute("""
                    SELECT t.*, d.file_path FROM tracks t
                    JOIN downloads d ON t.track_id = d.track_id
                    WHERE t.bpm IS NOT NULL AND d.file_path IS NOT NULL
                """).fetchall()

            xml = RekordboxXml(name="DJX", version="2.0")

            exported = 0
            for r in rows:
                file_path = r["file_path"]
                if not file_path or not os.path.exists(file_path):
                    continue

                abs_path = os.path.abspath(file_path)

                xml.add_track(
                    abs_path,
                    TrackID=r["track_id"],
                    Name=r["title"] or "Unknown",
                    Artist=r["artist"] or "Unknown",
                    Genre=r["genre"] or "",
                    AverageBpm=round(r["bpm"], 2) if r["bpm"] else 0,
                    Tonality=r["musical_key"] or "",
                    TotalTime=r["duration_seconds"] or 0,
                )
                exported += 1

            xml.save(output_path)
            return {"exported": exported, "path": os.path.abspath(output_path)}

        except ImportError:
            return {"error": "pyrekordbox not installed"}
        except Exception as e:
            logger.error(f"Rekordbox export error: {e}")
            return {"error": str(e)}

    def create_playlist_xml(self, name: str, track_ids: List[int],
                            output_path: str = "rekordbox_export.xml") -> dict:
        """Create a Rekordbox XML with a playlist."""
        try:
            from pyrekordbox import RekordboxXml

            xml = RekordboxXml(name="DJX", version="2.0")

            # Add tracks
            valid_ids = []
            for tid in track_ids:
                row = self.db.conn.execute("""
                    SELECT t.*, d.file_path FROM tracks t
                    JOIN downloads d ON t.track_id = d.track_id
                    WHERE t.track_id = ? AND d.file_path IS NOT NULL
                """, (tid,)).fetchone()

                if not row or not row["file_path"] or not os.path.exists(row["file_path"]):
                    continue

                abs_path = os.path.abspath(row["file_path"])
                xml.add_track(
                    abs_path,
                    TrackID=row["track_id"],
                    Name=row["title"] or "Unknown",
                    Artist=row["artist"] or "Unknown",
                    Genre=row["genre"] or "",
                    AverageBpm=round(row["bpm"], 2) if row["bpm"] else 0,
                    Tonality=row["musical_key"] or "",
                    TotalTime=row["duration_seconds"] or 0,
                )
                valid_ids.append(row["track_id"])

            # Create playlist
            playlist = xml.add_playlist(name)
            for tid in valid_ids:
                playlist.add_track(xml.get_track(TrackID=tid))

            xml.save(output_path)
            return {"exported": len(valid_ids), "playlist": name, "path": os.path.abspath(output_path)}

        except Exception as e:
            logger.error(f"Playlist export error: {e}")
            return {"error": str(e)}

    def import_from_xml(self, xml_path: str) -> dict:
        """Import tracks from a Rekordbox XML file into the DJX library.

        Matches tracks by file path (exact or filename match). For new tracks,
        creates entries from the XML metadata. For existing tracks, fills in
        any missing analysis data (BPM, key, cues).
        """
        try:
            from pyrekordbox import RekordboxXml
        except ImportError:
            return {"error": "pyrekordbox not installed. Run: pip install pyrekordbox"}

        xml_path = os.path.expanduser(xml_path)
        if not os.path.exists(xml_path):
            return {"error": f"File not found: {xml_path}"}

        try:
            xml = RekordboxXml(xml_path)
        except Exception as e:
            return {"error": f"Failed to parse XML: {e}"}

        # Build lookup of existing tracks by filename
        existing_by_file = {}
        for row in self.db.conn.execute(
            "SELECT track_id, file_path FROM downloads WHERE file_path IS NOT NULL"
        ).fetchall():
            fp = row["file_path"]
            existing_by_file[os.path.abspath(fp)] = row["track_id"]
            existing_by_file[os.path.basename(fp)] = row["track_id"]

        imported = 0
        updated = 0
        skipped = 0

        for track in xml.get_tracks():
            location = track.get("Location", "")
            if not location:
                skipped += 1
                continue

            # Extract all metadata from XML
            name = track.get("Name", "")
            artist = track.get("Artist", "")
            genre = track.get("Genre", "")
            bpm = track.get("AverageBpm")
            tonality = track.get("Tonality", "")  # e.g. "C# minor", "6A", "Gm"
            total_time = track.get("TotalTime", 0)
            rb_track_id = track.get("TrackID")
            album = track.get("Album", "")
            label = track.get("Label", "")
            rating = track.get("Rating", 0)
            comments = track.get("Comments", "")
            colour = track.get("Colour", "")

            # Normalize BPM
            if bpm:
                try:
                    bpm = float(bpm)
                    if bpm <= 0:
                        bpm = None
                except (ValueError, TypeError):
                    bpm = None

            # Normalize key: convert to "X major/minor" + Camelot
            musical_key, camelot_key = self._parse_tonality(tonality)

            # Parse cue points / hot cues from marks
            cues = []
            try:
                marks_list = list(track.marks)
                for mark in marks_list:
                    mark_type = str(mark.get("Type", "cue")).lower()
                    is_loop = mark_type in ("4", "loop")
                    cue = {
                        "name": mark.get("Name", ""),
                        "type": "loop" if is_loop else "cue",
                        "start": float(mark.get("Start", 0)),
                        "num": int(mark.get("Num", 0)),
                    }
                    end = mark.get("End")
                    if end is not None:
                        cue["end"] = float(end)
                    cues.append(cue)
            except Exception as e:
                logger.warning(f"Mark parse error for {name}: {e}")

            cues_json = json.dumps(cues) if cues else None

            # Parse tempo / beatgrid
            beats = []
            try:
                for tempo in track.tempos:
                    beats.append({
                        "bpm": float(tempo.get("Bpm", 0)),
                        "inizio": float(tempo.get("Inizio", 0)),
                    })
            except Exception:
                pass

            # Check if file exists on disk
            file_exists = os.path.exists(location)

            # Try to match to existing DB track
            abs_loc = os.path.abspath(location) if file_exists else location
            basename = os.path.basename(location)
            existing_tid = existing_by_file.get(abs_loc) or existing_by_file.get(basename)

            if existing_tid:
                # Update existing track with any missing analysis data
                self.db.conn.execute("""
                    UPDATE tracks SET
                        bpm = COALESCE(bpm, ?),
                        musical_key = COALESCE(musical_key, ?),
                        camelot_key = COALESCE(camelot_key, ?),
                        cues_json = COALESCE(cues_json, ?),
                        genre = CASE WHEN genre = '' THEN ? ELSE genre END
                    WHERE track_id = ?
                """, (bpm, musical_key, camelot_key, cues_json, genre, existing_tid))
                # Update file path if the file exists at the XML location
                if file_exists:
                    self.db.conn.execute(
                        "UPDATE downloads SET file_path = ? WHERE track_id = ?",
                        (abs_loc, existing_tid))
                updated += 1
            else:
                # New track — create entry
                # Generate a negative track_id from path hash
                track_id = -abs(int(hashlib.md5(location.encode()).hexdigest()[:8], 16))

                # Check for ID collision
                if self.db.conn.execute("SELECT 1 FROM tracks WHERE track_id = ?", (track_id,)).fetchone():
                    skipped += 1
                    continue

                # Parse artist/title from filename if not in XML
                if not name:
                    fname = os.path.splitext(basename)[0]
                    parts = fname.split(' - ', 1)
                    artist = artist or (parts[0].strip() if len(parts) > 1 else "")
                    name = parts[1].strip() if len(parts) > 1 else fname.strip()

                self.db.conn.execute("""
                    INSERT OR IGNORE INTO tracks
                    (track_id, title, artist, permalink_url, genre, bpm, musical_key,
                     camelot_key, cues_json, duration_seconds, discovery_source)
                    VALUES (?, ?, ?, '', ?, ?, ?, ?, ?, ?, 'rekordbox')
                """, (track_id, name, artist, genre, bpm, musical_key,
                      camelot_key, cues_json, total_time or 0))

                if file_exists:
                    # Determine genre folder from parent dir name
                    genre_folder = os.path.basename(os.path.dirname(location)) or "rekordbox"
                    file_size = os.path.getsize(location)
                    self.db.conn.execute("""
                        INSERT OR IGNORE INTO downloads
                        (track_id, genre_folder, file_path, file_size_bytes, status, download_method)
                        VALUES (?, ?, ?, ?, 'completed', 'rekordbox')
                    """, (track_id, genre_folder, abs_loc, file_size))

                imported += 1

        self.db.conn.commit()
        return {
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
            "total_in_xml": xml.num_tracks,
        }

    @staticmethod
    def _parse_tonality(tonality: str) -> tuple:
        """Parse Rekordbox Tonality field into (musical_key, camelot_key).
        Handles formats: 'C# minor', '6A', 'Gm', 'G#m', 'Cmaj'."""
        if not tonality:
            return None, None

        tonality = tonality.strip()

        # Already in "X minor/major" format
        if " minor" in tonality or " major" in tonality:
            camelot = to_camelot(tonality)
            return tonality, camelot or None

        # Camelot format: "6A", "11B"
        if len(tonality) <= 3 and tonality[-1:] in ("A", "B"):
            from core.camelot import to_traditional
            musical = to_traditional(tonality)
            return musical or None, tonality

        # Short format: "Gm", "C#m", "Cmaj", "Abm"
        t = tonality
        if t.endswith("maj"):
            key = t[:-3]
            musical = f"{key} major"
        elif t.endswith("m"):
            key = t[:-1]
            musical = f"{key} minor"
        else:
            return None, None

        camelot = to_camelot(musical)
        return musical if camelot else None, camelot or None
