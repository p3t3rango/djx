import glob
import os
import shutil
import subprocess
from typing import List, Optional, Callable

import requests
from soundcloud import SoundCloud

from core.config import get_setting
from core.database import Database
from core.models import Track, DownloadResult, DownloadReport
from core.utils import sanitize_filename, ensure_directory


def _find_executable(name: str) -> Optional[str]:
    """Find an executable using system PATH only (no user-writable directory fallbacks)."""
    return shutil.which(name)


class DownloadService:
    def __init__(self, sc: SoundCloud, db: Database):
        self.sc = sc
        self.db = db

    def download_tracks(self, tracks: List[Track], genre_folder: str,
                        on_progress: Optional[Callable] = None) -> DownloadReport:
        base_dir = get_setting("download_dir", self.db)
        output_dir = os.path.join(base_dir, genre_folder)
        ensure_directory(output_dir)
        report = DownloadReport()

        for i, track in enumerate(tracks):
            if on_progress:
                on_progress(i, len(tracks), track)

            # Check duplicate in DB
            if self.db.is_downloaded(track.track_id, genre_folder):
                report.skipped += 1
                report.results.append(DownloadResult(
                    track_id=track.track_id, title=track.title,
                    artist=track.artist, status="skipped"
                ))
                continue

            # Check file on disk too
            if self._file_exists(track, output_dir):
                self.db.record_download(track.track_id, genre_folder, status="completed")
                report.skipped += 1
                report.results.append(DownloadResult(
                    track_id=track.track_id, title=track.title,
                    artist=track.artist, status="skipped"
                ))
                continue

            # Store track metadata
            self.db.upsert_track(track.to_db_dict())

            # Try download cascade
            method, file_path = self._download_single(track, output_dir)
            if method:
                file_size = os.path.getsize(file_path) if file_path and os.path.exists(file_path) else None
                self.db.record_download(
                    track.track_id, genre_folder, file_path=file_path,
                    file_size=file_size, method=method, status="completed"
                )
                report.downloaded += 1
                report.results.append(DownloadResult(
                    track_id=track.track_id, title=track.title,
                    artist=track.artist, status="downloaded",
                    method=method, file_path=file_path
                ))

                # Auto-analyze if setting is enabled
                auto = self.db.get_setting("auto_analyze")
                if auto == "true" and file_path and os.path.exists(file_path):
                    try:
                        from core.analysis_service import analyze_track, write_id3_tags
                        from core.camelot import from_essentia
                        import json
                        result = analyze_track(file_path)
                        if result.success:
                            self.db.conn.execute("""
                                UPDATE tracks SET bpm = ?, musical_key = ?, camelot_key = ?,
                                    bpm_confidence = ?, key_confidence = ?,
                                    analyzed_at = datetime('now'), beats_json = ?
                                WHERE track_id = ?
                            """, (result.bpm, result.musical_key, result.camelot_key,
                                  result.bpm_confidence, result.key_confidence,
                                  json.dumps(result.beats[:100]), track.track_id))
                            self.db.conn.commit()
                            write_id3_tags(file_path, result.bpm, result.musical_key)
                    except Exception:
                        pass  # Don't fail download if analysis fails
            else:
                self.db.record_download(
                    track.track_id, genre_folder, status="failed",
                    error="All download methods failed"
                )
                report.failed += 1
                report.results.append(DownloadResult(
                    track_id=track.track_id, title=track.title,
                    artist=track.artist, status="failed",
                    error="All download methods failed"
                ))

        return report

    def _download_single(self, track: Track, output_dir: str):
        # Tier 1: yt-dlp
        path = self._try_ytdlp(track, output_dir)
        if path:
            return "yt-dlp", path

        # Tier 2: scdl
        path = self._try_scdl(track, output_dir)
        if path:
            return "scdl", path

        # Tier 3: direct stream
        path = self._try_direct(track, output_dir)
        if path:
            return "direct", path

        return None, None

    def _try_ytdlp(self, track: Track, output_dir: str) -> Optional[str]:
        ytdlp = _find_executable("yt-dlp")
        if not ytdlp:
            return None
        template = os.path.join(output_dir, f"{track.safe_filename}.%(ext)s")
        cmd = [
            ytdlp, "-x", "--audio-format", "mp3", "--audio-quality", "0",
            "--no-overwrites", "--no-warnings", "--quiet",
            "-o", template, track.permalink_url,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                # Find the actual output file
                pattern = os.path.join(output_dir, f"{track.safe_filename}.*")
                files = glob.glob(pattern)
                return files[0] if files else None
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def _try_scdl(self, track: Track, output_dir: str) -> Optional[str]:
        scdl = _find_executable("scdl")
        if not scdl:
            return None
        cmd = [
            scdl, "-l", track.permalink_url, "--path", output_dir,
            "--onlymp3", "--name-format", track.safe_filename,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                pattern = os.path.join(output_dir, f"{track.safe_filename}.*")
                files = glob.glob(pattern)
                return files[0] if files else None
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def _try_direct(self, track: Track, output_dir: str) -> Optional[str]:
        # Try original download
        try:
            download_url = self.sc.get_track_original_download(track.track_id)
            if download_url:
                path = self._download_stream(download_url, track, output_dir)
                if path:
                    return path
        except Exception:
            pass

        # Try stream transcodings
        try:
            sc_track = self.sc.get_track(track.track_id)
            if not sc_track or not hasattr(sc_track, "media") or not sc_track.media:
                return None

            transcodings = sc_track.media.transcodings
            if not transcodings:
                return None

            progressive = None
            any_transcoding = None
            for t in transcodings:
                if hasattr(t, "format") and t.format:
                    any_transcoding = t
                    protocol = getattr(t.format, "protocol", "")
                    if protocol == "progressive":
                        progressive = t
                        break

            chosen = progressive or any_transcoding
            if not chosen or not chosen.url:
                return None

            stream_url = chosen.url
            sep = "&" if "?" in stream_url else "?"
            resolve_url = f"{stream_url}{sep}client_id={self.sc.client_id}"
            resp = requests.get(resolve_url, timeout=10)
            if resp.status_code != 200:
                return None

            actual_url = resp.json().get("url")
            if not actual_url:
                return None

            return self._download_stream(actual_url, track, output_dir)
        except Exception:
            return None

    def _download_stream(self, url: str, track: Track, output_dir: str) -> Optional[str]:
        filepath = os.path.join(output_dir, f"{track.safe_filename}.mp3")
        try:
            resp = requests.get(url, stream=True, timeout=60)
            if resp.status_code != 200:
                return None
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            if os.path.getsize(filepath) < 1000:
                os.remove(filepath)
                return None
            return filepath
        except Exception:
            if os.path.exists(filepath):
                os.remove(filepath)
            return None

    def _file_exists(self, track: Track, output_dir: str) -> bool:
        pattern = os.path.join(output_dir, f"{track.safe_filename}.*")
        return len(glob.glob(pattern)) > 0
