import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Loader2, Download, Play, Pause, ExternalLink, TrendingUp, Flame, Sparkles, Link2, Zap } from 'lucide-react';
import { api } from '../api/client';
import { usePlayer, type PlayerTrack } from '../components/PlayerContext';

type SortMode = 'trending' | 'popular' | 'fresh' | 'related';

const SORT_TABS: { mode: SortMode; label: string; icon: any; desc: string }[] = [
  { mode: 'trending', label: 'TRENDING', icon: TrendingUp, desc: 'Rising fast right now' },
  { mode: 'popular', label: 'POPULAR', icon: Flame, desc: 'Top played of all time' },
  { mode: 'fresh', label: 'FRESH', icon: Sparkles, desc: 'Newest uploads first' },
  { mode: 'related', label: 'RELATED', icon: Link2, desc: 'Find similar tracks' },
];

export default function GenreBrowser() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [genres, setGenres] = useState<Record<string, any>>({});
  const [selectedGenre, setSelectedGenre] = useState(searchParams.get('genre') || '');
  const [sortMode, setSortMode] = useState<SortMode>('trending');
  const [tracks, setTracks] = useState<any[]>([]);
  const [remixTracks, setRemixTracks] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [downloadMsg, setDownloadMsg] = useState('');
  const [count, setCount] = useState(50);
  const [includeRemixes, setIncludeRemixes] = useState(false);
  const [analyzeAfter, setAnalyzeAfter] = useState(false);
  const [autoCues, setAutoCues] = useState(false);
  const [downloadArt, setDownloadArt] = useState(true);
  const [analyzeOnDiscover, setAnalyzeOnDiscover] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [relatedInput, setRelatedInput] = useState('');
  const [sortCol, setSortCol] = useState<string>('trending_score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const player = usePlayer();

  useEffect(() => { api.getGenres().then(setGenres); }, []);

  const discover = async (genre: string, sort: SortMode = sortMode) => {
    if (sort === 'related') return; // handled separately
    setSelectedGenre(genre);
    setSearchParams({ genre });
    setLoading(true);
    setTracks([]);
    setRemixTracks([]);
    setSelected(new Set());
    setMessage('Connecting to SoundCloud...');

    const { task_id } = await api.discover(genre, count, includeRemixes, sort, analyzeOnDiscover);
    pollTask(task_id);
  };

  const discoverRelated = async () => {
    // Try to extract track ID from URL or use as ID
    let trackId: number;
    const input = relatedInput.trim();
    if (!input) return;

    if (input.match(/^\d+$/)) {
      trackId = parseInt(input);
    } else {
      // Could be a SoundCloud URL — try to resolve
      setMessage('This feature works with track IDs. Find the ID from your library or SoundCloud.');
      return;
    }

    setLoading(true);
    setTracks([]);
    setRemixTracks([]);
    setSelected(new Set());
    setMessage('Finding related tracks...');

    const { task_id } = await api.discoverRelated(trackId, count);
    pollTask(task_id);
  };

  const pollTask = (task_id: string) => {
    const poll = setInterval(async () => {
      const status = await api.getDiscoveryStatus(task_id);
      setMessage(status.message || status.status);
      if (status.status === 'completed') {
        clearInterval(poll);
        const found = status.result?.tracks || [];
        const remixes = status.result?.remix_tracks || [];
        setTracks(found);
        setRemixTracks(remixes);
        setSelected(new Set([...found, ...remixes].map((t: any) => t.track_id)));
        setLoading(false);
        setMessage(`${found.length} tracks${remixes.length ? ` + ${remixes.length} remixes` : ''} discovered`);
      } else if (status.status === 'failed') {
        clearInterval(poll);
        setLoading(false);
        setMessage(`Error: ${status.error}`);
      }
    }, 2000);
  };

  const toggleSelect = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const allTracks = [...tracks, ...remixTracks];
  const selectAll = () => setSelected(new Set(allTracks.map(t => t.track_id)));
  const selectNone = () => setSelected(new Set());

  const downloadSelected = async () => {
    if (!selected.size) return;
    setDownloading(true);
    setDownloadMsg('Queuing...');
    const folder = selectedGenre ? (genres[selectedGenre]?.folder || selectedGenre) : 'related';
    const { task_id } = await api.downloadTracks(Array.from(selected), folder, analyzeAfter, downloadArt);
    const poll = setInterval(async () => {
      const status = await api.getDownloadStatus(task_id);
      setDownloadMsg(status.message || status.status);
      if (status.status === 'completed' || status.status === 'failed') {
        clearInterval(poll);
        setDownloading(false);
        const r = status.result;
        if (r) setDownloadMsg(`${r.downloaded} downloaded, ${r.skipped} skipped, ${r.failed} failed`);
        else if (status.error) setDownloadMsg(`Error: ${status.error}`);
      }
    }, 2000);
  };

  const formatPlays = (n: number) => n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}K` : String(n);
  // Dynamic thresholds per sort mode
  const thresholds = sortMode === 'popular'
    ? { viral: 65, hot: 55, rising: 45 }
    : sortMode === 'fresh'
    ? { viral: 220, hot: 180, rising: 130 }
    : { viral: 300, hot: 200, rising: 100 };  // trending
  const scoreColor = (s: number) => s >= thresholds.viral ? 'score-viral' : s >= thresholds.hot ? 'score-hot' : s >= thresholds.rising ? 'score-rising' : 'score-steady';
  const scoreLabel = (s: number) => s >= thresholds.viral ? 'VIRAL' : s >= thresholds.hot ? 'HOT' : s >= thresholds.rising ? 'RISING' : '';

  const toggleSort = (col: string) => {
    if (sortCol === col) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortCol(col);
      setSortDir(col === 'title' || col === 'artist' || col === 'genre' || col === 'camelot_key' ? 'asc' : 'desc');
    }
  };

  const sortArrow = (col: string) => sortCol === col ? (sortDir === 'asc' ? ' \u25B2' : ' \u25BC') : '';

  const sortTracks = (list: any[]) => {
    return [...list].sort((a, b) => {
      let va = a[sortCol], vb = b[sortCol];
      if (va == null) va = sortDir === 'asc' ? '\uffff' : '';
      if (vb == null) vb = sortDir === 'asc' ? '\uffff' : '';
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      if (va < vb) return sortDir === 'asc' ? -1 : 1;
      if (va > vb) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  };

  const renderTable = (trackList: any[], title?: string) => (
    <div className={title ? 'mt-6' : ''}>
      {title && <h3 className="text-xs font-mono text-[var(--color-glow)] tracking-widest mb-3">{title}</h3>}
      <div className="bg-[var(--color-surface-2)] rounded border border-[var(--color-border)] overflow-hidden">
        <table className="w-full text-[11px] font-mono">
          <thead>
            <tr className="border-b border-[var(--color-border)] text-[var(--color-text-dim)]">
              <th className="w-8 px-2 py-2.5">
                <input type="checkbox"
                  checked={trackList.every(t => selected.has(t.track_id)) && trackList.length > 0}
                  onChange={() => {
                    const allSelected = trackList.every(t => selected.has(t.track_id));
                    const next = new Set(selected);
                    trackList.forEach(t => allSelected ? next.delete(t.track_id) : next.add(t.track_id));
                    setSelected(next);
                  }} />
              </th>
              <th className="w-8"></th>
              <th className="text-left px-2 py-2.5 tracking-wider cursor-pointer hover:text-[var(--color-glow)]" onClick={() => toggleSort('title')}>TITLE{sortArrow('title')}</th>
              <th className="text-left px-2 py-2.5 tracking-wider cursor-pointer hover:text-[var(--color-glow)]" onClick={() => toggleSort('artist')}>ARTIST{sortArrow('artist')}</th>
              <th className="text-right px-2 py-2.5 tracking-wider cursor-pointer hover:text-[var(--color-glow)]" onClick={() => toggleSort('bpm')}>BPM{sortArrow('bpm')}</th>
              <th className="text-left px-2 py-2.5 tracking-wider cursor-pointer hover:text-[var(--color-glow)]" onClick={() => toggleSort('camelot_key')}>KEY{sortArrow('camelot_key')}</th>
              <th className="text-center px-2 py-2.5 tracking-wider cursor-pointer hover:text-[var(--color-glow)]" onClick={() => toggleSort('energy')}>NRG{sortArrow('energy')}</th>
              <th className="text-left px-2 py-2.5 tracking-wider cursor-pointer hover:text-[var(--color-glow)]" onClick={() => toggleSort('genre')}>GENRE{sortArrow('genre')}</th>
              <th className="text-center px-2 py-2.5 tracking-wider cursor-pointer hover:text-[var(--color-glow)]" onClick={() => toggleSort('bitrate')}>QUALITY{sortArrow('bitrate')}</th>
              <th className="text-right px-2 py-2.5 tracking-wider cursor-pointer hover:text-[var(--color-glow)]" onClick={() => toggleSort('playback_count')}>PLAYS{sortArrow('playback_count')}</th>
              <th className="text-right px-3 py-2.5 tracking-wider cursor-pointer hover:text-[var(--color-glow)]" onClick={() => toggleSort('trending_score')}>SCORE{sortArrow('trending_score')}</th>
              <th className="w-8"></th>
            </tr>
          </thead>
          <tbody>
            {sortTracks(trackList).map((t: any, idx: number) => {
              const score = Math.round(t.trending_score);
              const isActive = player.playingTrack?.track_id === t.track_id || player.embedTrack?.track_id === t.track_id;
              const isThisPlaying = player.playingTrack?.track_id === t.track_id && player.isPlaying;
              const isThisLoading = player.playingTrack?.track_id === t.track_id && player.isLoading;
              return (
                <tr key={t.track_id}
                  className={`border-b border-[var(--color-border)]/30 transition-all duration-150 ${isActive ? 'bg-[var(--color-glow-dim)]' : 'hover:bg-[var(--color-surface-3)]'}`}>
                  <td className="px-2 py-2 text-center">
                    <input type="checkbox" checked={selected.has(t.track_id)} onChange={() => toggleSelect(t.track_id)} />
                  </td>
                  <td className="px-1 py-2">
                    <button onClick={() => player.playFromQueue(trackList as PlayerTrack[], idx)}
                      className={`p-1 rounded-full transition-all ${isActive ? 'text-[var(--color-glow)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-glow)]'}`}>
                      {isThisLoading ? <Loader2 size={13} className="animate-spin" /> :
                       isThisPlaying ? <Pause size={13} /> : <Play size={13} />}
                    </button>
                  </td>
                  <td className="px-2 py-2 max-w-[360px]">
                    <div className="flex items-center gap-2.5">
                      {t.artwork_url ? (
                        <img src={t.artwork_url.replace('-large', '-small')} alt="" className="w-8 h-8 rounded object-cover shrink-0 bg-[var(--color-surface-3)]" />
                      ) : (
                        <div className="w-8 h-8 rounded bg-[var(--color-surface-3)] shrink-0" />
                      )}
                      <span className="truncate text-[var(--color-text)]">{t.title}</span>
                    </div>
                  </td>
                  <td className="px-2 py-2 max-w-[140px] truncate text-[var(--color-text-dim)]">{t.artist}</td>
                  <td className="px-2 py-2 text-right">
                    {t.bpm ? <span className="text-[var(--color-glow)]">{Math.round(t.bpm)}</span> : <span className="text-[var(--color-text-dim)]">—</span>}
                  </td>
                  <td className="px-2 py-2">
                    {t.camelot_key ? <span className="text-[var(--color-glow)]">{t.camelot_key}</span> : <span className="text-[var(--color-text-dim)]">—</span>}
                  </td>
                  <td className="px-2 py-2 text-center">
                    {t.energy ? (
                      <span className={`font-bold text-[10px] ${t.energy >= 7 ? 'text-red-400' : t.energy >= 4 ? 'text-yellow-400' : 'text-cyan-400'}`}>{t.energy}</span>
                    ) : <span className="text-[var(--color-text-dim)]">—</span>}
                  </td>
                  <td className="px-2 py-2 max-w-[100px] truncate text-[var(--color-text-dim)] text-[10px]">{t.genre || ''}</td>
                  <td className="px-2 py-2 text-center">
                    {t.bitrate ? (
                      <span className={`text-[9px] font-bold ${
                        t.bitrate >= 320 || t.audio_format === 'wav' || t.audio_format === 'flac' ? 'text-[var(--color-glow)]' :
                        t.bitrate >= 256 ? 'text-yellow-400' : 'text-red-400'
                      }`}>{t.audio_format?.toUpperCase()} {t.bitrate}</span>
                    ) : t.downloaded ? <span className="text-[9px] text-[var(--color-text-dim)]">DL'd</span> : <span className="text-[var(--color-text-dim)]">—</span>}
                  </td>
                  <td className="px-2 py-2 text-right text-[var(--color-text-dim)]">{formatPlays(t.playback_count)}</td>
                  <td className="px-3 py-2 text-right">
                    <span className={scoreColor(score)}>{score}</span>
                    {scoreLabel(score) && <span className={`ml-1.5 text-[9px] ${scoreColor(score)} opacity-60`}>{scoreLabel(score)}</span>}
                  </td>
                  <td className="px-1 py-2">
                    <a href={t.permalink_url} target="_blank" rel="noopener noreferrer"
                      className="p-1 rounded text-[var(--color-text-dim)] hover:text-[var(--color-text)] transition-colors inline-block">
                      <ExternalLink size={12} />
                    </a>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );

  return (
    <div>
      <h2 className="text-xl font-mono font-bold tracking-wider mb-6 glow-text">DISCOVER</h2>

      {/* Sort mode tabs */}
      <div className="flex gap-1 mb-5 border-b border-[var(--color-border)] pb-3">
        {SORT_TABS.map(({ mode, label, icon: Icon, desc }) => (
          <button key={mode} onClick={() => { setSortMode(mode); setTracks([]); setRemixTracks([]); setMessage(''); }}
            className={`flex items-center gap-1.5 px-4 py-2 rounded text-[11px] font-mono tracking-wide transition-all ${
              sortMode === mode
                ? 'bg-[var(--color-glow-dim)] text-[var(--color-glow)] glow-border-strong border'
                : 'text-[var(--color-text-dim)] hover:text-[var(--color-text)] border border-transparent'
            }`}
            title={desc}>
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>

      {/* Related mode: input */}
      {sortMode === 'related' && (
        <div className="flex gap-2 mb-5">
          <input value={relatedInput} onChange={e => setRelatedInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && discoverRelated()}
            placeholder="Enter a SoundCloud track ID..."
            className="flex-1 bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-3 py-2 text-xs font-mono text-[var(--color-text)] placeholder-[var(--color-text-dim)] focus:outline-none focus:border-[var(--color-border-glow)]" />
          <button onClick={discoverRelated} disabled={loading || !relatedInput.trim()}
            className="glow-btn px-4 py-2 rounded text-[11px] font-mono disabled:opacity-40">
            FIND RELATED
          </button>
        </div>
      )}

      {/* Genre pills (not for related mode) */}
      {sortMode !== 'related' && (
        <div className="flex gap-2 mb-5 flex-wrap">
          {Object.entries(genres).map(([key, val]: [string, any]) => (
            <button key={key} onClick={() => discover(key)} disabled={loading}
              className={`px-3 py-1.5 rounded text-[11px] font-mono tracking-wide transition-all duration-200 border ${
                selectedGenre === key
                  ? 'glow-border-strong bg-[var(--color-glow-dim)] text-[var(--color-glow)]'
                  : 'border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text-dim)] hover:text-[var(--color-text)] hover:border-[var(--color-border-glow)]'
              }`}>
              {val.display_name.toUpperCase()}
            </button>
          ))}
        </div>
      )}

      {/* Controls */}
      {sortMode !== 'related' && (
        <div className="flex items-center gap-5 mb-5 text-[11px] font-mono text-[var(--color-text-dim)]">
          <label className="flex items-center gap-2">
            LIMIT
            <input type="number" value={count} onChange={e => setCount(Number(e.target.value))}
              className="w-14 bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-2 py-1 text-[var(--color-text)] font-mono text-[11px]" />
          </label>
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input type="checkbox" checked={includeRemixes} onChange={e => setIncludeRemixes(e.target.checked)} />
            REMIXES
          </label>
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input type="checkbox" checked={analyzeOnDiscover} onChange={e => {
              setAnalyzeOnDiscover(e.target.checked);
              if (e.target.checked && count > 10) setCount(10);
            }} />
            <Zap size={11} className={analyzeOnDiscover ? 'text-[var(--color-glow)]' : ''} />
            ANALYZE
          </label>
          {analyzeOnDiscover && (
            <span className="text-[9px] text-yellow-400">~{count * 8}s for {count} tracks</span>
          )}
          <div className="flex-1" />
          <div className="flex items-center gap-3 text-[10px]">
            <span>SCORE:</span>
            <span className="score-viral">{thresholds.viral}+ VIRAL</span>
            <span className="score-hot">{thresholds.hot}+ HOT</span>
            <span className="score-rising">{thresholds.rising}+ RISING</span>
          </div>
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-[var(--color-glow)] mb-5 font-mono text-xs">
          <Loader2 size={14} className="animate-spin" /> {message}
        </div>
      )}

      {(tracks.length > 0 || remixTracks.length > 0) && (
        <>
          {/* Toolbar */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-4 text-[11px] font-mono">
              <span className="text-[var(--color-text-dim)]">{allTracks.length} TRACKS</span>
              <span className="text-[var(--color-glow)]">{selected.size} SELECTED</span>
              <button onClick={selectAll} className="text-[var(--color-text-dim)] hover:text-[var(--color-text)] transition-colors">ALL</button>
              <button onClick={selectNone} className="text-[var(--color-text-dim)] hover:text-[var(--color-text)] transition-colors">NONE</button>
            </div>
            <label className="flex items-center gap-1.5 cursor-pointer select-none text-[11px] font-mono">
              <input type="checkbox" checked={analyzeAfter} onChange={e => setAnalyzeAfter(e.target.checked)} />
              <Zap size={11} className={analyzeAfter ? 'text-[var(--color-glow)]' : 'text-[var(--color-text-dim)]'} />
              <span className="text-[var(--color-text-dim)]">ANALYZE</span>
            </label>
            <label className={`flex items-center gap-1.5 select-none text-[11px] font-mono ${analyzeAfter ? 'cursor-pointer' : 'opacity-40 cursor-not-allowed'}`}>
              <input type="checkbox" checked={autoCues} onChange={e => setAutoCues(e.target.checked)} disabled={!analyzeAfter} />
              <span className="text-[var(--color-text-dim)]">AUTO CUES</span>
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer select-none text-[11px] font-mono">
              <input type="checkbox" checked={downloadArt} onChange={e => setDownloadArt(e.target.checked)} />
              <span className="text-[var(--color-text-dim)]">COVER ART</span>
            </label>
            <button onClick={downloadSelected} disabled={downloading || !selected.size}
              className="glow-btn px-4 py-2 rounded text-[11px] font-mono flex items-center gap-2">
              {downloading ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
              {downloading ? downloadMsg : `DOWNLOAD ${selected.size}`}
            </button>
          </div>

          {!loading && message && <p className="text-[10px] font-mono text-[var(--color-text-dim)] mb-2">{message}</p>}

          {tracks.length > 0 && renderTable(tracks)}
          {remixTracks.length > 0 && renderTable(remixTracks, 'REMIXES')}
        </>
      )}

      {!loading && !tracks.length && !message && sortMode !== 'related' && (
        <div className="text-center py-16">
          <p className="text-sm font-mono text-[var(--color-text-dim)] mb-2">SELECT A GENRE TO START DISCOVERING</p>
          <p className="text-[11px] font-mono text-[var(--color-text-dim)] opacity-50">
            {sortMode === 'trending' && 'Rising tracks — play velocity × engagement × recency'}
            {sortMode === 'popular' && 'Most played tracks of all time in this genre'}
            {sortMode === 'fresh' && 'Newest uploads — underground finds before anyone else'}
          </p>
        </div>
      )}
    </div>
  );
}
