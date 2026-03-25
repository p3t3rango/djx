import { useEffect, useState } from 'react';
import { Loader2, Check, X, Eye, UserPlus, Sparkles, ExternalLink } from 'lucide-react';
import { api } from '../api/client';

export default function CuratedAccounts() {
  const [accounts, setAccounts] = useState<any[]>([]);
  const [genres, setGenres] = useState<Record<string, any>>({});
  const [selectedGenre, setSelectedGenre] = useState('');
  const [statusFilter, setStatusFilter] = useState('suggested');
  const [suggesting, setSuggesting] = useState(false);
  const [findingTastemakers, setFindingTastemakers] = useState(false);
  const [findingRelated, setFindingRelated] = useState(false);
  const [tastemakerMsg, setTastemakerMsg] = useState('');
  const [previewTracks, setPreviewTracks] = useState<any[]>([]);
  const [previewAccount, setPreviewAccount] = useState<any>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  useEffect(() => { api.getGenres().then(setGenres); }, []);
  useEffect(() => { loadAccounts(); }, [selectedGenre, statusFilter]);

  const loadAccounts = () => {
    api.getAccounts(selectedGenre || undefined, statusFilter || undefined).then(setAccounts);
  };

  const suggest = async () => {
    if (!selectedGenre) return;
    setSuggesting(true);
    await api.suggestAccounts(selectedGenre);
    loadAccounts();
    setSuggesting(false);
  };

  const findTastemakers = async () => {
    setFindingTastemakers(true);
    setTastemakerMsg('Scanning your library...');
    try {
      const res = await fetch('/api/accounts/tastemakers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sample_size: 20, min_overlap: 2 }),
      });
      const { task_id } = await res.json();

      const poll = setInterval(async () => {
        const status = await fetch(`/api/accounts/tastemakers/status/${task_id}`).then(r => r.json());
        setTastemakerMsg(status.message || status.status);
        if (status.status === 'completed' || status.status === 'failed') {
          clearInterval(poll);
          setFindingTastemakers(false);
          if (status.result) {
            setTastemakerMsg(`Found ${status.result.found} tastemakers who share your taste`);
          }
          if (status.error) {
            setTastemakerMsg(`Error: ${status.error}`);
          }
          loadAccounts();
        }
      }, 2000);
    } catch {
      setFindingTastemakers(false);
      setTastemakerMsg('Error starting tastemaker search');
    }
  };

  const findRelatedArtists = async () => {
    setFindingRelated(true);
    setTastemakerMsg('Scanning your library artists...');
    try {
      const res = await fetch('/api/accounts/related-artists', { method: 'POST' });
      const { task_id } = await res.json();
      const poll = setInterval(async () => {
        const status = await fetch(`/api/accounts/tastemakers/status/${task_id}`).then(r => r.json());
        setTastemakerMsg(status.message || status.status);
        if (status.status === 'completed' || status.status === 'failed') {
          clearInterval(poll);
          setFindingRelated(false);
          if (status.result) setTastemakerMsg(`Found ${status.result.found} related artists`);
          if (status.error) setTastemakerMsg(`Error: ${status.error}`);
          loadAccounts();
        }
      }, 2000);
    } catch {
      setFindingRelated(false);
      setTastemakerMsg('Error');
    }
  };

  const approve = async (userId: number) => { await api.approveAccount(userId); loadAccounts(); };
  const reject = async (userId: number) => { await api.rejectAccount(userId); loadAccounts(); };

  const preview = async (account: any) => {
    setPreviewAccount(account);
    setLoadingPreview(true);
    const tracks = await api.getAccountTracks(account.user_id);
    setPreviewTracks(tracks);
    setLoadingPreview(false);
  };

  const formatPlays = (n: number) => n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}K` : String(n);

  return (
    <div>
      <h2 className="text-xl font-mono font-bold tracking-wider mb-6 glow-text">CHANNELS</h2>

      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <select value={selectedGenre} onChange={e => setSelectedGenre(e.target.value)}
          className="bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-3 py-2 text-xs font-mono text-[var(--color-text)]">
          <option value="">ALL GENRES</option>
          {Object.entries(genres).map(([k, v]: [string, any]) => (
            <option key={k} value={k}>{v.display_name.toUpperCase()}</option>
          ))}
        </select>

        <div className="flex gap-1">
          {['suggested', 'approved', 'rejected'].map(s => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded text-[11px] font-mono tracking-wide ${
                statusFilter === s ? 'bg-[var(--color-surface-3)] text-[var(--color-text)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-text)]'
              }`}>
              {s.toUpperCase()}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        {selectedGenre && (
          <button onClick={suggest} disabled={suggesting}
            className="glow-btn px-4 py-2 rounded text-[11px] font-mono flex items-center gap-2">
            {suggesting ? <Loader2 size={12} className="animate-spin" /> : <UserPlus size={12} />}
            SUGGEST
          </button>
        )}

        <button onClick={findRelatedArtists} disabled={findingRelated}
          className="glow-btn px-4 py-2 rounded text-[11px] font-mono flex items-center gap-2 disabled:opacity-50">
          {findingRelated ? <Loader2 size={12} className="animate-spin" /> : <UserPlus size={12} />}
          RELATED ARTISTS
        </button>

        <button onClick={findTastemakers} disabled={findingTastemakers}
          className="px-4 py-2 rounded text-[11px] font-mono flex items-center gap-2 border border-purple-500/40 text-purple-400 bg-purple-500/10 hover:bg-purple-500/20 transition-colors disabled:opacity-50"
          style={{ boxShadow: '0 0 15px rgba(168,85,247,0.1)' }}>
          {findingTastemakers ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
          FIND TASTEMAKERS
        </button>
      </div>

      {tastemakerMsg && (
        <div className="mb-4 flex items-center gap-2 text-[11px] font-mono text-purple-400">
          {findingTastemakers && <Loader2 size={12} className="animate-spin" />}
          {tastemakerMsg}
        </div>
      )}

      {accounts.length === 0 && (
        <div className="text-center py-16">
          <p className="text-sm font-mono text-[var(--color-text-dim)] mb-2">
            {selectedGenre ? 'NO CHANNELS FOUND' : 'SELECT A GENRE OR FIND TASTEMAKERS'}
          </p>
          <p className="text-[11px] font-mono text-[var(--color-text-dim)] opacity-50">
            Tastemakers are users who liked multiple tracks in your library — they have similar taste
          </p>
        </div>
      )}

      <div className="space-y-2">
        {accounts.map((a: any) => (
          <div key={a.user_id} className="bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded p-4 flex items-center gap-4 hover:border-[var(--color-border-glow)] transition-colors">
            <div className="w-10 h-10 bg-[var(--color-surface-3)] rounded-full flex items-center justify-center text-[var(--color-text-dim)] text-sm font-mono font-bold shrink-0">
              {a.username[0]?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                {a.permalink_url ? (
                  <a href={a.permalink_url} target="_blank" rel="noopener noreferrer"
                    className="text-sm font-mono text-[var(--color-text)] hover:text-[var(--color-glow)] transition-colors">
                    {a.username}
                  </a>
                ) : (
                  <span className="text-sm font-mono">{a.username}</span>
                )}
                {a.permalink_url && (
                  <a href={a.permalink_url} target="_blank" rel="noopener noreferrer"
                    className="text-[var(--color-text-dim)] hover:text-[var(--color-glow)]" title="Open SoundCloud profile">
                    <ExternalLink size={11} />
                  </a>
                )}
              </div>
              <div className="text-[10px] font-mono text-[var(--color-text-dim)]">
                {formatPlays(a.follower_count)} followers · {a.track_count} tracks
                {a.genre && <> · {a.genre}</>}
              </div>
              {a.suggested_reason && (
                <div className="text-[10px] font-mono text-purple-400/70 mt-0.5 truncate">{a.suggested_reason}</div>
              )}
            </div>
            <div className="flex gap-1 shrink-0">
              <button onClick={() => preview(a)} className="p-2 hover:bg-[var(--color-surface-3)] rounded transition-colors" title="Preview tracks">
                <Eye size={14} className="text-[var(--color-text-dim)]" />
              </button>
              {a.status === 'suggested' && (
                <>
                  <button onClick={() => approve(a.user_id)} className="p-2 hover:bg-green-900/30 rounded transition-colors" title="Approve">
                    <Check size={14} className="text-green-500" />
                  </button>
                  <button onClick={() => reject(a.user_id)} className="p-2 hover:bg-red-900/30 rounded transition-colors" title="Reject">
                    <X size={14} className="text-red-500" />
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Preview Modal */}
      {previewAccount && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50" onClick={() => setPreviewAccount(null)}>
          <div className="bg-[var(--color-surface-2)] border border-[var(--color-border)] glow-border rounded-lg w-full max-w-xl max-h-[70vh] overflow-auto p-6" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-mono font-bold glow-text">{previewAccount.username.toUpperCase()}</h3>
                <p className="text-[10px] font-mono text-[var(--color-text-dim)]">
                  {formatPlays(previewAccount.follower_count)} followers · {previewAccount.track_count} tracks
                </p>
              </div>
              <button onClick={() => setPreviewAccount(null)} className="text-[var(--color-text-dim)]"><X size={16} /></button>
            </div>
            {loadingPreview ? (
              <div className="flex items-center gap-2 text-[var(--color-glow)] py-8 justify-center font-mono text-xs">
                <Loader2 size={14} className="animate-spin" /> LOADING...
              </div>
            ) : (
              <div className="space-y-1">
                {previewTracks.map((t: any) => (
                  <div key={t.track_id} className="flex items-center justify-between px-3 py-2 bg-[var(--color-surface-3)] rounded text-xs font-mono">
                    <span className="truncate flex-1">{t.title}</span>
                    <span className="text-[var(--color-text-dim)] ml-4">{formatPlays(t.playback_count)}</span>
                  </div>
                ))}
                {previewTracks.length === 0 && <p className="text-[var(--color-text-dim)] text-xs font-mono text-center py-4">NO TRACKS FOUND</p>}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
