import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Download, TrendingUp, Music, Users, ChevronRight, Play, Pause, Loader2, Link, Zap } from 'lucide-react';
import { api } from '../api/client';
import { usePlayer, type PlayerTrack } from '../components/PlayerContext';

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [recentDownloads, setRecentDownloads] = useState<any[]>([]);
  const [scUrl, setScUrl] = useState('');
  const [resolving, setResolving] = useState(false);
  const [resolved, setResolved] = useState<any>(null);
  const [dlFolder, setDlFolder] = useState('');
  const [analyzeAfter, setAnalyzeAfter] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadMsg, setDownloadMsg] = useState('');
  const navigate = useNavigate();
  const player = usePlayer();

  useEffect(() => {
    api.getDownloadStats().then(setStats);
    api.getAccounts(undefined, 'approved').then(setAccounts);
    api.getDownloads(undefined, 10).then(setRecentDownloads);
  }, []);

  const isSoundCloudUrl = (url: string) => {
    try {
      const parsed = new URL(url);
      return ['soundcloud.com', 'www.soundcloud.com', 'm.soundcloud.com', 'on.soundcloud.com'].includes(parsed.hostname);
    } catch { return false; }
  };

  const resolveUrl = async () => {
    if (!scUrl.trim()) return;
    if (!isSoundCloudUrl(scUrl.trim())) {
      setDownloadMsg('Please enter a valid SoundCloud URL');
      return;
    }
    setResolving(true);
    setResolved(null);
    setDownloadMsg('');
    const data = await api.resolveUrl(scUrl.trim());
    setResolving(false);
    if (data.error) {
      setDownloadMsg(`Error: ${data.error}`);
    } else {
      setResolved(data);
      setDlFolder(data.suggested_folder);
    }
  };

  const downloadTrack = async () => {
    if (!resolved) return;
    setDownloading(true);
    setDownloadMsg('Downloading...');
    const { task_id } = await api.downloadFromUrl(scUrl.trim(), dlFolder, analyzeAfter);
    const poll = setInterval(async () => {
      const status = await api.getDownloadStatus(task_id);
      setDownloadMsg(status.message || status.status);
      if (status.status === 'completed' || status.status === 'failed') {
        clearInterval(poll);
        setDownloading(false);
        if (!status.error) {
          setResolved(null);
          setScUrl('');
          api.getDownloads(undefined, 10).then(setRecentDownloads);
          api.getDownloadStats().then(setStats);
        }
      }
    }, 1500);
  };

  const formatPlays = (n: number) => n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}K` : String(n);
  const formatDuration = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

  const statCards = [
    { label: 'TOTAL TRACKS', value: stats?.total ?? '-', icon: Download },
    { label: 'THIS WEEK', value: stats?.this_week ?? '-', icon: TrendingUp },
    { label: 'GENRES', value: stats?.by_genre ? Object.keys(stats.by_genre).length : '-', icon: Music },
    { label: 'CHANNELS', value: accounts.length, icon: Users },
  ];

  const genreButtons = ['house', 'tech-house', 'afro-house', 'amapiano', 'uk-garage'];
  const recentWithTitle = recentDownloads.filter(d => d.title);

  return (
    <div>
      <h2 className="text-xl font-mono font-bold tracking-wider mb-8 glow-text">DASHBOARD</h2>

      {/* SoundCloud URL Download */}
      <div className="mb-8 bg-[var(--color-surface-2)] border border-[var(--color-border)] glow-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <Link size={14} className="text-[var(--color-glow)]" />
          <span className="text-[11px] font-mono text-[var(--color-glow)] tracking-wider">PASTE SOUNDCLOUD LINK</span>
        </div>
        <div className="flex gap-2">
          <input value={scUrl} onChange={e => { setScUrl(e.target.value); setResolved(null); setDownloadMsg(''); }}
            onKeyDown={e => e.key === 'Enter' && resolveUrl()}
            placeholder="https://soundcloud.com/artist/track-name"
            className="flex-1 bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-3 py-2.5 text-xs font-mono text-[var(--color-text)] placeholder-[var(--color-text-dim)] focus:outline-none focus:border-[var(--color-border-glow)]" />
          <button onClick={resolveUrl} disabled={resolving || !scUrl.trim()}
            className="glow-btn px-5 py-2.5 rounded text-xs font-mono flex items-center gap-2 disabled:opacity-40">
            {resolving ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
            {resolving ? 'RESOLVING' : 'RESOLVE'}
          </button>
        </div>

        {/* Resolved track preview */}
        {resolved && (
          <div className="mt-3 bg-[var(--color-surface-3)] rounded p-3">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="text-xs font-mono text-[var(--color-text)]">{resolved.title}</div>
                <div className="text-[10px] font-mono text-[var(--color-text-dim)]">
                  {resolved.artist} · {formatPlays(resolved.playback_count)} plays · {formatDuration(resolved.duration_seconds)}
                </div>
              </div>
              {resolved.genre && (
                <span className="text-[10px] font-mono text-[var(--color-glow)] bg-[var(--color-glow-dim)] px-2 py-0.5 rounded">
                  {resolved.genre}
                </span>
              )}
            </div>

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <span className="text-[9px] font-mono text-[var(--color-text-dim)]">FOLDER</span>
                <input value={dlFolder} onChange={e => setDlFolder(e.target.value)}
                  className="w-32 bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-2 py-1 text-[11px] font-mono text-[var(--color-text)]" />
              </div>

              <label className="flex items-center gap-1.5 cursor-pointer select-none">
                <input type="checkbox" checked={analyzeAfter} onChange={e => setAnalyzeAfter(e.target.checked)} />
                <span className="text-[9px] font-mono text-[var(--color-text-dim)]">ANALYZE AFTER</span>
                <Zap size={10} className={analyzeAfter ? 'text-[var(--color-glow)]' : 'text-[var(--color-text-dim)]'} />
              </label>

              <div className="flex-1" />

              <button onClick={downloadTrack} disabled={downloading}
                className="glow-btn px-5 py-2 rounded text-xs font-mono flex items-center gap-2 disabled:opacity-40">
                {downloading ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                {downloading ? 'DOWNLOADING' : 'DOWNLOAD'}
              </button>
            </div>
          </div>
        )}

        {downloadMsg && <p className="text-[10px] font-mono text-[var(--color-glow)] mt-2">{downloadMsg}</p>}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-10">
        {statCards.map(({ label, value, icon: Icon }) => (
          <div key={label} className="bg-[var(--color-surface-2)] rounded border border-[var(--color-border)] glow-border p-5">
            <div className="flex items-center gap-2 mb-3">
              <Icon size={14} className="text-[var(--color-glow)]" />
              <span className="text-[10px] font-mono text-[var(--color-text-dim)] tracking-widest">{label}</span>
            </div>
            <div className="text-3xl font-mono font-bold">{value}</div>
          </div>
        ))}
      </div>

      {/* Quick Discover */}
      <div className="mb-10">
        <h3 className="text-xs font-mono text-[var(--color-text-dim)] tracking-widest mb-3">QUICK DISCOVER</h3>
        <div className="flex gap-2">
          {genreButtons.map(g => (
            <button key={g} onClick={() => navigate(`/genres?genre=${g}`)}
              className="glow-btn px-4 py-2 rounded text-xs font-mono tracking-wide">
              {g.toUpperCase().replace('-', ' ')}
            </button>
          ))}
        </div>
      </div>

      {/* Genre + Recent */}
      {stats?.by_genre && (
        <div className="grid grid-cols-2 gap-6">
          <div>
            <h3 className="text-xs font-mono text-[var(--color-text-dim)] tracking-widest mb-3">LIBRARY BY GENRE</h3>
            <div className="bg-[var(--color-surface-2)] rounded border border-[var(--color-border)] overflow-hidden">
              {Object.entries(stats.by_genre)
                .sort(([, a]: any, [, b]: any) => b - a)
                .map(([genre, count]: [string, any]) => (
                  <button key={genre} onClick={() => navigate(`/downloads?genre=${genre}`)}
                    className="w-full flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-surface-3)] transition-colors text-left">
                    <span className="text-xs font-mono">{genre}</span>
                    <span className="text-xs font-mono text-[var(--color-glow)]">{count}</span>
                  </button>
                ))}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-mono text-[var(--color-text-dim)] tracking-widest">RECENT DOWNLOADS</h3>
              <button onClick={() => navigate('/downloads')} className="text-[10px] font-mono text-[var(--color-text-dim)] hover:text-[var(--color-glow)] transition-colors flex items-center gap-1">
                VIEW ALL <ChevronRight size={10} />
              </button>
            </div>
            <div className="bg-[var(--color-surface-2)] rounded border border-[var(--color-border)] overflow-hidden">
              {recentWithTitle.slice(0, 8).map((d: any, i: number) => {
                const isActive = player.playingTrack?.track_id === d.track_id;
                const isPlaying = isActive && player.isPlaying;
                return (
                  <div key={d.id || i} className={`flex items-center gap-2 px-3 py-2 border-b border-[var(--color-border)] last:border-0 transition-colors ${isActive ? 'bg-[var(--color-glow-dim)]' : 'hover:bg-[var(--color-surface-3)]'}`}>
                    <button onClick={() => player.playFromQueue(recentWithTitle as PlayerTrack[], i)}
                      className={`p-1 rounded-full shrink-0 ${isActive ? 'text-[var(--color-glow)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-glow)]'}`}>
                      {isPlaying ? <Pause size={12} /> : <Play size={12} />}
                    </button>
                    <button onClick={() => navigate(`/downloads?genre=${d.genre_folder}&track=${d.track_id}`)}
                      className="min-w-0 flex-1 text-left hover:text-[var(--color-glow)] transition-colors">
                      <div className="text-xs font-mono truncate">{d.title}</div>
                      <div className="text-[10px] text-[var(--color-text-dim)]">{d.artist}</div>
                    </button>
                    <span className="text-[10px] font-mono text-[var(--color-text-dim)] shrink-0">{d.genre_folder}</span>
                  </div>
                );
              })}
              {recentWithTitle.length === 0 && (
                <div className="px-4 py-6 text-center text-xs text-[var(--color-text-dim)]">No recent downloads</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
