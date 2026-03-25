import { useEffect, useState } from 'react';
import { Plus, Trash2, Edit3, Check, X, Play, GripVertical, FolderOutput } from 'lucide-react';
import { api } from '../api/client';
import { usePlayer, type PlayerTrack } from '../components/PlayerContext';

export default function Playlists() {
  const [playlists, setPlaylists] = useState<any[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [tracks, setTracks] = useState<any[]>([]);
  const [allTracks, setAllTracks] = useState<any[]>([]);
  const [renaming, setRenaming] = useState<number | null>(null);
  const [renameVal, setRenameVal] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const player = usePlayer();

  useEffect(() => {
    api.getPlaylists().then(setPlaylists);
    fetch('/api/analysis/tracks?limit=1000').then(r => r.json()).then(setAllTracks);
  }, []);

  useEffect(() => {
    if (expanded) {
      const pl = playlists.find(p => p.id === expanded);
      if (pl && allTracks.length) {
        const map = new Map(allTracks.map(t => [t.track_id, t]));
        setTracks(pl.track_ids.map((id: number) => map.get(id)).filter(Boolean));
      }
    }
  }, [expanded, playlists, allTracks]);

  const rename = async (id: number) => {
    if (!renameVal.trim()) return;
    await api.updatePlaylist(id, { name: renameVal });
    setRenaming(null);
    api.getPlaylists().then(setPlaylists);
  };

  const remove = async (playlistId: number, index: number) => {
    const pl = playlists.find(p => p.id === playlistId);
    if (!pl) return;
    const newIds = pl.track_ids.filter((_: any, i: number) => i !== index);
    await api.updatePlaylist(playlistId, { track_ids: newIds });
    api.getPlaylists().then(setPlaylists);
  };

  const handleDragEnd = async (playlistId: number) => {
    if (dragIdx === null || dragOverIdx === null || dragIdx === dragOverIdx) {
      setDragIdx(null);
      setDragOverIdx(null);
      return;
    }
    const pl = playlists.find(p => p.id === playlistId);
    if (!pl) return;
    const newIds = [...pl.track_ids];
    const [moved] = newIds.splice(dragIdx, 1);
    newIds.splice(dragOverIdx, 0, moved);
    await api.updatePlaylist(playlistId, { track_ids: newIds });
    setDragIdx(null);
    setDragOverIdx(null);
    api.getPlaylists().then(setPlaylists);
  };

  const exportPlaylist = async (pl: any) => {
    try {
      const res = await fetch('/api/pick-folder');
      const data = await res.json();
      if (!data.path) return;
      const result = await api.createPlaylist(pl.name, pl.track_ids, data.path);
      alert(`Exported ${result.copied} tracks to ${data.path}`);
    } catch {
      // Fallback to text prompt
      const folder = prompt('Export folder path:');
      if (!folder) return;
      await api.createPlaylist(pl.name, pl.track_ids, folder);
    }
  };

  const createPlaylist = async () => {
    if (!newName.trim()) return;
    await api.createPlaylist(newName, []);
    setNewName('');
    setShowCreate(false);
    api.getPlaylists().then(setPlaylists);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-mono font-bold tracking-wider glow-text">PLAYLISTS</h2>
        <button onClick={() => setShowCreate(true)}
          className="glow-btn px-4 py-2 rounded text-[11px] font-mono flex items-center gap-2">
          <Plus size={12} /> NEW PLAYLIST
        </button>
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="mb-5 bg-[var(--color-surface-2)] border border-[var(--color-border)] glow-border rounded p-4">
          <div className="flex gap-2">
            <input value={newName} onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && createPlaylist()}
              placeholder="Playlist name..."
              className="flex-1 bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-3 py-2 text-xs font-mono text-[var(--color-text)] focus:outline-none focus:border-[var(--color-border-glow)]" />
            <button onClick={createPlaylist} className="glow-btn px-4 py-2 rounded text-[11px] font-mono">CREATE</button>
            <button onClick={() => setShowCreate(false)} className="text-[var(--color-text-dim)]"><X size={16} /></button>
          </div>
        </div>
      )}

      {playlists.length === 0 && !showCreate && (
        <div className="text-center py-16">
          <p className="text-sm font-mono text-[var(--color-text-dim)] mb-2">NO PLAYLISTS YET</p>
          <p className="text-[11px] font-mono text-[var(--color-text-dim)] opacity-50">
            Create a playlist here or select tracks in the Library and click PLAYLIST
          </p>
        </div>
      )}

      <div className="space-y-3">
        {playlists.map(pl => (
          <div key={pl.id} className="bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3">
              {renaming === pl.id ? (
                <div className="flex items-center gap-2">
                  <input value={renameVal} onChange={e => setRenameVal(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && rename(pl.id)}
                    className="bg-[var(--color-surface)] border border-[var(--color-border-glow)] rounded px-2 py-1 text-xs font-mono text-[var(--color-text)]" />
                  <button onClick={() => rename(pl.id)} className="text-green-400"><Check size={14} /></button>
                  <button onClick={() => setRenaming(null)} className="text-[var(--color-text-dim)]"><X size={14} /></button>
                </div>
              ) : (
                <button onClick={() => setExpanded(expanded === pl.id ? null : pl.id)}
                  className="flex items-center gap-3 text-sm font-mono hover:text-[var(--color-glow)] transition-colors">
                  <span className="text-[var(--color-text)] font-bold">{pl.name}</span>
                  <span className="text-[10px] text-[var(--color-text-dim)]">{pl.track_count} TRACKS</span>
                </button>
              )}
              <div className="flex items-center gap-1">
                <button onClick={() => { setRenaming(pl.id); setRenameVal(pl.name); }}
                  className="p-1.5 hover:bg-[var(--color-surface-3)] rounded" title="Rename">
                  <Edit3 size={13} className="text-[var(--color-text-dim)]" />
                </button>
                <button onClick={() => exportPlaylist(pl)}
                  className="p-1.5 hover:bg-[var(--color-surface-3)] rounded" title="Export to folder">
                  <FolderOutput size={13} className="text-[var(--color-text-dim)]" />
                </button>
                <button onClick={() => api.deletePlaylist(pl.id).then(() => api.getPlaylists().then(setPlaylists))}
                  className="p-1.5 hover:bg-red-900/30 rounded" title="Delete">
                  <Trash2 size={13} className="text-[var(--color-text-dim)] hover:text-red-400" />
                </button>
              </div>
            </div>

            {/* Track list */}
            {expanded === pl.id && (
              <div className="border-t border-[var(--color-border)]">
                {tracks.length === 0 && (
                  <p className="px-4 py-6 text-center text-[11px] font-mono text-[var(--color-text-dim)]">
                    EMPTY — Select tracks in the Library and click PLAYLIST to add
                  </p>
                )}
                {tracks.length > 0 && (
                  <div className="flex items-center gap-2 px-4 py-1.5 text-[9px] font-mono text-[var(--color-text-dim)] tracking-widest border-b border-[var(--color-border)]">
                    <span className="w-5 shrink-0" />
                    <span className="w-5 shrink-0">#</span>
                    <span className="w-6 shrink-0" />
                    <span className="flex-1">TITLE</span>
                    <span className="w-[120px]">ARTIST</span>
                    <span className="w-[80px]">GENRE</span>
                    <span className="w-10 text-right">BPM</span>
                    <span className="w-8">KEY</span>
                    <span className="w-14 text-right">SIZE</span>
                    <span className="w-5" />
                  </div>
                )}
                {tracks.map((t: any, i: number) => (
                  <div key={`${t.track_id}-${i}`}
                    draggable
                    onDragStart={() => setDragIdx(i)}
                    onDragOver={e => { e.preventDefault(); setDragOverIdx(i); }}
                    onDragEnd={() => handleDragEnd(pl.id)}
                    className={`flex items-center gap-2 px-4 py-2 border-b border-[var(--color-border)]/30 last:border-0 transition-colors cursor-grab active:cursor-grabbing text-[11px] font-mono ${
                      dragOverIdx === i && dragIdx !== null && dragIdx !== i ? 'bg-[var(--color-glow-dim)]' : 'hover:bg-[var(--color-surface-3)]'
                    }`}>
                    <GripVertical size={12} className="text-[var(--color-text-dim)] shrink-0 w-5" />
                    <span className="text-[var(--color-text-dim)] w-5 text-right text-[10px] shrink-0">{i + 1}</span>
                    <button onClick={() => player.playFromQueue(tracks as PlayerTrack[], i)}
                      className="text-[var(--color-text-dim)] hover:text-[var(--color-glow)] shrink-0 w-6">
                      <Play size={12} />
                    </button>
                    <span className="flex-1 truncate text-[var(--color-text)]">{t.title || 'Unknown'}</span>
                    <span className="text-[var(--color-text-dim)] truncate w-[120px]">{t.artist || ''}</span>
                    <span className="text-[var(--color-text-dim)] truncate w-[80px]">{t.genre_folder || t.source_genre || ''}</span>
                    <span className="w-10 text-right">{t.bpm ? <span className="text-[var(--color-glow)]">{Math.round(t.bpm)}</span> : <span className="text-[var(--color-text-dim)]">—</span>}</span>
                    <span className="w-8">{t.camelot_key ? <span className="text-[var(--color-glow)]">{t.camelot_key}</span> : <span className="text-[var(--color-text-dim)]">—</span>}</span>
                    <span className="w-14 text-right text-[var(--color-text-dim)]">{t.file_size_bytes ? (t.file_size_bytes >= 1e6 ? `${(t.file_size_bytes/1e6).toFixed(1)}MB` : `${(t.file_size_bytes/1e3).toFixed(0)}KB`) : '—'}</span>
                    <button onClick={() => remove(pl.id, i)}
                      className="text-[var(--color-text-dim)] hover:text-red-400 shrink-0 w-5">
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
