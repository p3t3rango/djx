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
        ]
        for sql in migrations:
            try:
                self.conn.execute(sql)
            except Exception:
                pass  # Column already exists
        self.conn.commit()

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
                      limit: int = 50, offset: int = 0) -> List[dict]:
        query = "SELECT d.id, d.track_id, d.genre_folder, d.file_path, d.file_size_bytes, d.download_method, d.status, d.downloaded_at, COALESCE(t.title, '') as title, COALESCE(t.artist, '') as artist, COALESCE(t.permalink_url, '') as permalink_url, COALESCE(t.playback_count, 0) as playback_count, t.bpm, t.musical_key, t.camelot_key, t.cues_json, t.analyzed_at FROM downloads d LEFT JOIN tracks t ON d.track_id = t.track_id WHERE 1=1"
        params = []
        if genre:
            query += " AND d.genre_folder = ?"
            params.append(genre)
        if status:
            query += " AND d.status = ?"
            params.append(status)
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

    def close(self):
        self.conn.close()
