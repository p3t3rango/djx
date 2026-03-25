"""
Pioneer .pdb database writer.
Based on Deep Symmetry's reverse-engineered documentation:
https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/exports.html

All values are little-endian unless noted otherwise.
"""

import struct
import io
from typing import List, Dict, Optional


PAGE_SIZE = 4096

# Table type IDs
TABLE_TRACKS = 0x00
TABLE_GENRES = 0x01
TABLE_ARTISTS = 0x02
TABLE_ALBUMS = 0x03
TABLE_KEYS = 0x05
TABLE_PLAYLIST_TREE = 0x07
TABLE_PLAYLIST_ENTRIES = 0x08


def _encode_devicesql_string(s: str) -> bytes:
    """Encode a string in DeviceSQL format."""
    if not s:
        s = ""
    data = s.encode('utf-8')
    total_len = len(data) + 4  # 4-byte header
    # Long string format: flags byte + 2-byte length + pad byte + data
    # flags: 0x40 = ASCII
    header = struct.pack('<BBH', 0x40, 0x00, total_len)
    return header + data


def _encode_devicesql_string_utf16(s: str) -> bytes:
    """Encode a string in UTF-16LE DeviceSQL format (used for paths)."""
    if not s:
        s = ""
    data = s.encode('utf-16-le') + b'\x00\x00'
    total_len = len(data) + 4
    header = struct.pack('<BBH', 0x90, 0x00, total_len)
    return header + data


class PdbWriter:
    def __init__(self):
        self.pages: List[bytes] = []
        self.tables: Dict[int, dict] = {}  # type -> {first_page, last_page, rows}

    def add_track(self, track_id: int, title: str, artist_id: int, genre_id: int,
                  key_id: int, bpm: float, duration: int, file_path: str,
                  filename: str, bitrate: int = 320000, sample_rate: int = 44100,
                  file_size: int = 0, file_type: int = 0x01, rating: int = 0,
                  year: int = 0, analyze_path: str = "", date_added: str = "",
                  comment: str = ""):
        """Add a track row."""
        if TABLE_TRACKS not in self.tables:
            self.tables[TABLE_TRACKS] = {"rows": []}

        # Build string data
        strings = [""] * 21  # 21 string slots
        strings[10] = date_added      # date_added
        strings[14] = analyze_path    # analyze_path
        strings[16] = comment         # comment
        strings[17] = title           # title
        strings[19] = filename        # filename
        strings[20] = file_path       # file_path

        # Encode all strings
        encoded_strings = [_encode_devicesql_string(s) for s in strings]

        # Fixed portion of track row: 0x5E bytes + 21 string offsets (2 bytes each) = 0x5E + 42 = 0x88
        tempo = int(bpm * 100)

        # Calculate string offsets relative to row start
        string_data_start = 0x5E + 42  # after fixed fields + offset table
        offsets = []
        current_offset = string_data_start
        for es in encoded_strings:
            offsets.append(current_offset)
            current_offset += len(es)

        # Build fixed portion
        fixed = struct.pack('<HHI',
            0x0024,     # subtype
            0x0000,     # index_shift
            0x00000000, # bitmask
        )
        fixed += struct.pack('<I', sample_rate)
        fixed += struct.pack('<I', 0)           # composer_id
        fixed += struct.pack('<I', file_size)
        fixed += struct.pack('<I', 0)           # u2
        fixed += struct.pack('<HH', 0, 0)       # u3, u4
        fixed += struct.pack('<I', 0)           # artwork_id
        fixed += struct.pack('<I', key_id)
        fixed += struct.pack('<I', 0)           # original_artist_id
        fixed += struct.pack('<I', 0)           # label_id
        fixed += struct.pack('<I', 0)           # remixer_id
        fixed += struct.pack('<I', bitrate)
        fixed += struct.pack('<I', 0)           # track_number
        fixed += struct.pack('<I', tempo)
        fixed += struct.pack('<I', genre_id)
        fixed += struct.pack('<I', 0)           # album_id
        fixed += struct.pack('<I', artist_id)
        fixed += struct.pack('<I', track_id)
        fixed += struct.pack('<HH', 0, 0)       # disc_number, play_count
        fixed += struct.pack('<HH', year, 16)   # year, sample_depth
        fixed += struct.pack('<H', duration)
        fixed += struct.pack('<H', 0)           # u5
        fixed += struct.pack('<BBI', 0, rating, 0)  # color_id, rating, padding
        # Actually file_type is u16 then u7 is u16
        # Let me repack the end correctly
        # From offset 0x58: color_id(1), rating(1), file_type(2), u7(2)
        # Then 21 string offsets

        # Rebuild the end section properly
        row = bytearray()
        row += struct.pack('<HH', 0x0024, 0x0000)  # subtype, index_shift
        row += struct.pack('<I', 0)                  # bitmask
        row += struct.pack('<I', sample_rate)
        row += struct.pack('<I', 0)                  # composer_id
        row += struct.pack('<I', file_size)
        row += struct.pack('<I', 0)                  # u2
        row += struct.pack('<HH', 0, 0)              # u3, u4
        row += struct.pack('<I', 0)                  # artwork_id
        row += struct.pack('<I', key_id)
        row += struct.pack('<I', 0)                  # original_artist_id
        row += struct.pack('<I', 0)                  # label_id
        row += struct.pack('<I', 0)                  # remixer_id
        row += struct.pack('<I', bitrate)
        row += struct.pack('<I', 0)                  # track_number
        row += struct.pack('<I', tempo)
        row += struct.pack('<I', genre_id)
        row += struct.pack('<I', 0)                  # album_id
        row += struct.pack('<I', artist_id)
        row += struct.pack('<I', track_id)
        row += struct.pack('<HH', 0, 0)              # disc_number, play_count
        row += struct.pack('<HH', year, 16)           # year, sample_depth
        row += struct.pack('<H', duration)
        row += struct.pack('<H', 29)                  # u5
        row += struct.pack('<B', 0)                   # color_id
        row += struct.pack('<B', rating)
        row += struct.pack('<H', file_type)           # file_type
        row += struct.pack('<H', 0x0003)              # u7

        # String offsets (21 × u16)
        for ofs in offsets:
            row += struct.pack('<H', ofs)

        # String data
        for es in encoded_strings:
            row += es

        self.tables[TABLE_TRACKS]["rows"].append(bytes(row))

    def add_artist(self, artist_id: int, name: str):
        if TABLE_ARTISTS not in self.tables:
            self.tables[TABLE_ARTISTS] = {"rows": []}

        name_bytes = _encode_devicesql_string(name)
        # Use subtype 0x0064 (long name, 16-bit offset)
        row = struct.pack('<HHI', 0x0064, 0x0000, artist_id)
        row += struct.pack('<HH', 0x0003, 10)  # magic, offset to name
        row += name_bytes
        self.tables[TABLE_ARTISTS]["rows"].append(row)

    def add_genre(self, genre_id: int, name: str):
        if TABLE_GENRES not in self.tables:
            self.tables[TABLE_GENRES] = {"rows": []}

        name_bytes = _encode_devicesql_string(name)
        row = struct.pack('<I', genre_id) + name_bytes
        self.tables[TABLE_GENRES]["rows"].append(row)

    def add_key(self, key_id: int, name: str):
        if TABLE_KEYS not in self.tables:
            self.tables[TABLE_KEYS] = {"rows": []}

        name_bytes = _encode_devicesql_string(name)
        row = struct.pack('<II', key_id, key_id) + name_bytes
        self.tables[TABLE_KEYS]["rows"].append(row)

    def add_playlist(self, playlist_id: int, name: str, parent_id: int = 0,
                     is_folder: bool = False, sort_order: int = 0):
        if TABLE_PLAYLIST_TREE not in self.tables:
            self.tables[TABLE_PLAYLIST_TREE] = {"rows": []}

        name_bytes = _encode_devicesql_string(name)
        row = struct.pack('<IIII', parent_id, 0, sort_order, playlist_id)
        row += struct.pack('<I', 1 if is_folder else 0)
        row += name_bytes
        self.tables[TABLE_PLAYLIST_TREE]["rows"].append(row)

    def add_playlist_entry(self, entry_index: int, track_id: int, playlist_id: int):
        if TABLE_PLAYLIST_ENTRIES not in self.tables:
            self.tables[TABLE_PLAYLIST_ENTRIES] = {"rows": []}

        row = struct.pack('<III', entry_index, track_id, playlist_id)
        self.tables[TABLE_PLAYLIST_ENTRIES]["rows"].append(row)

    def _build_data_page(self, table_type: int, page_index: int, next_page: int,
                         rows: List[bytes], seq: int = 1) -> bytes:
        """Build a single data page with rows."""
        page = bytearray(PAGE_SIZE)

        # Common page header (0x00 - 0x1F)
        struct.pack_into('<I', page, 0x00, 0)            # padding
        struct.pack_into('<I', page, 0x04, page_index)
        struct.pack_into('<I', page, 0x08, table_type)
        struct.pack_into('<I', page, 0x0C, next_page)
        struct.pack_into('<I', page, 0x10, seq)          # seqpage
        struct.pack_into('<I', page, 0x14, 0)            # unknown

        num_rows = len(rows)
        # Row counts: bits 0-12 = num_row_offsets, bits 13-23 = num_rows (packed into 3 bytes)
        row_counts = (num_rows & 0x1FFF) | ((num_rows & 0x7FF) << 13)
        page[0x18] = row_counts & 0xFF
        page[0x19] = (row_counts >> 8) & 0xFF
        page[0x1A] = (row_counts >> 16) & 0xFF

        page[0x1B] = 0x24  # page_flags: data page

        # Data page extension
        struct.pack_into('<HH', page, 0x20, 0, 0)  # transaction fields
        struct.pack_into('<HH', page, 0x24, 0, 0)  # u6, u7

        # Write rows into heap starting at 0x28
        heap_pos = 0x28
        row_offsets = []
        for row_data in rows:
            row_offsets.append(heap_pos - 0x28)  # offset relative to end of page header
            end = heap_pos + len(row_data)
            if end > PAGE_SIZE - 40:  # leave room for row index at end
                break
            page[heap_pos:end] = row_data
            heap_pos = end

        used = heap_pos - 0x28
        free = PAGE_SIZE - heap_pos - (len(row_offsets) * 2 + 4)  # account for row index
        struct.pack_into('<HH', page, 0x1C, max(free, 0), used)

        # Write row index at end of page (grows backward)
        # Row presence flags (2 bytes) + row offsets (2 bytes each)
        idx_start = PAGE_SIZE - 4 - len(row_offsets) * 2
        rowpf = 0
        for i in range(min(len(row_offsets), 16)):
            rowpf |= (1 << i)

        # Row presence flags
        struct.pack_into('<H', page, PAGE_SIZE - 4, rowpf)
        # Transaction flags
        struct.pack_into('<H', page, PAGE_SIZE - 2, 0)

        # Row offsets (2 bytes each, before the flags)
        for i, ofs in enumerate(row_offsets):
            pos = PAGE_SIZE - 4 - (i + 1) * 2
            struct.pack_into('<H', page, pos, ofs)

        return bytes(page)

    def write(self, filepath: str):
        """Write the complete .pdb file."""
        self.pages = []

        # Reserve page 0 for header
        self.pages.append(b'\x00' * PAGE_SIZE)

        table_pointers = []
        page_idx = 1

        for table_type in sorted(self.tables.keys()):
            table_data = self.tables[table_type]
            rows = table_data["rows"]

            if not rows:
                table_pointers.append((table_type, 0, page_idx, page_idx))
                continue

            first_page = page_idx
            # Split rows into pages (simple: put as many as fit)
            # For simplicity, put rows one per page for large rows (tracks),
            # or batch small rows
            chunk_size = 1 if table_type == TABLE_TRACKS else 16

            for i in range(0, len(rows), chunk_size):
                chunk = rows[i:i + chunk_size]
                is_last = (i + chunk_size >= len(rows))
                next_pg = 0 if is_last else page_idx + 1

                data_page = self._build_data_page(
                    table_type, page_idx, next_pg, chunk, seq=page_idx
                )
                self.pages.append(data_page)
                last_page = page_idx
                page_idx += 1

            table_pointers.append((table_type, 0, first_page, last_page))

        # Build header page (page 0)
        header = bytearray(PAGE_SIZE)
        struct.pack_into('<I', header, 0x00, 0)                    # padding
        struct.pack_into('<I', header, 0x04, PAGE_SIZE)            # len_page
        struct.pack_into('<I', header, 0x08, len(table_pointers))  # num_tables
        struct.pack_into('<I', header, 0x0C, page_idx)             # next_unused
        struct.pack_into('<I', header, 0x10, 0)                    # padding
        struct.pack_into('<I', header, 0x14, 1)                    # seqdb

        # Table pointers start at 0x1C (each 16 bytes)
        for i, (ttype, empty, first, last) in enumerate(table_pointers):
            base = 0x1C + i * 16
            struct.pack_into('<IIII', header, base, ttype, empty, first, last)

        self.pages[0] = bytes(header)

        # Write all pages to file
        with open(filepath, 'wb') as f:
            for page in self.pages:
                f.write(page)
