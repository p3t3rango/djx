import json
import logging
import math
import os
from dataclasses import dataclass, field
from typing import List, Optional, Callable

import numpy as np
import essentia.standard as es
from mutagen.id3 import ID3, TBPM, TKEY, ID3NoHeaderError

from core.camelot import from_essentia
from core.database import Database

logger = logging.getLogger(__name__)

SAMPLE_RATE = 44100

# Hot cue colors (Rekordbox/Serato standard order)
CUE_LABELS = [
    "INTRO", "VERSE", "BUILD", "DROP 1",
    "BREAK", "DROP 2", "BRIDGE", "OUTRO",
]


@dataclass
class AnalysisResult:
    file_path: str
    bpm: float
    bpm_confidence: float
    musical_key: str       # "G minor"
    camelot_key: str       # "6A"
    key_confidence: float
    beats: List[float]     # beat positions in seconds
    energy: int = 0        # 1-10 energy level
    cues: List[dict] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


def _compute_energy(audio: np.ndarray) -> int:
    """Compute track energy on a 1-10 scale (Beatport-style).

    Uses four Essentia features:
    - Loudness (LUFS-like) — overall volume level
    - Onset rate — rhythmic density
    - Dynamic complexity — inverse: less dynamic = punchier
    - Spectral centroid — brightness
    """
    try:
        # Loudness (raw energy, log-scale to dB-like range)
        loudness_raw = float(es.Loudness()(audio))
        # Typical range: 100 (quiet) to 50000 (loud). Log-scale normalize.
        loud_db = 10 * math.log10(max(loudness_raw, 1))  # ~20 to ~47
        loud_norm = min(1.0, max(0.0, (loud_db - 20) / 27))

        # Onset rate (onsets per second) — second element of tuple
        onset_result = es.OnsetRate()(audio)
        onset_rate = float(onset_result[1])  # rate is the second output
        onset_norm = min(1.0, onset_rate / 8.0)

        # Dynamic complexity (0-10, higher = more dynamic = LESS punchy)
        dyn_result = es.DynamicComplexity()(audio)
        dyn_complex = float(dyn_result[0])
        dyn_norm = 1.0 - min(1.0, dyn_complex / 10.0)

        # Weighted blend (3 reliable features)
        score = (
            loud_norm * 0.50 +
            onset_norm * 0.30 +
            dyn_norm * 0.20
        )

        # Map to 1-10
        return max(1, min(10, round(score * 9) + 1))

    except Exception as e:
        logger.warning(f"Energy computation failed: {e}")
        return 5  # Default mid-energy


def _compute_energy_envelope(audio: np.ndarray, frame_sec=0.5, hop_sec=0.125) -> np.ndarray:
    """Compute a smoothed RMS energy envelope for structural analysis."""
    frame_size = int(SAMPLE_RATE * frame_sec)
    hop_size = int(SAMPLE_RATE * hop_sec)

    envelope = []
    rms = es.RMS()
    for i in range(0, len(audio) - frame_size, hop_size):
        envelope.append(rms(audio[i:i + frame_size]))

    env = np.array(envelope, dtype=np.float32)

    # Smooth with a moving average (4-second window)
    kernel_size = int(4.0 / hop_sec)
    if kernel_size > 1 and len(env) > kernel_size:
        kernel = np.ones(kernel_size) / kernel_size
        env = np.convolve(env, kernel, mode='same')

    return env


def _generate_full_beat_grid(bpm: float, duration: float, first_beat: float = 0.0) -> List[float]:
    """Generate a complete beat grid from BPM and duration."""
    if bpm <= 0 or duration <= 0:
        return []
    period = 60.0 / bpm
    beats = []
    t = first_beat
    while t < duration:
        beats.append(round(t, 4))
        t += period
    return beats


def _snap_to_downbeat(time_sec: float, downbeats: List[float]) -> float:
    """Snap a time to the nearest downbeat."""
    if not downbeats:
        return time_sec
    closest = min(downbeats, key=lambda b: abs(b - time_sec))
    return closest


def generate_auto_cues(audio: np.ndarray, beats: List[float], bpm: float, duration: float) -> List[dict]:
    """Generate 8 hot cue points using bar-level energy analysis.

    Places cues on exact downbeats where energy changes sharply:
    - DROP: the first loud bar after a quiet section
    - BREAK: the first quiet bar after a loud section
    - INTRO: first downbeat
    - OUTRO: where energy dies near the end
    """
    if duration < 30 or bpm <= 0:
        return []

    beat_period = 60.0 / bpm
    bar_len = beat_period * 4

    # Generate full beat grid
    first_beat = beats[0] if beats else 0.0
    full_beats = _generate_full_beat_grid(bpm, duration, first_beat)
    if len(full_beats) < 16:
        return []

    # Downbeats (start of each bar)
    downbeats = full_beats[::4]

    # Compute energy per bar
    rms_algo = es.RMS()
    bar_e = []
    for db in downbeats:
        s = int(db * SAMPLE_RATE)
        e = int(min((db + bar_len) * SAMPLE_RATE, len(audio)))
        if e - s < 1000:
            bar_e.append(0.0)
            continue
        bar_e.append(float(rms_algo(audio[s:e])))

    if not bar_e:
        return []

    bar_e = np.array(bar_e)
    e_max = bar_e.max()
    if e_max < 1e-8:
        return []
    bar_e = bar_e / e_max

    # Bar-to-bar energy changes
    diffs = np.diff(bar_e)

    # Adaptive threshold: use the standard deviation of energy changes
    diff_std = float(np.std(diffs)) if len(diffs) > 0 else 0.1
    rise_thresh = max(0.15, diff_std * 2.0)  # Significant energy rise
    fall_thresh = max(0.15, diff_std * 2.0)  # Significant energy fall

    # Find DROPS: bars where energy rises significantly
    # Cue goes on the bar that IS loud (the arrival)
    drops = []
    for i in range(len(diffs)):
        if diffs[i] > rise_thresh:
            drops.append((i + 1, float(diffs[i])))

    # Find BREAKS: bars where energy falls significantly
    # Cue goes on the bar that IS quiet (the drop-off)
    breaks = []
    for i in range(len(diffs)):
        if diffs[i] < -fall_thresh:
            breaks.append((i + 1, float(abs(diffs[i]))))

    # Sort by strength
    drops.sort(key=lambda x: x[1], reverse=True)
    breaks.sort(key=lambda x: x[1], reverse=True)

    # Build candidates with minimum spacing of 8 bars
    min_bars = 8
    candidates = []

    # INTRO: always bar 0
    candidates.append((0, "INTRO", 1.0))

    # Add drops (strongest first)
    for bar_idx, strength in drops:
        if bar_idx < len(downbeats) and all(abs(bar_idx - c[0]) >= min_bars for c in candidates):
            candidates.append((bar_idx, "DROP", strength))

    # Add breaks (strongest first)
    for bar_idx, strength in breaks:
        if bar_idx < len(downbeats) and all(abs(bar_idx - c[0]) >= min_bars for c in candidates):
            candidates.append((bar_idx, "BREAK", strength))

    # OUTRO: find where energy dies near the end
    for i in range(len(bar_e) - 1, max(0, len(bar_e) - 10), -1):
        if bar_e[i] < 0.15 and i > 0 and bar_e[i - 1] > 0.3:
            if all(abs(i - c[0]) >= min_bars for c in candidates):
                candidates.append((i, "OUTRO", 0.5))
            break

    # Fill remaining slots with 16-bar phrase boundaries
    if len(candidates) < 8:
        for bar_idx in range(16, len(downbeats) - 4, 16):
            if all(abs(bar_idx - c[0]) >= min_bars for c in candidates):
                candidates.append((bar_idx, "CUE", 0.1))

    # Sort by time, take top 8
    candidates.sort(key=lambda x: x[0])
    candidates = candidates[:8]

    # Assign labels with counting
    drop_n = 0
    break_n = 0
    cues = []
    for i, (bar_idx, label, _) in enumerate(candidates):
        t = downbeats[bar_idx] if bar_idx < len(downbeats) else duration * 0.9
        name = label
        if label == "DROP":
            drop_n += 1
            name = f"DROP {drop_n}" if drop_n > 1 else "DROP"
        elif label == "BREAK":
            break_n += 1
            name = f"BREAK {break_n}" if break_n > 1 else "BREAK"

        cues.append({
            "name": name,
            "type": "cue",
            "start": round(t, 3),
            "num": i,
            "end": None,
        })

    return cues


def analyze_track(file_path: str) -> AnalysisResult:
    """Run BPM, key, energy, and cue detection on an audio file."""
    try:
        loader = es.MonoLoader(filename=file_path, sampleRate=SAMPLE_RATE)
        audio = loader()

        # BPM + beats
        rhythm = es.RhythmExtractor2013(method="multifeature")
        bpm, beats, bpm_conf, _, _ = rhythm(audio)
        bpm = round(bpm, 1)

        # Key
        key, scale, key_strength = es.KeyExtractor()(audio)
        traditional, camelot = from_essentia(key, scale)

        # Energy (1-10)
        energy = _compute_energy(audio)

        # Auto cue points (use full beats before truncation)
        duration = len(audio) / SAMPLE_RATE
        all_beats = [round(float(b), 3) for b in beats]
        cues = generate_auto_cues(audio, all_beats, bpm, duration)

        return AnalysisResult(
            file_path=file_path,
            bpm=bpm,
            bpm_confidence=round(bpm_conf, 3),
            musical_key=traditional,
            camelot_key=camelot,
            key_confidence=round(key_strength, 3),
            beats=all_beats,
            energy=energy,
            cues=cues,
        )
    except Exception as e:
        logger.error(f"Analysis failed for {file_path}: {e}")
        return AnalysisResult(
            file_path=file_path, bpm=0, bpm_confidence=0,
            musical_key="", camelot_key="", key_confidence=0,
            beats=[], energy=0, cues=[], success=False, error=str(e),
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

    def analyze_and_store(self, track_id: int, file_path: str, force: bool = False) -> AnalysisResult:
        """Analyze a single track and store results in DB + ID3 tags.

        If force=True, re-analyzes even if already analyzed.
        Only writes cues when cues_json is NULL (preserves user/Rekordbox cues).
        """
        if not force:
            existing = self.db.conn.execute(
                "SELECT bpm FROM tracks WHERE track_id = ? AND bpm IS NOT NULL", (track_id,)
            ).fetchone()
            if existing:
                return AnalysisResult(
                    file_path=file_path, bpm=existing["bpm"], bpm_confidence=0,
                    musical_key="", camelot_key="", key_confidence=0,
                    beats=[], energy=0, success=True, error="already analyzed"
                )

        result = analyze_track(file_path)

        if result.success:
            # Write BPM, key, energy to DB
            self.db.conn.execute("""
                UPDATE tracks SET
                    bpm = ?, musical_key = ?, camelot_key = ?,
                    bpm_confidence = ?, key_confidence = ?,
                    energy = ?,
                    analyzed_at = datetime('now'),
                    beats_json = ?
                WHERE track_id = ?
            """, (
                result.bpm, result.musical_key, result.camelot_key,
                result.bpm_confidence, result.key_confidence,
                result.energy,
                json.dumps(result.beats[:100]),  # Store first 100 beats to save space
                track_id,
            ))

            # Write cues only if none exist (don't overwrite Rekordbox/manual cues)
            if result.cues:
                self.db.conn.execute("""
                    UPDATE tracks SET cues_json = ?
                    WHERE track_id = ? AND (cues_json IS NULL OR cues_json = '' OR cues_json = '[]')
                """, (json.dumps(result.cues), track_id))

            self.db.conn.commit()

            # Write to ID3 tags
            if os.path.exists(file_path):
                write_id3_tags(file_path, result.bpm, result.musical_key)

        return result

    def generate_cues_for_track(self, track_id: int) -> List[dict]:
        """Explicitly generate auto cues for a track (overwrites existing)."""
        row = self.db.conn.execute("""
            SELECT d.file_path, t.bpm, t.beats_json
            FROM downloads d
            JOIN tracks t ON d.track_id = t.track_id
            WHERE d.track_id = ? AND d.file_path IS NOT NULL
        """, (track_id,)).fetchone()

        if not row or not row["file_path"] or not os.path.exists(row["file_path"]):
            return []

        # Load audio
        audio = es.MonoLoader(filename=row["file_path"], sampleRate=SAMPLE_RATE)()
        duration = len(audio) / SAMPLE_RATE

        # Get beats — prefer stored, recompute if needed
        beats = json.loads(row["beats_json"]) if row["beats_json"] else []
        bpm = row["bpm"] or 0

        if not beats or bpm <= 0:
            # Recompute beats
            rhythm = es.RhythmExtractor2013(method="multifeature")
            bpm, beat_arr, _, _, _ = rhythm(audio)
            beats = [round(float(b), 3) for b in beat_arr]

        cues = generate_auto_cues(audio, beats, bpm, duration)

        # Save (overwrite — user explicitly requested)
        if cues:
            self.db.conn.execute(
                "UPDATE tracks SET cues_json = ? WHERE track_id = ?",
                (json.dumps(cues), track_id)
            )
            self.db.conn.commit()

        return cues

    def analyze_batch(self, track_ids_and_paths: List[tuple],
                      on_progress: Optional[Callable] = None,
                      force: bool = False) -> dict:
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

            result = self.analyze_and_store(track_id, file_path, force=force)
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

    def get_all_tracks_with_files(self) -> List[dict]:
        """Get all tracks that have files (for re-analysis)."""
        rows = self.db.conn.execute("""
            SELECT t.track_id, d.file_path, t.title, t.artist
            FROM tracks t
            JOIN downloads d ON t.track_id = d.track_id
            WHERE d.file_path IS NOT NULL AND d.status = 'completed'
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
        with_energy = self.db.conn.execute(
            "SELECT COUNT(*) as c FROM tracks WHERE energy IS NOT NULL"
        ).fetchone()["c"]
        with_cues = self.db.conn.execute(
            "SELECT COUNT(*) as c FROM tracks WHERE cues_json IS NOT NULL AND cues_json != '[]'"
        ).fetchone()["c"]
        return {
            "analyzed": analyzed,
            "unanalyzed": total_with_files - analyzed,
            "total": total_with_files,
            "with_energy": with_energy,
            "with_cues": with_cues,
        }
