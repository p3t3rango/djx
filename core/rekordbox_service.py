import logging
import os
from typing import List, Optional

from core.database import Database

logger = logging.getLogger(__name__)

# Default Rekordbox DB locations on macOS
_RB_DB_PATHS = [
    os.path.expanduser("~/Library/Pioneer/rekordbox/master.db"),
    os.path.expanduser("~/Library/Application Support/Pioneer/rekordbox/master.db"),
]


def find_rekordbox_db() -> Optional[str]:
    """Auto-detect Rekordbox database location."""
    for path in _RB_DB_PATHS:
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
