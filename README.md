# DJX

Open-source DJ toolkit for discovering, downloading, analyzing, and managing music from SoundCloud. Built for DJs who want full control over their library without being locked into Rekordbox.

## Features

### Discovery
- **Genre-based discovery** across 15 genres (House, Tech House, Afro House, Amapiano, UK Garage, Techno, Minimal, Disco/Funk, D&B, Dubstep, Trance, Dancehall, Hip-Hop, Jersey Club, Latin House)
- **4 discovery modes**: Trending (rising fast), Popular (most played all time), Fresh (newest uploads), Related (find similar tracks)
- **Trending score** combining play velocity, engagement ratio, and recency — surfaces tracks that are blowing up right now
- **Remix discovery** with automatic genre-filtered search
- **Paste any SoundCloud URL** to resolve, preview, and download with auto genre detection

### Channels & Tastemaker Discovery
- **Curated channels** — follow SoundCloud accounts by genre, approve/reject workflow
- **Related artists** — finds artists similar to those in your library via SoundCloud's algorithm
- **Tastemaker discovery** — finds DJs/curators who liked the same tracks you downloaded
- Approved channels feed into genre discovery for better results

### Library Management
- **Full metadata editing** — title, artist, genre (updates DB + ID3 tags on file)
- **Search and filter** by title, artist, genre
- **BPM and key columns** with Camelot/traditional toggle
- **Inline track detail** — click any track to open waveform, cues, and beat grid
- **File import** — add tracks from any folder on your computer
- **Delete** removes both DB record and file from disk

### Audio Analysis (via Essentia)
- **BPM detection** — accurate tempo analysis
- **Key detection** — musical key with Camelot wheel notation (8B, 6A, etc.)
- **Beat grid** — automatic beat detection with manual grid shift for downbeat alignment
- **Bulk analyze** — process your entire library in the background
- **Auto-analyze on download** — toggle in settings
- Results written to both database and MP3 ID3 tags

### Waveform Editor
- **CDJ/Serato-style waveform** — stacked frequency bands (bass blue, mids green, highs red)
- **Drag to scrub** — click and drag to scrub through the track
- **Hot cue placement** — click on waveform to place cues with custom names
- **Drag cues** — reposition cue markers by dragging, snaps to nearest beat
- **Beat grid editing** — shift grid in 10ms increments for downbeat alignment
- **Zoom and pan** — scroll to pan, Cmd+scroll to zoom
- **Live playhead** — shows current position with time overlay

### Player
- **Spotify-style bottom bar** — persists across all pages
- **Queue system** — skip forward/back through discovered tracks
- **Volume control** with mute toggle
- **Pause/resume** without losing position
- **Stream + embed fallback** — tries direct streaming, falls back to SoundCloud embed

### Playlists
- **Create playlists** from selected library tracks
- **Drag to reorder** tracks within playlists
- **Rename and delete** playlists
- **Export to folder** — copies playlist tracks to any folder (USB drives, etc.)
- **Native folder picker** on macOS

### Rekordbox Integration
- **Export to Rekordbox XML** — includes BPM, key, cue points
- Import the XML into Rekordbox to sync your library
- Hot cues and tempo maps included in export

### Download Engine
- **3-tier cascade**: yt-dlp (best quality) → scdl → direct stream
- **Duplicate detection** — SQLite-backed, never re-downloads
- **500+ tracks** downloaded and managed successfully

## Quick Start

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend && npm install && npm run build && cd ..

# Launch the web UI
python3 sc_discover.py --serve
# Open http://127.0.0.1:8000
```

## CLI Usage

```bash
# Interactive genre discovery
python3 sc_discover.py

# Specific genre
python3 sc_discover.py -g house -n 50

# All genres with remixes
python3 sc_discover.py -a -r

# Artist search
python3 sc_discover.py --artist "Fisher"

# Track search
python3 sc_discover.py --search "amapiano remix"

# Start web UI
python3 sc_discover.py --serve
```

## Tech Stack

- **Backend**: Python, FastAPI, SQLite, soundcloud-v2
- **Frontend**: React, TypeScript, Tailwind CSS, Vite
- **Audio Analysis**: Essentia (BPM, key, beats), Librosa (waveforms)
- **Download**: yt-dlp, mutagen (ID3 tags)
- **Rekordbox**: pyrekordbox (XML export)
- **Streaming**: HLS.js for in-browser audio preview

## Requirements

- Python 3.9+
- Node.js 18+
- ffmpeg (for audio processing)
- macOS / Linux (Windows untested)
