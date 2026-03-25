import json
import logging
import os
from dataclasses import dataclass
from typing import List, Optional, Callable

import essentia.standard as es
from mutagen.id3 import ID3, TBPM, TKEY, ID3NoHeaderError

from core.camelot import from_essentia
from core.database import Database

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    file_path: str
    bpm: float
    bpm_confidence: float
    musical_key: str       # "G minor"
    camelot_key: str       # "6A"
    key_confidence: float
    beats: List[float]     # beat positions in seconds
    success: bool = True
    error: Optional[str] = None


def analyze_track(file_path: str) -> AnalysisResult:
    """Run BPM and key detection on an audio file."""
    try:
        loader = es.MonoLoader(filename=file_path, sampleRate=44100)
        audio = loader()

        # BPM + beats
        rhythm = es.RhythmExtractor2013(method="multifeature")
        bpm, beats, bpm_conf, _, _ = rhythm(audio)

        # Round BPM to nearest integer for DJ use
        bpm = round(bpm, 1)

        # Key
        key, scale, key_strength = es.KeyExtractor()(audio)
        traditional, camelot = from_essentia(key, scale)

        return AnalysisResult(
            file_path=file_path,
            bpm=bpm,
            bpm_confidence=round(bpm_conf, 3),
            musical_key=traditional,
            camelot_key=camelot,
            key_confidence=round(key_strength, 3),
            beats=[round(float(b), 3) for b in beats],
        )
    except Exception as e:
        logger.error(f"Analysis failed for {file_path}: {e}")
        return AnalysisResult(
            file_path=file_path, bpm=0, bpm_confidence=0,
            musical_key="", camelot_key="", key_confidence=0,
            beats=[], success=False, error=str(e),
        )


def write_id3_tags(file_path: str, bpm: float, key: str):
    """Write BPM and key to the MP3 file's ID3 tags."""
    try:
        try:
            tags = ID3(file_path)
        except ID3NoHeaderError:
            tags = ID3()

        tags.add(TBPM(encoding=3, text=[str(int(round(bpm)))]))
        if key:
            tags.add(TKEY(encoding=3, text=[key]))
        tags.save(file_path)
    except Exception as e:
        logger.warning(f"Failed to write ID3 tags for {file_path}: {e}")


class AnalysisService:
    def __init__(self, db: Database):
        self.db = db

    def analyze_and_store(self, track_id: int, file_path: str) -> AnalysisResult:
        """Analyze a single track and store results in DB + ID3 tags."""
        result = analyze_track(file_path)

        if result.success:
            # Write to DB
            self.db.conn.execute("""
                UPDATE tracks SET
                    bpm = ?, musical_key = ?, camelot_key = ?,
                    bpm_confidence = ?, key_confidence = ?,
                    analyzed_at = datetime('now'),
                    beats_json = ?
                WHERE track_id = ?
            """, (
                result.bpm, result.musical_key, result.camelot_key,
                result.bpm_confidence, result.key_confidence,
                json.dumps(result.beats[:100]),  # Store first 100 beats to save space
                track_id,
            ))
            self.db.conn.commit()

            # Write to ID3 tags
            if os.path.exists(file_path):
                write_id3_tags(file_path, result.bpm, result.musical_key)

        return result

    def analyze_batch(self, track_ids_and_paths: List[tuple],
                      on_progress: Optional[Callable] = None) -> dict:
        """Analyze multiple tracks. Each item is (track_id, file_path)."""
        success = 0
        failed = 0
        total = len(track_ids_and_paths)

        for i, (track_id, file_path) in enumerate(track_ids_and_paths):
            if on_progress:
                on_progress(i, total, file_path)

            if not file_path or not os.path.exists(file_path):
                failed += 1
                continue

            result = self.analyze_and_store(track_id, file_path)
            if result.success:
                success += 1
            else:
                failed += 1

        return {"success": success, "failed": failed, "total": total}

    def get_unanalyzed_tracks(self) -> List[dict]:
        """Get tracks that have files but haven't been analyzed."""
        rows = self.db.conn.execute("""
            SELECT t.track_id, d.file_path, t.title, t.artist
            FROM tracks t
            JOIN downloads d ON t.track_id = d.track_id
            WHERE t.bpm IS NULL AND d.file_path IS NOT NULL AND d.status = 'completed'
        """).fetchall()
        return [dict(r) for r in rows]

    def get_analysis_stats(self) -> dict:
        """Get counts of analyzed vs unanalyzed tracks."""
        analyzed = self.db.conn.execute(
            "SELECT COUNT(*) as c FROM tracks WHERE bpm IS NOT NULL"
        ).fetchone()["c"]
        total_with_files = self.db.conn.execute(
            "SELECT COUNT(*) as c FROM downloads WHERE file_path IS NOT NULL AND status = 'completed'"
        ).fetchone()["c"]
        return {
            "analyzed": analyzed,
            "unanalyzed": total_with_files - analyzed,
            "total": total_with_files,
        }
