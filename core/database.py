import glob
import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


class Database:
    def __init__(self, db_path: str = "sc_discover.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER UNIQUE NOT NULL,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                permalink_url TEXT NOT NULL,
                genre TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                playback_count INTEGER DEFAULT 0,
                likes_count INTEGER DEFAULT 0,
                repost_count INTEGER DEFAULT 0,
                duration_seconds INTEGER DEFAULT 0,
                is_downloadable BOOLEAN DEFAULT 0,
                artwork_url TEXT,
                created_at TEXT,
                discovered_at TEXT DEFAULT (datetime('now')),
                discovery_source TEXT,
                source_genre TEXT,
                trending_score REAL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER NOT NULL,
                genre_folder TEXT NOT NULL,
                file_path TEXT,
                file_size_bytes INTEGER,
                download_method TEXT,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                downloaded_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (track_id) REFERENCES tracks(track_id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_downloads_unique
                ON downloads(track_id, genre_folder);

            CREATE TABLE IF NOT EXISTS curated_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT NOT NULL,
                permalink_url TEXT,
                avatar_url TEXT,
                description TEXT,
                follower_count INTEGER DEFAULT 0,
                track_count INTEGER DEFAULT 0,
                genre TEXT NOT NULL,
                status TEXT DEFAULT 'suggested',
                suggested_reason TEXT,
                added_at TEXT DEFAULT (datetime('now')),
                last_checked_at TEXT,
                approved_at TEXT,
                rejected_at TEXT
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        self.conn.commit()
        self._migrate()

    def _migrate(self):
        """Add columns that may not exist in older databases."""
        migrations = [
            "ALTER TABLE tracks ADD COLUMN bpm REAL",
            "ALTER TABLE tracks ADD COLUMN musical_key TEXT",
            "ALTER TABLE tracks ADD COLUMN camelot_key TEXT",
            "ALTER TABLE tracks ADD COLUMN bpm_confidence REAL",
            "ALTER TABLE tracks ADD COLUMN key_confidence REAL",
            "ALTER TABLE tracks ADD COLUMN analyzed_at TEXT",
            "ALTER TABLE tracks ADD COLUMN beats_json TEXT",
            "ALTER TABLE tracks ADD COLUMN cues_json TEXT",  # hot cues, memory cues, loops
            "ALTER TABLE tracks ADD COLUMN energy INTEGER",  # 1-10 energy level (Beatport scale)
        ]
        for sql in migrations:
            try:
                self.conn.execute(sql)
            except Exception:
                pass  # Column already exists

        # Create tags tables
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                color TEXT DEFAULT '#00ffc8',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS track_tags (
                track_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (track_id, tag_id)
            );
        """)
        self.conn.commit()

    # --- Tags ---

    def get_tags(self) -> List[dict]:
        rows = self.conn.execute("""
            SELECT t.*, COUNT(tt.track_id) as track_count
            FROM tags t LEFT JOIN track_tags tt ON t.id = tt.tag_id
            GROUP BY t.id ORDER BY t.name
        """).fetchall()
        return [dict(r) for r in rows]

    def create_tag(self, name: str, color: str = '#00ffc8') -> int:
        self.conn.execute("INSERT OR IGNORE INTO tags (name, color) VALUES (?, ?)", (name, color))
        self.conn.commit()
        row = self.conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        return row["id"] if row else 0

    def delete_tag(self, tag_id: int):
        self.conn.execute("DELETE FROM track_tags WHERE tag_id = ?", (tag_id,))
        self.conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        self.conn.commit()

    def tag_track(self, track_id: int, tag_id: int):
        self.conn.execute("INSERT OR IGNORE INTO track_tags (track_id, tag_id) VALUES (?, ?)", (track_id, tag_id))
        self.conn.commit()

    def untag_track(self, track_id: int, tag_id: int):
        self.conn.execute("DELETE FROM track_tags WHERE track_id = ? AND tag_id = ?", (track_id, tag_id))
        self.conn.commit()

    def get_track_tags(self, track_id: int) -> List[dict]:
        rows = self.conn.execute("""
            SELECT t.* FROM tags t JOIN track_tags tt ON t.id = tt.tag_id WHERE tt.track_id = ?
        """, (track_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_tracks_by_tag(self, tag_id: int) -> List[int]:
        rows = self.conn.execute("SELECT track_id FROM track_tags WHERE tag_id = ?", (tag_id,)).fetchall()
        return [r["track_id"] for r in rows]

    # --- Tracks ---

    def upsert_track(self, track_data: dict):
        self.conn.execute("""
            INSERT INTO tracks (track_id, title, artist, permalink_url, genre, tags,
                playback_count, likes_count, repost_count, duration_seconds,
                is_downloadable, artwork_url, created_at, discovery_source,
                source_genre, trending_score)
            VALUES (:track_id, :title, :artist, :permalink_url, :genre, :tags,
                :playback_count, :likes_count, :repost_count, :duration_seconds,
                :is_downloadable, :artwork_url, :created_at, :discovery_source,
                :source_genre, :trending_score)
            ON CONFLICT(track_id) DO UPDATE SET
                title = CASE WHEN excluded.title != '' THEN excluded.title ELSE tracks.title END,
                artist = CASE WHEN excluded.artist != '' THEN excluded.artist ELSE tracks.artist END,
                permalink_url = CASE WHEN excluded.permalink_url != '' THEN excluded.permalink_url ELSE tracks.permalink_url END,
                genre = CASE WHEN excluded.genre != '' THEN excluded.genre ELSE tracks.genre END,
                tags = CASE WHEN excluded.tags != '' THEN excluded.tags ELSE tracks.tags END,
                artwork_url = COALESCE(excluded.artwork_url, tracks.artwork_url),
                created_at = COALESCE(excluded.created_at, tracks.created_at),
                duration_seconds = CASE WHEN excluded.duration_seconds > 0 THEN excluded.duration_seconds ELSE tracks.duration_seconds END,
                playback_count = excluded.playback_count,
                likes_count = excluded.likes_count,
                repost_count = excluded.repost_count,
                trending_score = excluded.trending_score
        """, track_data)
        self.conn.commit()

    def get_track(self, track_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM tracks WHERE track_id = ?", (track_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_tracks(self, genre: str = None, limit: int = 100, offset: int = 0) -> List[dict]:
        if genre:
            rows = self.conn.execute(
                "SELECT * FROM tracks WHERE source_genre = ? ORDER BY trending_score DESC LIMIT ? OFFSET ?",
                (genre, limit, offset)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM tracks ORDER BY trending_score DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Downloads ---

    def is_downloaded(self, track_id: int, genre_folder: str = None) -> bool:
        if genre_folder:
            row = self.conn.execute(
                "SELECT 1 FROM downloads WHERE track_id = ? AND genre_folder = ? AND status = 'completed'",
                (track_id, genre_folder)
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT 1 FROM downloads WHERE track_id = ? AND status = 'completed'",
                (track_id,)
            ).fetchone()
        return row is not None

    def record_download(self, track_id: int, genre_folder: str, file_path: str = None,
                        file_size: int = None, method: str = None, status: str = "completed",
                        error: str = None):
        self.conn.execute("""
            INSERT INTO downloads (track_id, genre_folder, file_path, file_size_bytes,
                download_method, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(track_id, genre_folder) DO UPDATE SET
                file_path = excluded.file_path,
                file_size_bytes = excluded.file_size_bytes,
                download_method = excluded.download_method,
                status = excluded.status,
                error_message = excluded.error_message,
                downloaded_at = datetime('now')
        """, (track_id, genre_folder, file_path, file_size, method, status, error))
        self.conn.commit()

    def get_downloads(self, genre: str = None, status: str = None,
                      limit: int = 50, offset: int = 0,
                      min_energy: int = None, max_energy: int = None) -> List[dict]:
        query = "SELECT d.id, d.track_id, d.genre_folder, d.file_path, d.file_size_bytes, d.download_method, d.status, d.downloaded_at, COALESCE(t.title, '') as title, COALESCE(t.artist, '') as artist, COALESCE(t.permalink_url, '') as permalink_url, COALESCE(t.playback_count, 0) as playback_count, t.bpm, t.musical_key, t.camelot_key, t.cues_json, t.analyzed_at, t.artwork_url, t.energy FROM downloads d LEFT JOIN tracks t ON d.track_id = t.track_id WHERE 1=1"
        params = []
        if genre:
            query += " AND d.genre_folder = ?"
            params.append(genre)
        if status:
            query += " AND d.status = ?"
            params.append(status)
        if min_energy is not None:
            query += " AND t.energy >= ?"
            params.append(min_energy)
        if max_energy is not None:
            query += " AND t.energy <= ?"
            params.append(max_energy)
        query += " ORDER BY d.downloaded_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    def get_download_stats(self) -> dict:
        total = self.conn.execute(
            "SELECT COUNT(*) as c FROM downloads WHERE status = 'completed'"
        ).fetchone()["c"]
        by_genre = self.conn.execute(
            "SELECT genre_folder, COUNT(*) as c FROM downloads WHERE status = 'completed' GROUP BY genre_folder"
        ).fetchall()
        recent = self.conn.execute(
            "SELECT COUNT(*) as c FROM downloads WHERE status = 'completed' AND downloaded_at > datetime('now', '-7 days')"
        ).fetchone()["c"]
        return {
            "total": total,
            "this_week": recent,
            "by_genre": {r["genre_folder"]: r["c"] for r in by_genre},
        }

    def delete_download(self, download_id: int) -> Optional[str]:
        row = self.conn.execute("SELECT file_path FROM downloads WHERE id = ?", (download_id,)).fetchone()
        if row:
            self.conn.execute("DELETE FROM downloads WHERE id = ?", (download_id,))
            self.conn.commit()
            return row["file_path"]
        return None

    # --- Curated Accounts ---

    def upsert_account(self, account_data: dict):
        self.conn.execute("""
            INSERT INTO curated_accounts (user_id, username, permalink_url, avatar_url,
                description, follower_count, track_count, genre, status, suggested_reason)
            VALUES (:user_id, :username, :permalink_url, :avatar_url,
                :description, :follower_count, :track_count, :genre, :status, :suggested_reason)
            ON CONFLICT(user_id) DO UPDATE SET
                follower_count = :follower_count,
                track_count = :track_count
        """, account_data)
        self.conn.commit()

    def get_accounts(self, genre: str = None, status: str = None) -> List[dict]:
        query = "SELECT * FROM curated_accounts WHERE 1=1"
        params = []
        if genre:
            query += " AND genre = ?"
            params.append(genre)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY follower_count DESC"
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    def update_account_status(self, user_id: int, status: str):
        now = datetime.utcnow().isoformat()
        if status == "approved":
            self.conn.execute(
                "UPDATE curated_accounts SET status = ?, approved_at = ? WHERE user_id = ?",
                (status, now, user_id))
        elif status == "rejected":
            self.conn.execute(
                "UPDATE curated_accounts SET status = ?, rejected_at = ? WHERE user_id = ?",
                (status, now, user_id))
        else:
            self.conn.execute(
                "UPDATE curated_accounts SET status = ? WHERE user_id = ?",
                (status, user_id))
        self.conn.commit()

    def delete_account(self, user_id: int):
        self.conn.execute("DELETE FROM curated_accounts WHERE user_id = ?", (user_id,))
        self.conn.commit()

    # --- Settings ---

    def get_setting(self, key: str, default: str = None) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
            (key, value, value))
        self.conn.commit()

    def get_all_settings(self) -> dict:
        rows = self.conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # --- Migration ---

    def migrate_manifests(self, download_dir: str):
        manifest_paths = glob.glob(os.path.join(download_dir, "*/.manifest.json"))
        migrated = 0
        for manifest_path in manifest_paths:
            genre_folder = os.path.basename(os.path.dirname(manifest_path))
            try:
                with open(manifest_path) as f:
                    track_ids = json.load(f)
                for tid in track_ids:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO tracks (track_id, title, artist, permalink_url) VALUES (?, '', '', '')",
                        (tid,))
                    self.conn.execute(
                        "INSERT OR IGNORE INTO downloads (track_id, genre_folder, status) VALUES (?, ?, 'completed')",
                        (tid, genre_folder))
                self.conn.commit()
                os.rename(manifest_path, manifest_path + ".migrated")
                migrated += len(track_ids)
            except (json.JSONDecodeError, OSError):
                pass
        return migrated

    # --- Library Manifest (portable metadata) ---

    def export_library_manifest(self, download_dir: str) -> str:
        """Export all library metadata to djx_library.json in the download folder.
        File paths are stored relative to download_dir for portability."""
        manifest = {"version": 1, "tracks": [], "tags": [], "track_tags": [], "playlists": []}

        # Tracks + downloads joined
        rows = self.conn.execute("""
            SELECT t.*, d.genre_folder, d.file_path, d.file_size_bytes, d.download_method, d.downloaded_at
            FROM tracks t
            JOIN downloads d ON t.track_id = d.track_id
            WHERE d.status = 'completed'
        """).fetchall()
        for r in rows:
            track = dict(r)
            # Make file_path relative
            fp = track.get("file_path")
            if fp and os.path.isabs(fp):
                try:
                    track["file_path"] = os.path.relpath(fp, download_dir)
                except ValueError:
                    pass  # different drive on Windows
            manifest["tracks"].append(track)

        # Tags, track-tags, playlists — tables may not exist yet
        for table, key in [("tags", "tags"), ("track_tags", "track_tags"), ("playlists", "playlists")]:
            try:
                for r in self.conn.execute(f"SELECT * FROM {table}").fetchall():
                    manifest[key].append(dict(r))
            except Exception:
                pass

        out_path = os.path.join(download_dir, "djx_library.json")
        with open(out_path, "w") as f:
            json.dump(manifest, f, indent=2, default=str)
        return out_path

    def import_library_manifest(self, manifest_path: str, download_dir: str) -> dict:
        """Restore library from a djx_library.json manifest.
        Resolves relative file paths against download_dir."""
        with open(manifest_path) as f:
            manifest = json.load(f)

        imported_tracks = 0
        skipped_tracks = 0

        for t in manifest.get("tracks", []):
            track_id = t.get("track_id")
            if not track_id:
                continue

            # Resolve relative file path
            fp = t.get("file_path")
            if fp and not os.path.isabs(fp):
                fp = os.path.join(download_dir, fp)
            # Skip if file doesn't exist on disk
            if not fp or not os.path.exists(fp):
                skipped_tracks += 1
                continue

            # Upsert track — preserve existing data, fill in gaps
            existing = self.conn.execute("SELECT 1 FROM tracks WHERE track_id = ?", (track_id,)).fetchone()
            if existing:
                # Update analysis fields if they're missing locally but present in manifest
                self.conn.execute("""
                    UPDATE tracks SET
                        bpm = COALESCE(bpm, ?), musical_key = COALESCE(musical_key, ?),
                        camelot_key = COALESCE(camelot_key, ?), bpm_confidence = COALESCE(bpm_confidence, ?),
                        key_confidence = COALESCE(key_confidence, ?), analyzed_at = COALESCE(analyzed_at, ?),
                        beats_json = COALESCE(beats_json, ?), cues_json = COALESCE(cues_json, ?),
                        permalink_url = CASE WHEN permalink_url = '' THEN ? ELSE permalink_url END,
                        artwork_url = COALESCE(artwork_url, ?),
                        energy = COALESCE(energy, ?)
                    WHERE track_id = ?
                """, (
                    t.get("bpm"), t.get("musical_key"), t.get("camelot_key"),
                    t.get("bpm_confidence"), t.get("key_confidence"), t.get("analyzed_at"),
                    t.get("beats_json"), t.get("cues_json"),
                    t.get("permalink_url", ""), t.get("artwork_url"), t.get("energy"),
                    track_id,
                ))
                # Update file path in downloads
                self.conn.execute(
                    "UPDATE downloads SET file_path = ? WHERE track_id = ? AND (file_path IS NULL OR file_path = '')",
                    (fp, track_id))
            else:
                self.conn.execute("""
                    INSERT OR IGNORE INTO tracks
                    (track_id, title, artist, permalink_url, genre, tags, playback_count,
                     likes_count, repost_count, duration_seconds, artwork_url, discovery_source,
                     bpm, musical_key, camelot_key, bpm_confidence, key_confidence, analyzed_at,
                     beats_json, cues_json, energy)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    track_id, t.get("title", ""), t.get("artist", ""),
                    t.get("permalink_url", ""), t.get("genre", ""), t.get("tags", ""),
                    t.get("playback_count", 0), t.get("likes_count", 0),
                    t.get("repost_count", 0), t.get("duration_seconds", 0),
                    t.get("artwork_url"), t.get("discovery_source"),
                    t.get("bpm"), t.get("musical_key"), t.get("camelot_key"),
                    t.get("bpm_confidence"), t.get("key_confidence"), t.get("analyzed_at"),
                    t.get("beats_json"), t.get("cues_json"), t.get("energy"),
                ))
                self.conn.execute("""
                    INSERT OR IGNORE INTO downloads (track_id, genre_folder, file_path, file_size_bytes, status, download_method)
                    VALUES (?, ?, ?, ?, 'completed', ?)
                """, (track_id, t.get("genre_folder", "imported"), fp,
                      t.get("file_size_bytes"), t.get("download_method", "imported")))
            imported_tracks += 1

        # Restore tags
        imported_tags = 0
        for tag in manifest.get("tags", []):
            self.conn.execute("INSERT OR IGNORE INTO tags (id, name, color) VALUES (?, ?, ?)",
                              (tag["id"], tag["name"], tag.get("color", "#00ffc8")))
            imported_tags += 1

        # Restore track-tag assignments
        for tt in manifest.get("track_tags", []):
            self.conn.execute("INSERT OR IGNORE INTO track_tags (track_id, tag_id) VALUES (?, ?)",
                              (tt["track_id"], tt["tag_id"]))

        # Restore playlists
        for pl in manifest.get("playlists", []):
            self.conn.execute("INSERT OR IGNORE INTO playlists (id, name, track_ids_json) VALUES (?, ?, ?)",
                              (pl["id"], pl["name"], pl.get("track_ids_json", "[]")))

        self.conn.commit()
        return {"imported_tracks": imported_tracks, "skipped_tracks": skipped_tracks, "imported_tags": imported_tags}

    def close(self):
        self.conn.close()
