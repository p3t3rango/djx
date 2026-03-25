import json
import logging
import numpy as np
from typing import List, Optional

logger = logging.getLogger(__name__)


def generate_waveform(file_path: str, num_points: int = 800) -> dict:
    """Generate waveform amplitude data and frequency color data for visualization."""
    try:
        import librosa

        # Load audio
        y, sr = librosa.load(file_path, sr=22050, mono=True)
        duration = len(y) / sr

        # Downsample to num_points
        samples_per_point = len(y) // num_points
        if samples_per_point < 1:
            samples_per_point = 1

        amplitudes = []
        # Also compute spectral centroid for frequency coloring
        lows = []
        mids = []
        highs = []

        # Compute STFT for frequency bands
        S = np.abs(librosa.stft(y, n_fft=2048, hop_length=samples_per_point))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)

        # Frequency band boundaries
        low_mask = freqs < 250
        mid_mask = (freqs >= 250) & (freqs < 4000)
        high_mask = freqs >= 4000

        for i in range(min(num_points, S.shape[1])):
            col = S[:, i]
            amplitudes.append(float(np.mean(col)))
            lows.append(float(np.mean(col[low_mask])) if np.any(low_mask) else 0)
            mids.append(float(np.mean(col[mid_mask])) if np.any(mid_mask) else 0)
            highs.append(float(np.mean(col[high_mask])) if np.any(high_mask) else 0)

        # Normalize to 0-1 range
        max_amp = max(amplitudes) if amplitudes else 1
        if max_amp > 0:
            amplitudes = [a / max_amp for a in amplitudes]
            max_low = max(lows) if lows else 1
            max_mid = max(mids) if mids else 1
            max_high = max(highs) if highs else 1
            lows = [l / max_low if max_low > 0 else 0 for l in lows]
            mids = [m / max_mid if max_mid > 0 else 0 for m in mids]
            highs = [h / max_high if max_high > 0 else 0 for h in highs]

        return {
            "amplitudes": [round(a, 3) for a in amplitudes],
            "lows": [round(l, 3) for l in lows],
            "mids": [round(m, 3) for m in mids],
            "highs": [round(h, 3) for h in highs],
            "duration": round(duration, 2),
            "sample_rate": sr,
            "num_points": len(amplitudes),
        }
    except Exception as e:
        logger.error(f"Waveform generation failed for {file_path}: {e}")
        return {"error": str(e)}
