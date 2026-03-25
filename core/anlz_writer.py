"""
Pioneer ANLZ file writer (.DAT, .EXT).
Based on Deep Symmetry's documentation:
https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/anlz.html

All ANLZ values are BIG-ENDIAN (opposite of .pdb).
"""

import struct
from typing import List, Optional


def write_anlz_dat(filepath: str, audio_path: str, bpm: float,
                   beats: List[float], cues: List[dict] = None,
                   waveform_data: dict = None):
    """Write a .DAT analysis file with path, beat grid, cues, and waveform."""
    sections = []

    # PPTH: Path section
    sections.append(_build_ppth(audio_path))

    # PQTZ: Beat grid
    if beats and bpm:
        sections.append(_build_pqtz(bpm, beats))

    # PCOB: Cue points (memory points)
    all_cues = cues or []
    if all_cues:
        sections.append(_build_pcob(all_cues, cue_type=1))  # hot cues

    # PWAV: Waveform preview (400 bytes)
    if waveform_data and 'amplitudes' in waveform_data:
        sections.append(_build_pwav_from_data(waveform_data))
    else:
        sections.append(_build_pwav_placeholder())

    # Assemble file
    content = b''
    for section in sections:
        content += section

    # PMAI header
    header_len = 0x1C
    file_len = header_len + len(content)
    header = struct.pack('>4sII', b'PMAI', header_len, file_len)
    header += b'\x00' * (header_len - 12)

    with open(filepath, 'wb') as f:
        f.write(header)
        f.write(content)


def write_anlz_ext(filepath: str, waveform_data: dict = None, duration: float = 0):
    """Write a .EXT analysis file with color waveform data."""
    sections = []

    if waveform_data and 'lows' in waveform_data:
        # PWV4: Color waveform preview (1200 entries × 6 bytes = 7200 bytes)
        sections.append(_build_pwv4(waveform_data))

        # PWV5: Color waveform detail (150 entries/sec × 2 bytes)
        sections.append(_build_pwv5(waveform_data, duration))

    if not sections:
        return  # Don't write empty EXT file

    content = b''
    for section in sections:
        content += section

    header_len = 0x1C
    file_len = header_len + len(content)
    header = struct.pack('>4sII', b'PMAI', header_len, file_len)
    header += b'\x00' * (header_len - 12)

    with open(filepath, 'wb') as f:
        f.write(header)
        f.write(content)


def _build_ppth(path: str) -> bytes:
    """Build PPTH (path) section."""
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

    beat_data = b''
    for i, beat_time in enumerate(beats):
        beat_number = (i % 4) + 1
        time_ms = int(beat_time * 1000)
        beat_data += struct.pack('>HHI', beat_number, tempo, time_ms)

    len_tag = header_len + len(beat_data)

    section = struct.pack('>4sII', b'PQTZ', header_len, len_tag)
    section += struct.pack('>II', 0, 0x00800000)
    section += struct.pack('>I', num_beats)
    section += beat_data
    return section


def _build_pcob(cues: List[dict], cue_type: int = 0) -> bytes:
    """Build PCOB (cue list) section with PCPT entries."""
    header_len = 0x18

    entries = b''
    for i, cue in enumerate(cues):
        time_ms = int(cue.get('start', 0) * 1000)
        loop_ms = int(cue.get('end', 0) * 1000) if cue.get('end') else 0
        is_loop = 2 if cue.get('type') == 'loop' else 1
        hot_cue_num = cue.get('num', 0) + 1 if cue_type == 1 else 0

        entry = struct.pack('>4sII', b'PCPT', 0x1C, 0x38)
        entry += struct.pack('>I', hot_cue_num)
        entry += struct.pack('>I', 4 if (is_loop == 2 and loop_ms) else 0)
        entry += struct.pack('>I', 0x00100000)
        entry += struct.pack('>HH', 0xFFFF if i == 0 else i - 1, i + 1)
        entry += struct.pack('>B', is_loop)
        entry += b'\x00\x03\xe8'
        entry += struct.pack('>I', time_ms)
        entry += struct.pack('>I', loop_ms)
        entry += b'\x00' * 16
        entries += entry

    len_tag = header_len + len(entries)

    section = struct.pack('>4sII', b'PCOB', header_len, len_tag)
    section += struct.pack('>I', cue_type)
    section += struct.pack('>HH', 0, len(cues))
    section += struct.pack('>I', len(cues))
    section += entries
    return section


def _build_pwav_placeholder() -> bytes:
    """Build PWAV with placeholder data."""
    header_len = 0x14
    preview_len = 400
    len_tag = header_len + preview_len

    section = struct.pack('>4sII', b'PWAV', header_len, len_tag)
    section += struct.pack('>I', preview_len)
    section += struct.pack('>I', 0x00100000)
    section += bytes([0x10] * preview_len)
    return section


def _build_pwav_from_data(waveform: dict) -> bytes:
    """Build PWAV from real waveform data — 400 byte monochrome preview."""
    amplitudes = waveform.get('amplitudes', [])
    highs = waveform.get('highs', [])

    # Resample to 400 points
    preview = bytearray(400)
    src_len = len(amplitudes)
    for i in range(400):
        src_idx = int(i * src_len / 400) if src_len > 0 else 0
        if src_idx < src_len:
            amp = amplitudes[src_idx]
            h = highs[src_idx] if src_idx < len(highs) else 0
            height = min(31, int(amp * 31))
            whiteness = min(7, int(h * 7))
            preview[i] = (whiteness << 5) | height
        else:
            preview[i] = 0

    header_len = 0x14
    len_tag = header_len + 400

    section = struct.pack('>4sII', b'PWAV', header_len, len_tag)
    section += struct.pack('>I', 400)
    section += struct.pack('>I', 0x00100000)
    section += bytes(preview)
    return section


def _build_pwv4(waveform: dict) -> bytes:
    """Build PWV4 — color waveform preview (1200 entries × 6 bytes = 7200 bytes).
    Goes in .EXT file. Used by Nexus 2+ and rekordbox."""
    lows = waveform.get('lows', [])
    mids = waveform.get('mids', [])
    highs = waveform.get('highs', [])
    amplitudes = waveform.get('amplitudes', [])
    src_len = len(amplitudes)

    # 1200 entries, 6 bytes each
    num_entries = 1200
    entry_bytes = 6
    data = bytearray(num_entries * entry_bytes)

    for i in range(num_entries):
        src_idx = int(i * src_len / num_entries) if src_len > 0 else 0
        if src_idx < src_len:
            low = lows[src_idx] if src_idx < len(lows) else 0
            mid = mids[src_idx] if src_idx < len(mids) else 0
            high = highs[src_idx] if src_idx < len(highs) else 0
            amp = amplitudes[src_idx]

            # 6-byte color entry: red_height, red_whiteness, green_height, green_whiteness, blue_height, blue_whiteness
            r_h = min(31, int(high * amp * 31))
            g_h = min(31, int(mid * amp * 31))
            b_h = min(31, int(low * amp * 31))
            r_w = min(7, int(high * 7))
            g_w = min(7, int(mid * 7))
            b_w = min(7, int(low * 7))

            base = i * entry_bytes
            data[base] = r_h
            data[base + 1] = r_w
            data[base + 2] = g_h
            data[base + 3] = g_w
            data[base + 4] = b_h
            data[base + 5] = b_w

    header_len = 0x18
    len_tag = header_len + len(data)

    section = struct.pack('>4sII', b'PWV4', header_len, len_tag)
    section += struct.pack('>I', entry_bytes)
    section += struct.pack('>I', num_entries)
    section += struct.pack('>I', 0)
    section += bytes(data)
    return section


def _build_pwv5(waveform: dict, duration: float) -> bytes:
    """Build PWV5 — color waveform detail (150 entries/sec × 2 bytes).
    Goes in .EXT file. Nexus 2+ scrolling waveform.

    2-byte entry (big-endian):
    bits 15-13: red (0-7)
    bits 12-10: green (0-7)
    bits 9-7:   blue (0-7)
    bits 6-2:   height (0-31)
    bits 1-0:   unused
    """
    lows = waveform.get('lows', [])
    mids = waveform.get('mids', [])
    highs = waveform.get('highs', [])
    amplitudes = waveform.get('amplitudes', [])
    src_len = len(amplitudes)

    num_entries = max(int(duration * 150), 1) if duration else src_len
    entry_bytes = 2
    data = bytearray(num_entries * entry_bytes)

    for i in range(num_entries):
        src_idx = int(i * src_len / num_entries) if src_len > 0 else 0
        if src_idx < src_len:
            low = lows[src_idx] if src_idx < len(lows) else 0
            mid = mids[src_idx] if src_idx < len(mids) else 0
            high = highs[src_idx] if src_idx < len(highs) else 0
            amp = amplitudes[src_idx]

            r = min(7, int(high * 7))
            g = min(7, int(mid * 7))
            b = min(7, int(low * 7))
            height = min(31, int(amp * 31))

            val = (r << 13) | (g << 10) | (b << 7) | (height << 2)
            struct.pack_into('>H', data, i * 2, val)

    header_len = 0x18
    len_tag = header_len + len(data)

    section = struct.pack('>4sII', b'PWV5', header_len, len_tag)
    section += struct.pack('>I', entry_bytes)
    section += struct.pack('>I', num_entries)
    section += struct.pack('>I', 0x00960305)
    section += bytes(data)
    return section
