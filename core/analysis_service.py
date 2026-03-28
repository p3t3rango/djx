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


def _snap_to_downbeat(time_sec: float, beats: List[float]) -> float:
    """Snap a time position to the nearest downbeat (every 4 beats)."""
    if not beats:
        return time_sec

    # Get downbeats (every 4th beat)
    downbeats = beats[::4] if len(beats) > 4 else beats

    # Find closest downbeat
    closest = min(downbeats, key=lambda b: abs(b - time_sec))
    return closest


def generate_auto_cues(audio: np.ndarray, beats: List[float], bpm: float, duration: float) -> List[dict]:
    """Generate 8 hot cue points based on structural analysis.

    Uses energy envelope + spectral flux to detect drops, breakdowns,
    builds, intros, and outros. Snaps to nearest downbeat.
    """
    if duration < 30 or not beats or bpm <= 0:
        return []

    hop_sec = 0.125
    env = _compute_energy_envelope(audio, frame_sec=0.5, hop_sec=hop_sec)

    if len(env) < 10:
        return []

    # Normalize envelope to 0-1
    env_min, env_max = env.min(), env.max()
    if env_max - env_min < 1e-6:
        return []
    env_norm = (env - env_min) / (env_max - env_min)

    # Compute derivative (energy change rate)
    deriv = np.diff(env_norm)

    # Compute time array for each envelope frame
    times = np.arange(len(env_norm)) * hop_sec

    # Minimum distance between cues: 16 beats
    beat_period = 60.0 / bpm
    min_dist = beat_period * 16

    # --- Detect structural points ---
    detected = []  # (time, type, strength)

    # Track regions
    track_25 = duration * 0.25
    track_75 = duration * 0.75

    # Adaptive thresholds based on track dynamics
    deriv_std = float(np.std(deriv)) if len(deriv) > 0 else 0.1
    drop_thresh = max(0.05, deriv_std * 1.5)
    break_thresh = max(0.04, deriv_std * 1.2)

    # 1. Find drops: positive derivative spikes (energy increases)
    for i in range(1, len(deriv) - 1):
        if deriv[i] > drop_thresh and deriv[i] > deriv[i - 1] and deriv[i] > deriv[i + 1]:
            t = times[i]
            detected.append((t, "drop", float(deriv[i])))

    # 2. Find breakdowns: negative derivative dips (energy decreases)
    for i in range(1, len(deriv) - 1):
        if deriv[i] < -break_thresh and deriv[i] < deriv[i - 1] and deriv[i] < deriv[i + 1]:
            t = times[i]
            detected.append((t, "breakdown", float(abs(deriv[i]))))

    # 3. Find builds: sustained rising energy (positive derivative over 4+ seconds)
    window = int(4.0 / hop_sec)
    build_thresh = max(0.01, deriv_std * 0.3)
    for i in range(window, len(deriv)):
        segment = deriv[i - window:i]
        if np.mean(segment) > build_thresh and np.min(segment) > -build_thresh:
            t = times[i - window]
            detected.append((t, "build", float(np.mean(segment))))

    # Sort by strength and deduplicate (min distance)
    detected.sort(key=lambda x: x[2], reverse=True)
    filtered = []
    for t, typ, strength in detected:
        if all(abs(t - ft) > min_dist for ft, _, _ in filtered):
            filtered.append((t, typ, strength))

    # --- Assign 8 cue slots ---
    cues = []

    # Cue 1: INTRO (first downbeat or start)
    intro_time = _snap_to_downbeat(beats[0] if beats else 0, beats)
    cues.append({"name": "INTRO", "type": "cue", "start": round(intro_time, 3), "num": 0})

    # Cue 2: VERSE (first energy rise in first 25%)
    verse_candidates = [(t, s) for t, typ, s in filtered if t < track_25 and typ in ("drop", "build")]
    if verse_candidates:
        verse_t = _snap_to_downbeat(verse_candidates[0][0], beats)
        cues.append({"name": "VERSE", "type": "cue", "start": round(verse_t, 3), "num": 1})

    # Cue 3: BUILD (first build before the biggest drop)
    drops = [(t, s) for t, typ, s in filtered if typ == "drop"]
    builds = [(t, s) for t, typ, s in filtered if typ == "build"]
    if builds:
        # Prefer build closest before the first drop
        if drops:
            pre_drop_builds = [(t, s) for t, s in builds if t < drops[0][0]]
            if pre_drop_builds:
                build_t = _snap_to_downbeat(pre_drop_builds[-1][0], beats)
            else:
                build_t = _snap_to_downbeat(builds[0][0], beats)
        else:
            build_t = _snap_to_downbeat(builds[0][0], beats)
        cues.append({"name": "BUILD", "type": "cue", "start": round(build_t, 3), "num": 2})

    # Cue 4: DROP 1 (biggest drop)
    if drops:
        drop1_t = _snap_to_downbeat(drops[0][0], beats)
        cues.append({"name": "DROP 1", "type": "cue", "start": round(drop1_t, 3), "num": 3})

    # Cue 5: BREAK (first breakdown after drop 1)
    breakdowns = [(t, s) for t, typ, s in filtered if typ == "breakdown"]
    if drops and breakdowns:
        post_drop = [(t, s) for t, s in breakdowns if t > drops[0][0]]
        if post_drop:
            break_t = _snap_to_downbeat(post_drop[0][0], beats)
            cues.append({"name": "BREAK", "type": "cue", "start": round(break_t, 3), "num": 4})

    # Cue 6: DROP 2 (second biggest drop, if exists)
    if len(drops) > 1:
        drop2_t = _snap_to_downbeat(drops[1][0], beats)
        cues.append({"name": "DROP 2", "type": "cue", "start": round(drop2_t, 3), "num": 5})

    # Cue 7: BRIDGE (second breakdown or breakdown in second half)
    if len(breakdowns) > 1:
        bridge_t = _snap_to_downbeat(breakdowns[1][0], beats)
        cues.append({"name": "BRIDGE", "type": "cue", "start": round(bridge_t, 3), "num": 6})

    # Cue 8: OUTRO (energy drop in last 25%)
    outro_candidates = [(t, s) for t, typ, s in filtered if t > track_75 and typ == "breakdown"]
    if outro_candidates:
        outro_t = _snap_to_downbeat(outro_candidates[0][0], beats)
    else:
        # Fallback: 75% of the track
        outro_t = _snap_to_downbeat(duration * 0.75, beats)
    cues.append({"name": "OUTRO", "type": "cue", "start": round(outro_t, 3), "num": 7})

    # Fill empty slots with evenly spaced phrase markers
    used_nums = {c["num"] for c in cues}
    used_times = {c["start"] for c in cues}
    if len(cues) < 8:
        # Divide track into segments and place cues at phrase boundaries
        bar_len = beat_period * 4
        # Try 16-bar phrases first, then 32-bar
        phrase_len = bar_len * 16
        candidate_times = []
        t = phrase_len
        while t < duration * 0.92:
            snap_t = _snap_to_downbeat(t, beats)
            # Don't place too close to existing cues
            if all(abs(snap_t - et) > min_dist * 0.5 for et in used_times):
                candidate_times.append(snap_t)
            t += phrase_len

        for num in range(8):
            if num not in used_nums and len(cues) < 8 and candidate_times:
                snap_t = candidate_times.pop(0)
                used_times.add(snap_t)
                cues.append({
                    "name": CUE_LABELS[num] if num < len(CUE_LABELS) else f"CUE {num + 1}",
                    "type": "cue",
                    "start": round(snap_t, 3),
                    "num": num,
                })

    # Sort by cue number
    cues.sort(key=lambda c: c["num"])
    return cues[:8]


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
