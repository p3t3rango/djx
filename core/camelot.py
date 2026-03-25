# Camelot Wheel — harmonic mixing key notation used by Rekordbox, Traktor, Serato

_KEY_TO_CAMELOT = {
    "Ab minor": "1A", "G# minor": "1A",
    "Eb minor": "2A", "D# minor": "2A",
    "Bb minor": "3A", "A# minor": "3A",
    "F minor": "4A",
    "C minor": "5A",
    "G minor": "6A",
    "D minor": "7A",
    "A minor": "8A",
    "E minor": "9A",
    "B minor": "10A",
    "F# minor": "11A", "Gb minor": "11A",
    "Db minor": "12A", "C# minor": "12A",

    "B major": "1B",
    "F# major": "2B", "Gb major": "2B",
    "Db major": "3B", "C# major": "3B",
    "Ab major": "4B", "G# major": "4B",
    "Eb major": "5B", "D# major": "5B",
    "Bb major": "6B", "A# major": "6B",
    "F major": "7B",
    "C major": "8B",
    "G major": "9B",
    "D major": "10B",
    "A major": "11B",
    "E major": "12B",
}

_CAMELOT_TO_KEY = {
    "1A": "Ab minor", "2A": "Eb minor", "3A": "Bb minor", "4A": "F minor",
    "5A": "C minor", "6A": "G minor", "7A": "D minor", "8A": "A minor",
    "9A": "E minor", "10A": "B minor", "11A": "F# minor", "12A": "Db minor",
    "1B": "B major", "2B": "F# major", "3B": "Db major", "4B": "Ab major",
    "5B": "Eb major", "6B": "Bb major", "7B": "F major", "8B": "C major",
    "9B": "G major", "10B": "D major", "11B": "A major", "12B": "E major",
}


def to_camelot(key_string: str) -> str:
    """Convert 'G minor' or 'C major' to Camelot code like '6A' or '8B'."""
    return _KEY_TO_CAMELOT.get(key_string, "")


def to_traditional(camelot_code: str) -> str:
    """Convert '6A' to 'G minor'."""
    return _CAMELOT_TO_KEY.get(camelot_code.upper(), "")


def from_essentia(key: str, scale: str) -> tuple:
    """Convert essentia output (key='G', scale='minor') to (traditional, camelot).
    Returns ('G minor', '6A')."""
    traditional = f"{key} {scale}"
    camelot = to_camelot(traditional)
    return traditional, camelot


def compatible_keys(camelot_code: str) -> list:
    """Return list of Camelot codes that mix well with the given code.
    Compatible: same number different letter, ±1 same letter."""
    code = camelot_code.upper()
    if len(code) < 2:
        return []
    try:
        num = int(code[:-1])
        letter = code[-1]
    except ValueError:
        return []

    other_letter = "B" if letter == "A" else "A"
    prev_num = 12 if num == 1 else num - 1
    next_num = 1 if num == 12 else num + 1

    return [
        f"{num}{other_letter}",
        f"{prev_num}{letter}",
        f"{next_num}{letter}",
    ]
