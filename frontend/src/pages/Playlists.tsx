import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Plus, Trash2, Edit3, Check, X, Play, Pause, GripVertical, FolderOutput } from 'lucide-react';
import { api } from '../api/client';
import { usePlayer, type PlayerTrack } from '../components/PlayerContext';

function PlaylistCover({ tracks, size = 160, coverPath, playlistId, onCoverChange }: {
  tracks: any[]; size?: number; coverPath?: string | null; playlistId?: number; onCoverChange?: () => void;
}) {
  // Custom cover takes priority
  if (coverPath && playlistId) {
    return (
      <div className="relative group">
        <img src={`/api/downloads/playlists/${playlistId}/cover?t=${Date.now()}`} alt=""
          className="rounded-lg object-cover bg-[var(--color-surface-3)]"
          style={{ width: size, height: size }} />
        {onCoverChange && (
          <label className="absolute inset-0 rounded-lg bg-black/60 opacity-0 group-hover:opacity-100 flex items-center justify-center cursor-pointer transition-opacity">
            <span className="text-[10px] font-mono text-white">CHANGE COVER</span>
            <input type="file" accept="image/*" className="hidden" onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file || !playlistId) return;
              const buf = await file.arrayBuffer();
              await fetch(`/api/downloads/playlists/${playlistId}/cover`, { method: 'POST', body: buf });
              onCoverChange();
            }} />
          </label>
        )}
      </div>
    );
  }

  // Spotify-style 2x2 grid from first 4 track artworks
  const arts = tracks.slice(0, 4).map(t => t?.artwork_url?.replace('-large', '-t200x200'));
  const half = size / 2;

  const overlay = onCoverChange && playlistId ? (
    <label className="absolute inset-0 rounded-lg bg-black/60 opacity-0 group-hover:opacity-100 flex items-center justify-center cursor-pointer transition-opacity">
      <span className="text-[10px] font-mono text-white">SET COVER</span>
      <input type="file" accept="image/*" className="hidden" onChange={async (e) => {
        const file = e.target.files?.[0];
        if (!file || !playlistId) return;
        const buf = await file.arrayBuffer();
        await fetch(`/api/downloads/playlists/${playlistId}/cover`, { method: 'POST', body: buf });
        onCoverChange();
      }} />
    </label>
  ) : null;

  if (arts.filter(Boolean).length === 0) {
    return (
      <div className="relative group rounded-lg bg-[var(--color-surface-3)] flex items-center justify-center"
        style={{ width: size, height: size }}>
        <Play size={size / 4} className="text-[var(--color-text-dim)] opacity-30" />
        {overlay}
      </div>
    );
  }

  if (arts.filter(Boolean).length < 4) {
    return (
      <div className="relative group">
        <img src={arts.find(Boolean) || ''} alt=""
          className="rounded-lg object-cover bg-[var(--color-surface-3)]"
          style={{ width: size, height: size }} />
        {overlay}
      </div>
    );
  }

  return (
    <div className="relative group rounded-lg overflow-hidden"
      style={{ width: size, height: size }}>
      <div className="grid grid-cols-2 grid-rows-2" style={{ width: size, height: size }}>
        {arts.slice(0, 4).map((url, i) => (
          <img key={i} src={url || ''} alt=""
            className="object-cover bg-[var(--color-surface-3)]"
            style={{ width: half, height: half }} />
        ))}
      </div>
      {overlay}
    </div>
  );
}

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
  const [showAddTracks, setShowAddTracks] = useState(false);
  const [addSearch, setAddSearch] = useState('');
  const player = usePlayer();
  const location = useLocation();

  // Reset to grid view when navigating to /playlists
  useEffect(() => {
    setExpanded(null);
    setShowAddTracks(false);
  }, [location.key]);

  useEffect(() => {
    api.getPlaylists().then(setPlaylists);
    fetch('/api/downloads/?limit=1000').then(r => r.json()).then(setAllTracks);
  }, []);

  useEffect(() => {
    if (expanded) {
      const pl = playlists.find(p => p.id === expanded);
      if (pl && allTracks.length) {
        const map = new Map(allTracks.map(t => [t.track_id, t]));
        const plTracks = pl.track_ids.map((id: number) => map.get(id)).filter(Boolean);
        // Fetch tags for each track
        Promise.all(plTracks.map((t: any) =>
          api.getTrackTags(t.track_id).then(tags => ({ ...t, track_tags: tags }))
        )).then(setTracks);
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
      const folder = prompt('Export folder path:');
      if (!folder) return;
      await api.createPlaylist(pl.name, pl.track_ids, folder);
    }
  };

  const createPlaylist = async () => {
    if (!newName.trim()) return;
    const name = newName.trim();
    await api.createPlaylist(name, []);
    setNewName('');
    setShowCreate(false);
    const updated = await api.getPlaylists();
    setPlaylists(updated);
    // Find the newly created playlist (empty, matching name)
    const newest = updated.find((p: any) => p.name === name && p.track_count === 0)
      || updated[updated.length - 1];
    if (newest) {
      setExpanded(newest.id);
      setShowAddTracks(true);
    }
  };

  // Build track map for cover art
  const trackMap = new Map(allTracks.map(t => [t.track_id, t]));
  const getPlaylistTracks = (pl: any) => (pl.track_ids || []).map((id: number) => trackMap.get(id)).filter(Boolean);

  const formatSize = (b: number) => b >= 1e6 ? `${(b/1e6).toFixed(1)}MB` : b >= 1e3 ? `${(b/1e3).toFixed(0)}KB` : '—';

  // Grid view (no playlist expanded)
  if (!expanded) {
    return (
      <div>
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-mono font-bold tracking-wider glow-text">PLAYLISTS</h2>
          <button onClick={() => setShowCreate(true)}
            className="glow-btn px-4 py-2 rounded text-[11px] font-mono flex items-center gap-2">
            <Plus size={12} /> NEW PLAYLIST
          </button>
        </div>

        {showCreate && (
          <div className="mb-5 bg-[var(--color-surface-2)] border border-[var(--color-border)] glow-border rounded p-4">
            <div className="flex gap-2">
              <input value={newName} onChange={e => setNewName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && createPlaylist()}
                placeholder="Playlist name..."
                className="flex-1 bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-3 py-2 text-xs font-mono text-[var(--color-text)] focus:outline-none focus:border-[var(--color-border-glow)]"
                autoFocus />
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

        {/* Spotify-style grid */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {playlists.map(pl => {
            const plTracks = getPlaylistTracks(pl);
            return (
              <div key={pl.id}
                className="group bg-[var(--color-surface-2)] rounded-lg border border-[var(--color-border)] p-3 hover:border-[var(--color-border-glow)] hover:bg-[var(--color-surface-3)] transition-all cursor-pointer"
                onClick={() => setExpanded(pl.id)}>
                <PlaylistCover tracks={plTracks} size={180} coverPath={pl.cover_path} playlistId={pl.id} />
                <div className="mt-3">
                  <div className="text-xs font-mono font-bold text-[var(--color-text)] truncate">{pl.name}</div>
                  <div className="text-[10px] font-mono text-[var(--color-text-dim)]">{pl.track_count} tracks</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Expanded playlist detail view
  const currentPl = playlists.find(p => p.id === expanded);
  if (!currentPl) return null;
  const plTracks = getPlaylistTracks(currentPl);

  return (
    <div>
      {/* Playlist header */}
      <div className="flex items-start gap-6 mb-6">
        <PlaylistCover tracks={plTracks} size={200} coverPath={currentPl.cover_path} playlistId={currentPl.id}
          onCoverChange={() => api.getPlaylists().then(setPlaylists)} />
        <div className="flex-1 min-w-0 pt-2">
          <button onClick={() => setExpanded(null)}
            className="text-[10px] font-mono text-[var(--color-text-dim)] hover:text-[var(--color-glow)] mb-2 transition-colors">
            &larr; ALL PLAYLISTS
          </button>
          {renaming === currentPl.id ? (
            <div className="flex items-center gap-2 mb-2">
              <input value={renameVal} onChange={e => setRenameVal(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && rename(currentPl.id)}
                className="bg-[var(--color-surface)] border border-[var(--color-border-glow)] rounded px-3 py-1.5 text-lg font-mono font-bold text-[var(--color-text)]"
                autoFocus />
              <button onClick={() => rename(currentPl.id)} className="text-green-400"><Check size={16} /></button>
              <button onClick={() => setRenaming(null)} className="text-[var(--color-text-dim)]"><X size={16} /></button>
            </div>
          ) : (
            <h2 className="text-2xl font-mono font-bold text-[var(--color-text)] mb-1">{currentPl.name}</h2>
          )}
          <div className="text-[11px] font-mono text-[var(--color-text-dim)] mb-4">
            {currentPl.track_count} tracks
          </div>
          <div className="flex items-center gap-2">
            {tracks.length > 0 && (
              <button onClick={() => player.playFromQueue(tracks as PlayerTrack[], 0)}
                className="glow-btn px-5 py-2 rounded-full text-[11px] font-mono flex items-center gap-2">
                <Play size={14} /> PLAY ALL
              </button>
            )}
            <button onClick={() => setShowAddTracks(!showAddTracks)}
              className="px-4 py-2 rounded-full text-[11px] font-mono border border-[var(--color-border)] text-[var(--color-text-dim)] hover:text-[var(--color-glow)] hover:border-[var(--color-border-glow)] transition-colors flex items-center gap-2">
              <Plus size={14} /> ADD TRACKS
            </button>
            <button onClick={() => { setRenaming(currentPl.id); setRenameVal(currentPl.name); }}
              className="p-2 hover:bg-[var(--color-surface-3)] rounded" title="Rename">
              <Edit3 size={14} className="text-[var(--color-text-dim)]" />
            </button>
            <button onClick={() => exportPlaylist(currentPl)}
              className="p-2 hover:bg-[var(--color-surface-3)] rounded" title="Export to folder">
              <FolderOutput size={14} className="text-[var(--color-text-dim)]" />
            </button>
            <button onClick={() => { api.deletePlaylist(currentPl.id).then(() => { setExpanded(null); api.getPlaylists().then(setPlaylists); }); }}
              className="p-2 hover:bg-red-900/30 rounded" title="Delete">
              <Trash2 size={14} className="text-[var(--color-text-dim)] hover:text-red-400" />
            </button>
          </div>
        </div>
      </div>

      {/* Add tracks panel */}
      {showAddTracks && (
        <div className="mb-4 bg-[var(--color-surface-2)] border border-[var(--color-border)] glow-border rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[11px] font-mono text-[var(--color-glow)]">ADD FROM LIBRARY</span>
            <button onClick={() => setShowAddTracks(false)} className="text-[var(--color-text-dim)]"><X size={14} /></button>
          </div>
          <input value={addSearch} onChange={e => setAddSearch(e.target.value)}
            placeholder="Search tracks..."
            className="w-full bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-3 py-2 text-xs font-mono text-[var(--color-text)] placeholder-[var(--color-text-dim)] focus:outline-none focus:border-[var(--color-border-glow)] mb-3" />
          <div className="max-h-[300px] overflow-y-auto space-y-0.5">
            {allTracks
              .filter(t => !currentPl.track_ids.includes(t.track_id))
              .filter(t => !addSearch || (t.title||'').toLowerCase().includes(addSearch.toLowerCase()) || (t.artist||'').toLowerCase().includes(addSearch.toLowerCase()))
              .slice(0, 50)
              .map((t: any) => (
                <div key={t.track_id}
                  className="flex items-center gap-2 px-3 py-1.5 rounded hover:bg-[var(--color-surface-3)] transition-colors">
                  {t.artwork_url ? (
                    <img src={t.artwork_url.replace('-large', '-small')} alt=""
                      className="w-7 h-7 rounded object-cover shrink-0 bg-[var(--color-surface-3)]" />
                  ) : (
                    <div className="w-7 h-7 rounded bg-[var(--color-surface-3)] shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] font-mono text-[var(--color-text)] truncate">{t.title}</div>
                    <div className="text-[9px] font-mono text-[var(--color-text-dim)] truncate">{t.artist}</div>
                  </div>
                  {t.bpm && <span className="text-[9px] font-mono text-[var(--color-glow)]">{Math.round(t.bpm)}</span>}
                  {t.camelot_key && <span className="text-[9px] font-mono text-[var(--color-glow)] w-6">{t.camelot_key}</span>}
                  <button onClick={async () => {
                    const newIds = [...currentPl.track_ids, t.track_id];
                    await api.updatePlaylist(currentPl.id, { track_ids: newIds });
                    api.getPlaylists().then(setPlaylists);
                  }}
                    className="glow-btn px-2 py-0.5 rounded text-[9px] font-mono shrink-0">ADD</button>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Track table */}
      <div className="bg-[var(--color-surface-2)] rounded border border-[var(--color-border)] overflow-hidden">
        {tracks.length === 0 && (
          <p className="px-4 py-10 text-center text-[11px] font-mono text-[var(--color-text-dim)]">
            EMPTY — Select tracks in the Library and click PLAYLIST to add
          </p>
        )}
        {tracks.length > 0 && (
          <table className="w-full text-[11px] font-mono">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-[var(--color-text-dim)]">
                <th className="w-6 px-1"></th>
                <th className="w-6 px-1 py-2.5">#</th>
                <th className="w-8"></th>
                <th className="text-left px-2 py-2.5 tracking-wider">TITLE</th>
                <th className="text-left px-2 py-2.5 tracking-wider">ARTIST</th>
                <th className="text-right px-2 py-2.5 tracking-wider">BPM</th>
                <th className="text-center px-2 py-2.5 tracking-wider">NRG</th>
                <th className="text-left px-2 py-2.5 tracking-wider">KEY</th>
                <th className="text-left px-2 py-2.5 tracking-wider">GENRE</th>
                <th className="text-left px-2 py-2.5 tracking-wider">TAGS</th>
                <th className="text-center px-2 py-2.5 tracking-wider">QUALITY</th>
                <th className="text-right px-2 py-2.5 tracking-wider">SIZE</th>
                <th className="w-6"></th>
              </tr>
            </thead>
            <tbody>
              {tracks.map((t: any, i: number) => {
                const isActive = player.playingTrack?.track_id === t.track_id;
                const isPlaying = isActive && player.isPlaying;
                return (
                  <tr key={`${t.track_id}-${i}`}
                    draggable
                    onDragStart={() => setDragIdx(i)}
                    onDragOver={e => { e.preventDefault(); setDragOverIdx(i); }}
                    onDragEnd={() => handleDragEnd(currentPl.id)}
                    className={`border-b border-[var(--color-border)]/30 last:border-0 transition-colors cursor-grab active:cursor-grabbing ${
                      dragOverIdx === i && dragIdx !== null && dragIdx !== i ? 'bg-[var(--color-glow-dim)]' : isActive ? 'bg-[var(--color-glow-dim)]/50' : 'hover:bg-[var(--color-surface-3)]'
                    }`}>
                    <td className="px-1 py-2">
                      <GripVertical size={12} className="text-[var(--color-text-dim)]" />
                    </td>
                    <td className="px-1 py-2 text-right text-[10px] text-[var(--color-text-dim)]">{i + 1}</td>
                    <td className="px-1 py-2">
                      <button onClick={() => player.playFromQueue(tracks as PlayerTrack[], i)}
                        className={`p-1 rounded-full ${isActive ? 'text-[var(--color-glow)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-glow)]'}`}>
                        {isPlaying ? <Pause size={12} /> : <Play size={12} />}
                      </button>
                    </td>
                    <td className="px-2 py-2 max-w-[240px]">
                      <div className="flex items-center gap-2.5">
                        {t.artwork_url ? (
                          <img src={t.artwork_url.replace('-large', '-small')} alt=""
                            className="w-8 h-8 rounded object-cover shrink-0 bg-[var(--color-surface-3)]" />
                        ) : (
                          <div className="w-8 h-8 rounded bg-[var(--color-surface-3)] shrink-0" />
                        )}
                        <span className="truncate text-[var(--color-text)]">{t.title || 'Unknown'}</span>
                      </div>
                    </td>
                    <td className="px-2 py-2 max-w-[120px] truncate text-[var(--color-text-dim)]">{t.artist || ''}</td>
                    <td className="px-2 py-2 text-right">
                      {t.bpm ? <span className="text-[var(--color-glow)]">{Math.round(t.bpm)}</span> : <span className="text-[var(--color-text-dim)]">—</span>}
                    </td>
                    <td className="px-2 py-2 text-center">
                      {t.energy ? (
                        <span className={`font-bold text-[10px] ${t.energy >= 7 ? 'text-red-400' : t.energy >= 4 ? 'text-yellow-400' : 'text-cyan-400'}`}>
                          {t.energy}
                        </span>
                      ) : <span className="text-[var(--color-text-dim)]">—</span>}
                    </td>
                    <td className="px-2 py-2">
                      {t.camelot_key ? <span className="text-[var(--color-glow)]">{t.camelot_key}</span> : <span className="text-[var(--color-text-dim)]">—</span>}
                    </td>
                    <td className="px-2 py-2 text-[var(--color-text-dim)]">{t.genre_folder || ''}</td>
                    <td className="px-2 py-2">
                      <div className="flex items-center gap-1 flex-wrap">
                        {(t.track_tags || []).map((tag: any) => (
                          <span key={tag.id} className="px-1.5 py-0 rounded text-[9px] font-mono"
                            style={{ background: tag.color + '30', borderLeft: `2px solid ${tag.color}` }}>
                            {tag.name}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-2 py-2 text-center">
                      {t.bitrate ? (
                        <span className={`text-[9px] font-bold ${
                          t.bitrate >= 320 || t.audio_format === 'wav' || t.audio_format === 'flac' ? 'text-[var(--color-glow)]' :
                          t.bitrate >= 256 ? 'text-yellow-400' : 'text-red-400'
                        }`}>
                          {t.audio_format?.toUpperCase()} {t.bitrate}
                        </span>
                      ) : <span className="text-[var(--color-text-dim)] text-[9px]">—</span>}
                    </td>
                    <td className="px-2 py-2 text-right text-[var(--color-text-dim)]">
                      {t.file_size_bytes ? formatSize(t.file_size_bytes) : '—'}
                    </td>
                    <td className="px-1 py-2">
                      <button onClick={() => remove(currentPl.id, i)}
                        className="text-[var(--color-text-dim)] hover:text-red-400">
                        <X size={12} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
