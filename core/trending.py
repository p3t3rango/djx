import math
from datetime import datetime
from typing import Optional

from core.models import Track


def compute_trending_score(track: Track) -> float:
    age_days = _get_age_days(track.created_at)

    # Plays per day (velocity)
    plays_per_day = track.playback_count / age_days

    # Engagement ratio
    engagement = (track.likes_count + track.repost_count) / max(track.playback_count, 1)

    # Recency boost: exponential decay
    # ~0.81 at 7 days, ~0.41 at 30 days, ~0.05 at 100 days
    recency_multiplier = math.exp(-0.03 * age_days)

    score = (plays_per_day * 0.6 + engagement * 10000 * 0.4) * recency_multiplier
    return round(score, 2)


def _get_age_days(created_at: Optional[str]) -> float:
    if not created_at:
        return 365  # default to 1 year if unknown (penalizes tracks with no date)
    try:
        # Handle various datetime formats from SoundCloud
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ",
                     "%Y/%m/%d %H:%M:%S +0000", "%Y-%m-%d %H:%M:%S+00:00"):
            try:
                dt = datetime.strptime(created_at.strip(), fmt)
                age = (datetime.utcnow() - dt).days
                return max(age, 1)
            except ValueError:
                continue
        # Try parsing just the date portion
        date_str = created_at[:10]
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        age = (datetime.utcnow() - dt).days
        return max(age, 1)
    except Exception:
        return 365
