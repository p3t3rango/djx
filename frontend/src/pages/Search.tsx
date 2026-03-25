import { useState } from 'react';
import { Search as SearchIcon, Loader2, Download, User, Play, Pause, ExternalLink } from 'lucide-react';
import { api } from '../api/client';
import { usePlayer } from '../components/PlayerContext';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState<'tracks' | 'artists'>('tracks');
  const [tracks, setTracks] = useState<any[]>([]);
  const [artists, setArtists] = useState<any[]>([]);
  const [artistTracks, setArtistTracks] = useState<any[]>([]);
  const [selectedArtist, setSelectedArtist] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadMsg, setDownloadMsg] = useState('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const player = usePlayer();

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    if (tab === 'tracks') {
      const results = await api.searchTracks(query);
      setTracks(results);
      setSelected(new Set(results.map((t: any) => t.track_id)));
    } else {
      const results = await api.searchArtists(query);
      setArtists(results);
    }
    setLoading(false);
  };

  const viewArtist = async (artist: any) => {
    setSelectedArtist(artist);
    setLoading(true);
    const t = await api.getArtistTracks(artist.user_id);
    setArtistTracks(t);
    setSelected(new Set(t.map((tr: any) => tr.track_id)));
    setLoading(false);
  };

  const toggleSelect = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const downloadSelected = async (tracksToDownload: any[], folder: string) => {
    const ids = tracksToDownload.filter(t => selected.has(t.track_id)).map(t => t.track_id);
    if (!ids.length) return;
    setDownloading(true);
    setDownloadMsg('Starting...');
    const { task_id } = await api.downloadTracks(ids, folder);
    const poll = setInterval(async () => {
      const status = await api.getDownloadStatus(task_id);
      setDownloadMsg(status.message || status.status);
      if (status.status === 'completed' || status.status === 'failed') {
        clearInterval(poll);
        setDownloading(false);
        const r = status.result;
        if (r) setDownloadMsg(`${r.downloaded} downloaded, ${r.skipped} skipped`);
      }
    }, 2000);
  };

  const formatPlays = (n: number) => n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}K` : String(n);
  const scoreColor = (s: number) => s >= 1000 ? 'score-viral' : s >= 200 ? 'score-hot' : s >= 50 ? 'score-rising' : 'score-steady';

  const renderTrackTable = (trackList: any[], folder: string) => {
    const selectedCount = trackList.filter(t => selected.has(t.track_id)).length;
    return (
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-4 text-[11px] font-mono">
            <span className="text-[var(--color-text-dim)]">{trackList.length} TRACKS</span>
            <span className="text-[var(--color-glow)]">{selectedCount} SELECTED</span>
            <button onClick={() => setSelected(new Set(trackList.map(t => t.track_id)))}
              className="text-[var(--color-text-dim)] hover:text-[var(--color-text)] transition-colors">ALL</button>
            <button onClick={() => setSelected(new Set())}
              className="text-[var(--color-text-dim)] hover:text-[var(--color-text)] transition-colors">NONE</button>
          </div>
          <button onClick={() => downloadSelected(trackList, folder)}
            disabled={downloading || selectedCount === 0}
            className="glow-btn px-4 py-2 rounded text-[11px] font-mono flex items-center gap-2">
            {downloading ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
            {downloading ? downloadMsg : `DOWNLOAD ${selectedCount}`}
          </button>
        </div>
        <div className="bg-[var(--color-surface-2)] rounded border border-[var(--color-border)] overflow-hidden">
          <table className="w-full text-[11px] font-mono">
            <thead><tr className="border-b border-[var(--color-border)] text-[var(--color-text-dim)]">
              <th className="w-8 px-2 py-2.5">
                <input type="checkbox" checked={selectedCount === trackList.length && trackList.length > 0}
                  onChange={() => selectedCount === trackList.length ? setSelected(new Set()) : setSelected(new Set(trackList.map(t => t.track_id)))} />
              </th>
              <th className="w-8"></th>
              <th className="text-left px-2 py-2.5 tracking-wider">TITLE</th>
              <th className="text-left px-2 py-2.5 tracking-wider">ARTIST</th>
              <th className="text-right px-2 py-2.5 tracking-wider">PLAYS</th>
              <th className="text-right px-3 py-2.5 tracking-wider">SCORE</th>
              <th className="w-8"></th>
            </tr></thead>
            <tbody>
              {trackList.map((t: any, idx: number) => {
                const score = Math.round(t.trending_score);
                const isActive = player.playingTrack?.track_id === t.track_id || player.embedTrack?.track_id === t.track_id;
                const isThisPlaying = player.playingTrack?.track_id === t.track_id && player.isPlaying;
                const isThisLoading = player.playingTrack?.track_id === t.track_id && player.isLoading;
                return (
                  <tr key={t.track_id} className={`border-b border-[var(--color-border)]/30 transition-all duration-150 ${isActive ? 'bg-[var(--color-glow-dim)]' : 'hover:bg-[var(--color-surface-3)]'}`}>
                    <td className="px-2 py-2 text-center">
                      <input type="checkbox" checked={selected.has(t.track_id)} onChange={() => toggleSelect(t.track_id)} />
                    </td>
                    <td className="px-1 py-2">
                      <button onClick={() => player.playFromQueue(trackList, idx)}
                        className={`p-1 rounded-full transition-all ${isActive ? 'text-[var(--color-glow)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-glow)]'}`}>
                        {isThisLoading ? <Loader2 size={13} className="animate-spin" /> :
                         isThisPlaying ? <Pause size={13} /> : <Play size={13} />}
                      </button>
                    </td>
                    <td className="px-2 py-2 max-w-[280px] truncate text-[var(--color-text)]">{t.title}</td>
                    <td className="px-2 py-2 max-w-[160px] truncate text-[var(--color-text-dim)]">{t.artist}</td>
                    <td className="px-2 py-2 text-right text-[var(--color-text-dim)]">{formatPlays(t.playback_count)}</td>
                    <td className={`px-3 py-2 text-right ${scoreColor(score)}`}>{score}</td>
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
  };

  return (
    <div>
      <h2 className="text-xl font-mono font-bold tracking-wider mb-6 glow-text">SEARCH</h2>

      <div className="flex gap-2 mb-4">
        <div className="flex-1 relative">
          <SearchIcon size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-dim)]" />
          <input value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
            placeholder={tab === 'tracks' ? 'Search tracks...' : 'Search artists...'}
            className="w-full bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded-lg pl-10 pr-4 py-2.5 text-xs font-mono text-[var(--color-text)] placeholder-[var(--color-text-dim)] focus:outline-none focus:border-[var(--color-border-glow)]" />
        </div>
        <button onClick={search} disabled={loading}
          className="glow-btn px-6 py-2.5 rounded-lg text-xs font-mono disabled:opacity-50">
          {loading ? <Loader2 size={14} className="animate-spin" /> : 'SEARCH'}
        </button>
      </div>

      <div className="flex gap-1 mb-6">
        {(['tracks', 'artists'] as const).map(t => (
          <button key={t} onClick={() => { setTab(t); setSelectedArtist(null); }}
            className={`px-4 py-1.5 rounded text-[11px] font-mono tracking-wide ${tab === t ? 'bg-[var(--color-surface-3)] text-[var(--color-text)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-text)]'}`}>
            {t.toUpperCase()}
          </button>
        ))}
      </div>

      {tab === 'tracks' && tracks.length > 0 &&
        renderTrackTable(tracks, `search-${query.replace(/\s+/g, '-').toLowerCase().replace(/[^a-z0-9-]/g, '').slice(0, 30)}`)}

      {tab === 'artists' && !selectedArtist && artists.length > 0 && (
        <div className="grid grid-cols-2 gap-3">
          {artists.map((a: any) => (
            <button key={a.user_id} onClick={() => viewArtist(a)}
              className="flex items-center gap-3 bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded-lg p-4 hover:border-[var(--color-border-glow)] transition-colors text-left">
              <div className="w-10 h-10 bg-[var(--color-surface-3)] rounded-full flex items-center justify-center">
                <User size={18} className="text-[var(--color-text-dim)]" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-mono text-sm">{a.username}</div>
                <div className="text-[10px] font-mono text-[var(--color-text-dim)]">
                  {formatPlays(a.follower_count)} followers · {a.track_count} tracks
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {selectedArtist && (
        <div>
          <button onClick={() => setSelectedArtist(null)}
            className="text-[11px] font-mono text-[var(--color-glow)] mb-3 hover:underline">← BACK</button>
          <h3 className="text-sm font-mono font-bold mb-3">{selectedArtist.username.toUpperCase()}</h3>
          {loading ? (
            <div className="flex items-center gap-2 text-[var(--color-glow)] font-mono text-xs">
              <Loader2 size={14} className="animate-spin" /> LOADING...
            </div>
          ) : renderTrackTable(artistTracks, `artist-${selectedArtist.username.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '').slice(0, 30)}`)}
        </div>
      )}
    </div>
  );
}
