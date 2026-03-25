GENRES = {
    "house": {
        "display_name": "House",
        "tags": ["house"],
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
}

REMIX_SUFFIXES = ["remix", "bootleg", "edit", "rework"]

TRACKS_PER_GENRE = 50
DOWNLOAD_DIR = "downloads"
MIN_PLAYBACK_COUNT = 1000
MIN_DURATION_SEC = 120   # 2 minutes
MAX_DURATION_SEC = 600   # 10 minutes
API_DELAY = 0.5          # seconds between API calls
MAX_RETRIES = 3
