import math
from datetime import datetime
from typing import Optional

from core.models import Track


def compute_trending_score(track: Track) -> float:
    """Trending score — rewards play velocity, engagement, and recency.
    Designed for discovering tracks that are rising fast right now."""
    age_days = _get_age_days(track.created_at)

    # Plays per day (velocity)
    plays_per_day = track.playback_count / age_days

    # Engagement ratio (likes + reposts relative to plays)
    engagement = (track.likes_count + track.repost_count) / max(track.playback_count, 1)

    # Recency boost: softer decay — half-life ~60 days
    # ~0.89 at 7 days, ~0.71 at 30 days, ~0.50 at 60 days, ~0.12 at 180 days
    recency = math.exp(-0.0116 * age_days)

    # Velocity component: log-scaled plays/day (so 10K/day isn't 10000x more than 1/day)
    velocity = math.log10(max(plays_per_day, 1) + 1)

    # Engagement boost (0-1 scale, typical good engagement is 2-5%)
    eng_boost = min(engagement * 20, 1.0)

    score = (velocity * 100 + eng_boost * 50) * (0.3 + 0.7 * recency)
    return round(score, 1)


def compute_popular_score(track: Track) -> float:
    """Popular score — rewards total reach and engagement.
    Age is a very minor factor; a 7M play track always scores high."""
    # Log-scaled play count dominates: 1K=30, 10K=40, 100K=50, 1M=60, 10M=70
    play_score = math.log10(max(track.playback_count, 1) + 1) * 10

    # Engagement as a small bonus (0-15 points)
    engagement = (track.likes_count + track.repost_count) / max(track.playback_count, 1)
    eng_bonus = min(engagement * 200, 15)

    # Very mild recency tiebreaker (not a penalty)
    age_days = _get_age_days(track.created_at)
    recency_tiebreak = 1.0 / (1.0 + age_days / 365)  # 0.5 at 1 year, 0.25 at 3yr

    score = (play_score + eng_bonus) * (0.85 + 0.15 * recency_tiebreak)
    return round(score, 1)


def compute_fresh_score(track: Track) -> float:
    """Fresh score — rewards newness, with plays as a quality signal."""
    age_days = _get_age_days(track.created_at)

    # Freshness: steep decay — designed to highlight this week's tracks
    freshness = math.exp(-0.05 * age_days)

    # Minimum quality bar: log plays as a small boost
    quality = math.log10(max(track.playback_count, 1) + 1)

    score = freshness * 200 + quality * 20
    return round(score, 1)


def _get_age_days(created_at: Optional[str]) -> float:
    if not created_at:
        return 365
    try:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ",
                     "%Y/%m/%d %H:%M:%S +0000", "%Y-%m-%d %H:%M:%S+00:00"):
            try:
                dt = datetime.strptime(created_at.strip(), fmt)
                age = (datetime.utcnow() - dt).days
                return max(age, 1)
            except ValueError:
                continue
        date_str = created_at[:10]
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        age = (datetime.utcnow() - dt).days
        return max(age, 1)
    except Exception:
        return 365
