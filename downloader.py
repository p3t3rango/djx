import glob
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from soundcloud import SoundCloud

from config import DOWNLOAD_DIR
from models import DiscoveredTrack
from utils import sanitize_filename, ensure_directory

console = Console()


def _find_executable(name: str) -> Optional[str]:
    """Find executable on PATH or in common pip install locations."""
    path = shutil.which(name)
    if path:
        return path
    # Check common user pip bin directories
    for candidate in [
        os.path.expanduser(f"~/Library/Python/3.9/bin/{name}"),
        os.path.expanduser(f"~/.local/bin/{name}"),
    ]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


@dataclass
class DownloadReport:
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    failed_tracks: List[str] = field(default_factory=list)


class TrackDownloader:
    def __init__(self, sc_client: SoundCloud, base_dir: str = DOWNLOAD_DIR):
        self.sc = sc_client
        self.base_dir = base_dir

    def download_tracks(self, tracks: List[DiscoveredTrack], genre_folder: str) -> DownloadReport:
        output_dir = os.path.join(self.base_dir, genre_folder)
        ensure_directory(output_dir)
        manifest = self._load_manifest(output_dir)
        report = DownloadReport()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Downloading...", total=len(tracks))

            for track in tracks:
                short_name = f"{track.artist} - {track.title}"
                if len(short_name) > 50:
                    short_name = short_name[:47] + "..."
                progress.update(task, description=short_name)

                if self._is_duplicate(track, output_dir, manifest):
                    report.skipped += 1
                    progress.advance(task)
                    continue

                success = self._download_single(track, output_dir)
                if success:
                    report.downloaded += 1
                    manifest.add(track.track_id)
                    self._save_manifest(output_dir, manifest)
                else:
                    report.failed += 1
                    report.failed_tracks.append(f"{track.artist} - {track.title}")

                progress.advance(task)

        return report

    def _download_single(self, track: DiscoveredTrack, output_dir: str) -> bool:
        if self._try_ytdlp(track, output_dir):
            return True
        if self._try_scdl(track, output_dir):
            return True
        if self._try_direct(track, output_dir):
            return True
        return False

    def _try_ytdlp(self, track: DiscoveredTrack, output_dir: str) -> bool:
        ytdlp = _find_executable("yt-dlp")
        if not ytdlp:
            return False
        template = os.path.join(output_dir, f"{track.safe_filename}.%(ext)s")
        cmd = [
            ytdlp,
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--no-overwrites",
            "--no-warnings",
            "--quiet",
            "-o", template,
            track.permalink_url,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _try_scdl(self, track: DiscoveredTrack, output_dir: str) -> bool:
        scdl = _find_executable("scdl")
        if not scdl:
            return False
        cmd = [
            scdl,
            "-l", track.permalink_url,
            "--path", output_dir,
            "--onlymp3",
            "--name-format", f"{track.safe_filename}",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _try_direct(self, track: DiscoveredTrack, output_dir: str) -> bool:
        # Try original download first
        try:
            download_url = self.sc.get_track_original_download(track.track_id)
            if download_url:
                return self._download_stream(download_url, track, output_dir)
        except Exception:
            pass

        # Try stream transcodings
        try:
            sc_track = self.sc.get_track(track.track_id)
            if not sc_track or not hasattr(sc_track, "media") or not sc_track.media:
                return False

            transcodings = sc_track.media.transcodings
            if not transcodings:
                return False

            # Prefer progressive (direct MP3) over HLS
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
            if not chosen:
                return False

            stream_url = chosen.url
            if not stream_url:
                return False

            # Resolve the stream URL (it returns JSON with the actual URL)
            sep = "&" if "?" in stream_url else "?"
            resolve_url = f"{stream_url}{sep}client_id={self.sc.client_id}"
            resp = requests.get(resolve_url, timeout=10)
            if resp.status_code != 200:
                return False

            actual_url = resp.json().get("url")
            if not actual_url:
                return False

            return self._download_stream(actual_url, track, output_dir)
        except Exception:
            return False

    def _download_stream(self, url: str, track: DiscoveredTrack, output_dir: str) -> bool:
        ext = "mp3"
        filepath = os.path.join(output_dir, f"{track.safe_filename}.{ext}")
        try:
            resp = requests.get(url, stream=True, timeout=60)
            if resp.status_code != 200:
                return False
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            # Verify file is not empty
            if os.path.getsize(filepath) < 1000:
                os.remove(filepath)
                return False
            return True
        except Exception:
            if os.path.exists(filepath):
                os.remove(filepath)
            return False

    def _is_duplicate(self, track: DiscoveredTrack, output_dir: str, manifest: set) -> bool:
        if track.track_id in manifest:
            return True
        pattern = os.path.join(output_dir, f"{track.safe_filename}.*")
        return len(glob.glob(pattern)) > 0

    def _load_manifest(self, output_dir: str) -> set:
        path = os.path.join(output_dir, ".manifest.json")
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return set(json.load(f))
            except (json.JSONDecodeError, TypeError):
                pass
        return set()

    def _save_manifest(self, output_dir: str, manifest: set):
        path = os.path.join(output_dir, ".manifest.json")
        with open(path, "w") as f:
            json.dump(list(manifest), f)
