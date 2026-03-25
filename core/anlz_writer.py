"""
Pioneer ANLZ file writer (.DAT, .EXT).
Based on Deep Symmetry's documentation:
https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/anlz.html

All ANLZ values are BIG-ENDIAN (opposite of .pdb).
"""

import struct
from typing import List, Optional


def write_anlz_dat(filepath: str, audio_path: str, bpm: float,
                   beats: List[float], cues: List[dict] = None):
    """Write a .DAT analysis file with path, beat grid, cues, and waveform preview."""
    sections = []

    # PPTH: Path section
    sections.append(_build_ppth(audio_path))

    # PQTZ: Beat grid
    if beats and bpm:
        sections.append(_build_pqtz(bpm, beats))

    # PCOB: Cue points (memory points)
    memory_cues = [c for c in (cues or []) if c.get('type') != 'hot_cue']
    if memory_cues:
        sections.append(_build_pcob(memory_cues, cue_type=0))

    # PCOB: Hot cues
    hot_cues = [c for c in (cues or []) if c.get('type') == 'cue' or c.get('num', -1) >= 0]
    if hot_cues:
        sections.append(_build_pcob(hot_cues, cue_type=1))

    # PWAV: Waveform preview (400 bytes of zeros as placeholder)
    sections.append(_build_pwav())

    # Assemble file
    content = b''
    for section in sections:
        content += section

    # PMAI header
    header_len = 0x1C
    file_len = header_len + len(content)
    header = struct.pack('>4sII', b'PMAI', header_len, file_len)
    header += b'\x00' * (header_len - 12)  # padding

    with open(filepath, 'wb') as f:
        f.write(header)
        f.write(content)


def _build_ppth(path: str) -> bytes:
    """Build PPTH (path) section."""
    # Path as UTF-16 BE with null terminator
    path_bytes = path.encode('utf-16-be') + b'\x00\x00'
    len_path = len(path_bytes)

    header_len = 0x10
    len_tag = header_len + len_path

    section = struct.pack('>4sII', b'PPTH', header_len, len_tag)
    section += struct.pack('>I', len_path)
    section += path_bytes
    return section


def _build_pqtz(bpm: float, beats: List[float]) -> bytes:
    """Build PQTZ (beat grid) section."""
    header_len = 0x18
    num_beats = len(beats)
    tempo = int(bpm * 100)

    # Build beat entries (8 bytes each)
    beat_data = b''
    for i, beat_time in enumerate(beats):
        beat_number = (i % 4) + 1  # 1-4 cycling
        time_ms = int(beat_time * 1000)
        beat_data += struct.pack('>HHI', beat_number, tempo, time_ms)

    len_tag = header_len + len(beat_data)

    section = struct.pack('>4sII', b'PQTZ', header_len, len_tag)
    section += struct.pack('>II', 0, 0x00800000)  # unknown1, unknown2
    section += struct.pack('>I', num_beats)
    section += beat_data
    return section


def _build_pcob(cues: List[dict], cue_type: int = 0) -> bytes:
    """Build PCOB (cue list) section with PCPT entries.
    cue_type: 0 = memory points, 1 = hot cues
    """
    header_len = 0x18

    # Build PCPT entries (0x38 bytes each)
    entries = b''
    for i, cue in enumerate(cues):
        time_ms = int(cue.get('start', 0) * 1000)
        loop_ms = int(cue.get('end', 0) * 1000) if cue.get('end') else 0
        is_loop = 2 if cue.get('type') == 'loop' else 1
        hot_cue_num = cue.get('num', 0) + 1 if cue_type == 1 else 0

        entry = struct.pack('>4sII', b'PCPT', 0x1C, 0x38)
        entry += struct.pack('>I', hot_cue_num)     # hot_cue
        entry += struct.pack('>I', 4 if (is_loop == 2 and loop_ms) else 0)  # status
        entry += struct.pack('>I', 0x00100000)       # unknown1
        entry += struct.pack('>HH', 0xFFFF if i == 0 else i - 1, i + 1)  # order
        entry += struct.pack('>B', is_loop)          # type
        entry += b'\x00\x03\xe8'                     # unknown2
        entry += struct.pack('>I', time_ms)          # time
        entry += struct.pack('>I', loop_ms)          # loop_time
        entry += b'\x00' * 16                        # unknown3
        entries += entry

    len_tag = header_len + len(entries)

    section = struct.pack('>4sII', b'PCOB', header_len, len_tag)
    section += struct.pack('>I', cue_type)           # type
    section += struct.pack('>HH', 0, len(cues))      # unk, lencues
    section += struct.pack('>I', len(cues))           # memory_count
    section += entries
    return section


def _build_pwav() -> bytes:
    """Build PWAV (waveform preview) section — 400 bytes."""
    header_len = 0x14
    preview_len = 400
    len_tag = header_len + preview_len

    section = struct.pack('>4sII', b'PWAV', header_len, len_tag)
    section += struct.pack('>I', preview_len)
    section += struct.pack('>I', 0x00100000)
    # Generate a simple flat waveform as placeholder
    # Each byte: bits 0-4 = height (0-31), bits 5-7 = whiteness
    section += bytes([0x10] * preview_len)  # mid-height, medium white
    return section
