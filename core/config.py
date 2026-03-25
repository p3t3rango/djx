from typing import Optional
from core.database import Database

GENRES = {
    # Main DJ genres
    "house": {
        "display_name": "House",
        "tags": ["house", "deep house"],
        "search_queries": ["house", "house music", "deep house"],
        "accepted_genres": ["house", "deep house", "dance & edm", "dance"],
        "folder": "house",
    },
    "tech-house": {
        "display_name": "Tech House",
        "tags": ["tech house", "techhouse"],
        "search_queries": ["tech house", "techhouse"],
        "accepted_genres": ["tech house", "techhouse", "house", "dance & edm", "dance", "electronic"],
        "folder": "tech-house",
    },
    "afro-house": {
        "display_name": "Afro House",
        "tags": ["afro house", "afrohouse"],
        "search_queries": ["afro house", "afrohouse", "afro tech"],
        "accepted_genres": ["afro house", "afrohouse", "house", "dance & edm", "dance", "electronic", "afro"],
        "folder": "afro-house",
    },
    "amapiano": {
        "display_name": "Amapiano",
        "tags": ["amapiano"],
        "search_queries": ["amapiano", "amapiano beats"],
        "accepted_genres": ["amapiano", "house", "dance & edm", "dance", "electronic", "afro"],
        "folder": "amapiano",
    },
    "uk-garage": {
        "display_name": "UK Garage",
        "tags": ["uk garage", "ukgarage", "ukg"],
        "search_queries": ["uk garage", "ukg", "2-step garage"],
        "accepted_genres": ["uk garage", "ukgarage", "ukg", "garage", "house", "dance & edm", "dance", "electronic"],
        "folder": "uk-garage",
    },
    # Extended genres
    "techno": {
        "display_name": "Techno",
        "tags": ["techno", "hard techno"],
        "search_queries": ["techno", "hard techno", "minimal techno"],
        "accepted_genres": ["techno", "hard techno", "minimal techno", "electronic", "dance & edm"],
        "folder": "techno",
    },
    "minimal": {
        "display_name": "Minimal / Deep",
        "tags": ["minimal", "minimal house", "minimal techno"],
        "search_queries": ["minimal house", "minimal techno", "deep minimal"],
        "accepted_genres": ["minimal", "minimal techno", "high tech minimal", "high-tech minimal", "deep house", "electronic"],
        "folder": "minimal",
    },
    "disco-funk": {
        "display_name": "Disco / Funk",
        "tags": ["disco", "nu disco", "funk"],
        "search_queries": ["disco house", "nu disco", "disco edits", "funk house"],
        "accepted_genres": ["disco", "funk", "nu disco", "electronic", "dance & edm", "dance"],
        "folder": "disco-funk",
    },
    "drum-and-bass": {
        "display_name": "Drum & Bass",
        "tags": ["drum and bass", "dnb", "drum & bass"],
        "search_queries": ["drum and bass", "dnb", "liquid dnb", "jungle"],
        "accepted_genres": ["drum & bass", "drum and bass", "dnb", "electronic", "dance & edm"],
        "folder": "drum-and-bass",
    },
    "dubstep-bass": {
        "display_name": "Dubstep / Bass",
        "tags": ["dubstep", "bass", "riddim"],
        "search_queries": ["dubstep", "bass music", "riddim", "future bass"],
        "accepted_genres": ["dubstep", "bass", "riddim", "future bass", "electronic", "dance & edm"],
        "folder": "dubstep-bass",
    },
    "trance": {
        "display_name": "Trance",
        "tags": ["trance", "progressive trance"],
        "search_queries": ["trance", "progressive trance", "uplifting trance"],
        "accepted_genres": ["trance", "eurotrance", "electronic", "dance & edm"],
        "folder": "trance",
    },
    "dancehall-reggaeton": {
        "display_name": "Dancehall / Reggaeton",
        "tags": ["dancehall", "reggaeton"],
        "search_queries": ["dancehall", "reggaeton", "moombahton"],
        "accepted_genres": ["dancehall", "reggaeton", "latin", "latin music", "reggae"],
        "folder": "dancehall-reggaeton",
    },
    "hip-hop": {
        "display_name": "Hip-Hop / R&B",
        "tags": ["hip hop", "r&b", "rap"],
        "search_queries": ["hip hop", "r&b", "rap"],
        "accepted_genres": ["hip-hop", "hip hop", "hip-hop & rap", "hip hop/rap", "hip-hop/rap", "rap", "r&b", "r&b & soul"],
        "folder": "hip-hop",
    },
    "jersey-club": {
        "display_name": "Jersey Club",
        "tags": ["jersey club", "jersey"],
        "search_queries": ["jersey club", "jersey club remix"],
        "accepted_genres": ["jersey club", "dance & edm", "electronic", "hip-hop & rap"],
        "folder": "jersey-club",
    },
    "latin-house": {
        "display_name": "Latin House",
        "tags": ["latin house", "tribal house"],
        "search_queries": ["latin house", "tribal house", "brazilian bass"],
        "accepted_genres": ["latin house", "tribal house", "house", "latin", "dance & edm", "electronic"],
        "folder": "latin-house",
    },
}

REMIX_SUFFIXES = ["remix", "bootleg", "edit", "rework", "flip"]

# Defaults (overridable via settings table)
DEFAULTS = {
    "tracks_per_genre": "50",
    "download_dir": "downloads",
    "min_playback_count": "1000",
    "min_duration_sec": "120",
    "max_duration_sec": "600",
    "api_delay": "0.5",
    "trending_recency_days": "30",
}


def get_setting(key: str, db: Optional[Database] = None) -> str:
    if db:
        val = db.get_setting(key)
        if val is not None:
            return val
    return DEFAULTS.get(key, "")


def get_int_setting(key: str, db: Optional[Database] = None) -> int:
    return int(get_setting(key, db))


def get_float_setting(key: str, db: Optional[Database] = None) -> float:
    return float(get_setting(key, db))
