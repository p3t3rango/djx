import logging
import numpy as np
from typing import List, Optional

logger = logging.getLogger(__name__)


def generate_waveform(file_path: str, num_points: int = 4000) -> dict:
    """Generate high-resolution waveform with frequency-separated color data.

    Uses STFT with high hop resolution for Serato-quality detail.
    Returns per-column peak amplitudes (not mean) for sharper transients.
    """
    try:
        import librosa

        # Load at full quality
        y, sr = librosa.load(file_path, sr=22050, mono=True)
        duration = len(y) / sr

        # Calculate hop length for desired resolution
        # Target: num_points columns for the whole track
        hop_length = max(1, len(y) // num_points)

        # STFT with 2048 FFT, hop_length controls column density
        S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop_length))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)

        # Frequency band masks (Serato standard ranges)
        low_mask = freqs < 200       # Sub-bass + bass
        mid_mask = (freqs >= 200) & (freqs < 3000)  # Mids
        high_mask = freqs >= 3000    # Highs + presence

        actual_points = min(num_points, S.shape[1])

        # Use peak amplitude per column (not mean) for sharper transients
        amplitudes = np.zeros(actual_points)
        lows = np.zeros(actual_points)
        mids = np.zeros(actual_points)
        highs = np.zeros(actual_points)

        for i in range(actual_points):
            col = S[:, i]
            amplitudes[i] = np.max(col)
            lows[i] = np.max(col[low_mask]) if np.any(low_mask) else 0
            mids[i] = np.max(col[mid_mask]) if np.any(mid_mask) else 0
            highs[i] = np.max(col[high_mask]) if np.any(high_mask) else 0

        # Normalize each band to 0-1
        for arr in [amplitudes, lows, mids, highs]:
            mx = arr.max()
            if mx > 0:
                arr /= mx

        return {
            "amplitudes": [round(float(a), 3) for a in amplitudes],
            "lows": [round(float(l), 3) for l in lows],
            "mids": [round(float(m), 3) for m in mids],
            "highs": [round(float(h), 3) for h in highs],
            "duration": round(duration, 2),
            "sample_rate": sr,
            "num_points": actual_points,
        }
    except Exception as e:
        logger.error(f"Waveform generation failed for {file_path}: {e}")
        return {"error": str(e)}
