import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Trash2, ChevronLeft, ChevronRight, Search, Loader2, Play, Pause, Edit3, Check, X, ListPlus, AudioWaveform, Zap, Upload, FolderOpen, ToggleLeft, ToggleRight, Sparkles, Tag, Plus } from 'lucide-react';
import { api } from '../api/client';
import { usePlayer, type PlayerTrack } from '../components/PlayerContext';
import TrackDetail from '../components/TrackDetail';

export default function Downloads() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [downloads, setDownloads] = useState<any[]>([]);
  const [genres, setGenres] = useState<string[]>([]);
  const [selectedGenre, setSelectedGenre] = useState(searchParams.get('genre') || '');
  const [stats, setStats] = useState<any>(null);
  const [page, setPage] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [detailTrack, setDetailTrack] = useState<any>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editData, setEditData] = useState({ title: '', artist: '', genre: '' });
  const [showPlaylist, setShowPlaylist] = useState(false);
  const [playlistName, setPlaylistName] = useState('');
  const [exportFolder, setExportFolder] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeMsg, setAnalyzeMsg] = useState('');
  const [showImport, setShowImport] = useState(false);
  const [importPath, setImportPath] = useState('');
  const [importGenre, setImportGenre] = useState('imported');
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState('');
  const [camelotMode, setCamelotMode] = useState(true);
  const [findingTastemakers, setFindingTastemakers] = useState(false);
  const [tastemakerMsg, setTastemakerMsg] = useState('');
  const [tags, setTags] = useState<any[]>([]);
  const [selectedTag, setSelectedTag] = useState<number | null>(null);
  const [showTagMenu, setShowTagMenu] = useState<number | null>(null);
  const [trackTagsMap, setTrackTagsMap] = useState<Record<number, any[]>>({});
  const [showCreateTag, setShowCreateTag] = useState(false);
  const [newTagName, setNewTagName] = useState('');
  const [newTagColor, setNewTagColor] = useState('#00ffc8');
  const player = usePlayer();
  const pageSize = 30;

  useEffect(() => {
    api.getDownloadStats().then(s => { setStats(s); setGenres(Object.keys(s.by_genre || {})); });
    loadTags();
  }, []);

  const loadTags = () => api.getTags().then(setTags);

  // Load tags for visible tracks
  useEffect(() => {
    downloads.forEach(d => {
      if (!trackTagsMap[d.track_id]) {
        api.getTrackTags(d.track_id).then(t => {
          setTrackTagsMap(prev => ({ ...prev, [d.track_id]: t }));
        });
      }
    });
  }, [downloads]);

  useEffect(() => {
    const g = searchParams.get('genre') || '';
    if (g !== selectedGenre) { setSelectedGenre(g); setPage(0); }
  }, [searchParams]);

  useEffect(() => { loadDownloads(); }, [selectedGenre, page]);

  const loadDownloads = () => {
    api.getDownloads(selectedGenre || undefined, pageSize, page * pageSize).then(setDownloads);
  };

  const changeGenre = (g: string) => {
    setSelectedGenre(g); setPage(0);
    g ? setSearchParams({ genre: g }) : setSearchParams({});
  };

  const deleteDownload = async (id: number) => { await api.deleteDownload(id); loadDownloads(); };

  const startEdit = (d: any) => {
    setEditingId(d.track_id);
    setEditData({ title: d.title || '', artist: d.artist || '', genre: d.genre_folder || '' });
  };

  const saveEdit = async () => {
    if (!editingId) return;
    await api.editMetadata(editingId, editData);
    setEditingId(null);
    loadDownloads();
  };

  const toggleSelect = (tid: number) => {
    const next = new Set(selected);
    if (next.has(tid)) next.delete(tid); else next.add(tid);
    setSelected(next);
  };

  const createPlaylist = async () => {
    if (!playlistName.trim() || !selected.size) return;
    await api.createPlaylist(playlistName, Array.from(selected), exportFolder || undefined);
    setShowPlaylist(false); setPlaylistName(''); setExportFolder('');
    navigate('/playlists');
  };

  // Analyze
  const analyzeSelected = () => startAnalysis({ track_ids: Array.from(selected) });
  const analyzeAll = () => startAnalysis({ all_unanalyzed: true });

  const startAnalysis = async (body: any) => {
    setAnalyzing(true);
    setAnalyzeMsg('Starting...');
    const res = await fetch('/api/analysis/analyze', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const { task_id } = await res.json();
    const poll = setInterval(async () => {
      const status = await fetch(`/api/analysis/status/${task_id}`).then(r => r.json());
      setAnalyzeMsg(status.message || status.status);
      if (status.status === 'completed' || status.status === 'failed') {
        clearInterval(poll);
        setAnalyzing(false);
        loadDownloads();
        if (status.result) setAnalyzeMsg(`Done: ${status.result.success} analyzed`);
      }
    }, 2000);
  };

  const findTastemakers = async () => {
    setFindingTastemakers(true);
    setTastemakerMsg('Scanning...');
    const body: any = { min_overlap: 1 };
    if (selected.size > 0) body.track_ids = Array.from(selected);
    else body.sample_size = 20;

    const res = await fetch('/api/accounts/tastemakers', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const { task_id } = await res.json();
    const poll = setInterval(async () => {
      const status = await fetch(`/api/accounts/tastemakers/status/${task_id}`).then(r => r.json());
      setTastemakerMsg(status.message || status.status);
      if (status.status === 'completed' || status.status === 'failed') {
        clearInterval(poll);
        setFindingTastemakers(false);
        if (status.result) setTastemakerMsg(`Found ${status.result.found} tastemakers → go to Channels to review`);
        if (status.error) setTastemakerMsg(`Error: ${status.error}`);
      }
    }, 2000);
  };

  const exportRekordbox = async () => {
    const body: any = {};
    if (selected.size > 0) body.track_ids = Array.from(selected);
    const res = await fetch('/api/analysis/export-rekordbox', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    setAnalyzeMsg(data.error ? `Error: ${data.error}` : `Exported ${data.exported} tracks (XML)`);
  };

  const exportUSB = async () => {
    // Open native folder picker
    const res = await fetch('/api/pick-folder');
    const data = await res.json();
    if (!data.path) return;

    setAnalyzeMsg('Exporting to USB...');
    const trackIds = selected.size > 0 ? Array.from(selected) : undefined;
    const { task_id } = await api.exportUSB(data.path, trackIds);

    const poll = setInterval(async () => {
      const status = await fetch(`/api/analysis/status/${task_id}`).then(r => r.json());
      setAnalyzeMsg(status.message || status.status);
      if (status.status === 'completed' || status.status === 'failed') {
        clearInterval(poll);
        if (status.result) setAnalyzeMsg(`CDJ export: ${status.result.exported} tracks to ${status.result.path}`);
        if (status.error) setAnalyzeMsg(`Error: ${status.error}`);
      }
    }, 2000);
  };

  const importFiles = async () => {
    if (!importPath.trim()) return;
    setImporting(true);
    const res = await fetch('/api/analysis/import-folder', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder_path: importPath, genre_folder: importGenre }),
    });
    const data = await res.json();
    setImportMsg(data.error ? `Error: ${data.error}` : `Imported ${data.imported}, ${data.skipped} skipped`);
    setImporting(false);
    loadDownloads();
  };

  const createTag = async () => {
    if (!newTagName.trim()) return;
    await api.createTag(newTagName.trim(), newTagColor);
    setNewTagName('');
    setShowCreateTag(false);
    loadTags();
  };

  const assignTag = async (trackId: number, tagId: number) => {
    await api.tagTrack(trackId, tagId);
    const updated = await api.getTrackTags(trackId);
    setTrackTagsMap(prev => ({ ...prev, [trackId]: updated }));
    setShowTagMenu(null);
    loadTags();
  };

  const removeTag = async (trackId: number, tagId: number) => {
    await api.untagTrack(trackId, tagId);
    const updated = await api.getTrackTags(trackId);
    setTrackTagsMap(prev => ({ ...prev, [trackId]: updated }));
    loadTags();
  };

  const formatSize = (b: number | null) => { if (!b) return '-'; return b >= 1e6 ? `${(b/1e6).toFixed(1)}MB` : `${(b/1e3).toFixed(0)}KB`; };

  let filtered = searchQuery
    ? downloads.filter(d => (d.title||'').toLowerCase().includes(searchQuery.toLowerCase()) || (d.artist||'').toLowerCase().includes(searchQuery.toLowerCase()))
    : downloads;

  // Filter by tag
  if (selectedTag) {
    filtered = filtered.filter(d => {
      const tt = trackTagsMap[d.track_id];
      return tt && tt.some((t: any) => t.id === selectedTag);
    });
  }

  const analyzedCount = downloads.filter(d => d.bpm != null).length;
  const unanalyzedCount = downloads.filter(d => d.bpm == null && d.file_path).length;

  return (
    <div>
      <h2 className="text-xl font-mono font-bold tracking-wider mb-6 glow-text">LIBRARY</h2>

      {/* Track Detail Panel — at the TOP */}
      {detailTrack && (
        <div className="mb-5">
          <TrackDetail
            track={detailTrack}
            onClose={() => setDetailTrack(null)}
            onAnalyzed={() => { loadDownloads(); }}
          />
        </div>
      )}

      {/* Toolbar row 1 */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <select value={selectedGenre} onChange={e => changeGenre(e.target.value)}
          className="bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-3 py-2 text-xs font-mono text-[var(--color-text)]">
          <option value="">ALL GENRES</option>
          {genres.map(g => <option key={g} value={g}>{g.toUpperCase()}</option>)}
        </select>

        <div className="flex-1 relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-dim)]" />
          <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
            placeholder="Filter by title or artist..."
            className="w-full bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded pl-9 pr-3 py-2 text-xs font-mono text-[var(--color-text)] placeholder-[var(--color-text-dim)] focus:outline-none focus:border-[var(--color-border-glow)]" />
        </div>

        <button onClick={() => setCamelotMode(!camelotMode)}
          className="flex items-center gap-1 text-[10px] font-mono text-[var(--color-text-dim)] hover:text-[var(--color-glow)]">
          {camelotMode ? <ToggleRight size={13} className="text-[var(--color-glow)]" /> : <ToggleLeft size={13} />}
          {camelotMode ? 'CAM' : 'KEY'}
        </button>

        {stats && <span className="text-[10px] font-mono text-[var(--color-text-dim)]">{stats.total} TRACKS</span>}
      </div>

      {/* Toolbar row 2 — actions */}
      <div className="flex items-center gap-2 mb-5 flex-wrap">
        {selected.size > 0 && (
          <>
            <button onClick={() => setShowPlaylist(true)}
              className="glow-btn px-3 py-1.5 rounded text-[10px] font-mono flex items-center gap-1.5">
              <ListPlus size={11} /> PLAYLIST ({selected.size})
            </button>
            <button onClick={analyzeSelected} disabled={analyzing}
              className="glow-btn px-3 py-1.5 rounded text-[10px] font-mono flex items-center gap-1.5">
              {analyzing ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
              ANALYZE ({selected.size})
            </button>
            <button onClick={findTastemakers} disabled={findingTastemakers}
              className="px-3 py-1.5 rounded text-[10px] font-mono flex items-center gap-1.5 border border-purple-500/40 text-purple-400 bg-purple-500/10 hover:bg-purple-500/20 transition-colors disabled:opacity-50">
              {findingTastemakers ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
              TASTEMAKERS ({selected.size})
            </button>
          </>
        )}

        {unanalyzedCount > 0 && (
          <button onClick={analyzeAll} disabled={analyzing}
            className="px-3 py-1.5 rounded text-[10px] font-mono flex items-center gap-1.5 border border-[var(--color-border)] text-[var(--color-text-dim)] hover:text-[var(--color-glow)] hover:border-[var(--color-border-glow)] transition-colors">
            {analyzing ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
            ANALYZE ALL ({unanalyzedCount})
          </button>
        )}

        <button onClick={() => setShowImport(!showImport)}
          className="px-3 py-1.5 rounded text-[10px] font-mono flex items-center gap-1.5 border border-[var(--color-border)] text-[var(--color-text-dim)] hover:text-[var(--color-text)] hover:border-[var(--color-border-glow)] transition-colors">
          <FolderOpen size={11} /> IMPORT
        </button>

        {analyzedCount > 0 && (
          <>
            <button onClick={exportRekordbox}
              className="px-3 py-1.5 rounded text-[10px] font-mono flex items-center gap-1.5 border border-[var(--color-border)] text-[var(--color-text-dim)] hover:text-[var(--color-text)] hover:border-[var(--color-border-glow)] transition-colors">
              <Upload size={11} /> REKORDBOX XML
            </button>
            <button onClick={exportUSB}
              className="px-3 py-1.5 rounded text-[10px] font-mono flex items-center gap-1.5 border border-orange-500/40 text-orange-400 bg-orange-500/10 hover:bg-orange-500/20 transition-colors">
              <Upload size={11} /> CDJ USB
            </button>
          </>
        )}

        <div className="flex-1" />
        {analyzeMsg && <span className="text-[10px] font-mono text-[var(--color-glow)]">{analyzeMsg}</span>}
        {tastemakerMsg && (
          <span className="text-[10px] font-mono text-purple-400 flex items-center gap-2">
            {findingTastemakers && <Loader2 size={10} className="animate-spin" />}
            {tastemakerMsg}
            {!findingTastemakers && tastemakerMsg.includes('Found') && (
              <button onClick={() => navigate('/accounts')} className="underline hover:text-purple-300">VIEW →</button>
            )}
          </span>
        )}
        {tastemakerMsg && (
          <span className="text-[10px] font-mono text-purple-400 flex items-center gap-2">
            {findingTastemakers && <Loader2 size={10} className="animate-spin" />}
            {tastemakerMsg}
            {!findingTastemakers && tastemakerMsg.includes('Found') && (
              <button onClick={() => navigate('/accounts')} className="underline hover:text-purple-300">VIEW →</button>
            )}
          </span>
        )}
      </div>

      {/* Import panel */}
      {showImport && (
        <div className="mb-4 bg-[var(--color-surface-2)] border border-[var(--color-border)] glow-border rounded p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-mono text-[var(--color-glow)]">IMPORT AUDIO FILES</span>
            <button onClick={() => setShowImport(false)} className="text-[var(--color-text-dim)]"><X size={14} /></button>
          </div>
          <div className="flex gap-2">
            <input value={importPath} onChange={e => setImportPath(e.target.value)} placeholder="Folder path"
              className="flex-1 bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-3 py-2 text-xs font-mono text-[var(--color-text)] placeholder-[var(--color-text-dim)]" />
            <button onClick={async () => { const r = await fetch('/api/pick-folder'); const d = await r.json(); if (d.path) setImportPath(d.path); }}
              className="px-3 py-2 rounded text-[10px] font-mono border border-[var(--color-border)] text-[var(--color-text-dim)] hover:text-[var(--color-text)]">BROWSE</button>
            <input value={importGenre} onChange={e => setImportGenre(e.target.value)} placeholder="Genre"
              className="w-28 bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-3 py-2 text-xs font-mono text-[var(--color-text)]" />
            <button onClick={importFiles} disabled={importing} className="glow-btn px-4 py-2 rounded text-[11px] font-mono disabled:opacity-40">
              {importing ? <Loader2 size={12} className="animate-spin" /> : 'IMPORT'}
            </button>
          </div>
          {importMsg && <p className="text-[10px] font-mono text-[var(--color-glow)] mt-2">{importMsg}</p>}
        </div>
      )}

      {/* Playlist creation modal */}
      {showPlaylist && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50" onClick={() => setShowPlaylist(false)}>
          <div className="bg-[var(--color-surface-2)] border border-[var(--color-border)] glow-border rounded-lg w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-mono font-bold glow-text">CREATE PLAYLIST</span>
              <button onClick={() => setShowPlaylist(false)} className="text-[var(--color-text-dim)]"><X size={16} /></button>
            </div>
            <div className="space-y-3">
              <input value={playlistName} onChange={e => setPlaylistName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && createPlaylist()} placeholder="Playlist name"
                className="w-full bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-3 py-2 text-xs font-mono text-[var(--color-text)]" />
              <div className="flex gap-2">
                <input value={exportFolder} onChange={e => setExportFolder(e.target.value)} placeholder="Export folder (optional)"
                  className="flex-1 bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-3 py-2 text-xs font-mono text-[var(--color-text)] placeholder-[var(--color-text-dim)]" />
                <button onClick={async () => { const r = await fetch('/api/pick-folder'); const d = await r.json(); if (d.path) setExportFolder(d.path); }}
                  className="px-3 py-2 rounded text-[10px] font-mono border border-[var(--color-border)] text-[var(--color-text-dim)]">BROWSE</button>
              </div>
              <p className="text-[11px] font-mono text-[var(--color-text-dim)]">{selected.size} tracks</p>
              <button onClick={createPlaylist} disabled={!playlistName.trim()}
                className="glow-btn w-full px-4 py-2.5 rounded text-[11px] font-mono disabled:opacity-40">CREATE</button>
            </div>
          </div>
        </div>
      )}

      {/* Tags */}
      {tags.length > 0 && (
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <Tag size={12} className="text-[var(--color-text-dim)]" />
          <button onClick={() => setSelectedTag(null)}
            className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${!selectedTag ? 'bg-[var(--color-surface-3)] text-[var(--color-text)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-text)]'}`}>
            ALL
          </button>
          {tags.map(tag => (
            <button key={tag.id} onClick={() => setSelectedTag(selectedTag === tag.id ? null : tag.id)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono flex items-center gap-1 transition-colors ${
                selectedTag === tag.id ? 'text-[var(--color-text)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-text)]'
              }`}
              style={{ borderLeft: `3px solid ${tag.color}`, background: selectedTag === tag.id ? tag.color + '20' : 'transparent' }}>
              {tag.name} <span className="opacity-50">{tag.track_count}</span>
            </button>
          ))}
          <button onClick={() => setShowCreateTag(!showCreateTag)}
            className="p-1 text-[var(--color-text-dim)] hover:text-[var(--color-glow)]" title="New tag">
            <Plus size={12} />
          </button>
          {showCreateTag && (
            <div className="flex items-center gap-1">
              <input type="color" value={newTagColor} onChange={e => setNewTagColor(e.target.value)}
                className="w-6 h-6 rounded border-none cursor-pointer" />
              <input value={newTagName} onChange={e => setNewTagName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && createTag()}
                placeholder="Tag name"
                className="w-24 bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-2 py-0.5 text-[10px] font-mono text-[var(--color-text)]" />
              <button onClick={createTag} className="text-[10px] font-mono text-[var(--color-glow)]">ADD</button>
            </div>
          )}
        </div>
      )}

      {tags.length === 0 && (
        <div className="flex items-center gap-2 mb-4">
          <button onClick={() => setShowCreateTag(!showCreateTag)}
            className="flex items-center gap-1.5 px-3 py-1 rounded text-[10px] font-mono border border-[var(--color-border)] text-[var(--color-text-dim)] hover:text-[var(--color-text)] hover:border-[var(--color-border-glow)] transition-colors">
            <Tag size={11} /> CREATE TAGS
          </button>
          {showCreateTag && (
            <div className="flex items-center gap-1">
              <input type="color" value={newTagColor} onChange={e => setNewTagColor(e.target.value)}
                className="w-6 h-6 rounded border-none cursor-pointer" />
              <input value={newTagName} onChange={e => setNewTagName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && createTag()}
                placeholder="Tag name"
                className="w-24 bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-2 py-0.5 text-[10px] font-mono text-[var(--color-text)]" />
              <button onClick={createTag} className="text-[10px] font-mono text-[var(--color-glow)]">ADD</button>
            </div>
          )}
        </div>
      )}

      {/* Genre pills */}
      {!selectedGenre && !selectedTag && genres.length > 0 && (
        <div className="flex gap-2 mb-4 flex-wrap">
          {genres.map(g => (
            <button key={g} onClick={() => changeGenre(g)}
              className="px-3 py-1 rounded text-[10px] font-mono border border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text-dim)] hover:text-[var(--color-text)] hover:border-[var(--color-border-glow)] transition-colors">
              {g.toUpperCase()} <span className="ml-1 text-[var(--color-glow)] opacity-60">{stats?.by_genre?.[g] || 0}</span>
            </button>
          ))}
        </div>
      )}

      {/* Track table */}
      <div className="bg-[var(--color-surface-2)] rounded border border-[var(--color-border)] overflow-hidden">
        <table className="w-full text-[11px] font-mono">
          <thead>
            <tr className="border-b border-[var(--color-border)] text-[var(--color-text-dim)]">
              <th className="w-8 px-2 py-2.5">
                <input type="checkbox" checked={selected.size === filtered.length && filtered.length > 0}
                  onChange={() => selected.size === filtered.length ? setSelected(new Set()) : setSelected(new Set(filtered.map(d => d.track_id)))} />
              </th>
              <th className="w-8"></th>
              <th className="text-left px-2 py-2.5 tracking-wider">TITLE</th>
              <th className="text-left px-2 py-2.5 tracking-wider">ARTIST</th>
              <th className="text-right px-2 py-2.5 tracking-wider">BPM</th>
              <th className="text-left px-2 py-2.5 tracking-wider">KEY</th>
              <th className="text-left px-2 py-2.5 tracking-wider">GENRE</th>
              <th className="text-left px-2 py-2.5 tracking-wider">TAGS</th>
              <th className="text-right px-2 py-2.5 tracking-wider">SIZE</th>
              <th className="w-20"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((d: any, i: number) => {
              const isEditing = editingId === d.track_id;
              const isActive = player.playingTrack?.track_id === d.track_id;
              const isPlaying = isActive && player.isPlaying;
              const isLoading = isActive && player.isLoading;
              const isDetailOpen = detailTrack?.track_id === d.track_id;
              const hasAnalysis = d.bpm != null;
              const keyDisplay = camelotMode ? d.camelot_key : d.musical_key;

              return (
                <tr key={d.id || i} className={`border-b border-[var(--color-border)]/30 transition-colors ${isDetailOpen ? 'bg-[var(--color-glow-dim)]' : isActive ? 'bg-[var(--color-glow-dim)]/50' : 'hover:bg-[var(--color-surface-3)]'}`}>
                  <td className="px-2 py-2 text-center">
                    <input type="checkbox" checked={selected.has(d.track_id)} onChange={() => toggleSelect(d.track_id)} />
                  </td>
                  <td className="px-1 py-2">
                    <button onClick={() => player.playFromQueue(filtered as PlayerTrack[], i)}
                      className={`p-1 rounded-full transition-all ${isActive ? 'text-[var(--color-glow)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-glow)]'}`}>
                      {isLoading ? <Loader2 size={13} className="animate-spin" /> : isPlaying ? <Pause size={13} /> : <Play size={13} />}
                    </button>
                  </td>
                  <td className="px-2 py-2 max-w-[200px]">
                    {isEditing ? (
                      <input value={editData.title} onChange={e => setEditData({...editData, title: e.target.value})}
                        className="w-full bg-[var(--color-surface)] border border-[var(--color-border-glow)] rounded px-2 py-0.5 text-[11px] font-mono text-[var(--color-text)]" />
                    ) : (
                      <button onClick={() => setDetailTrack(isDetailOpen ? null : d)}
                        className="truncate block text-left w-full text-[var(--color-text)] hover:text-[var(--color-glow)] transition-colors">
                        {d.title || <span className="italic text-[var(--color-text-dim)]">unknown</span>}
                      </button>
                    )}
                  </td>
                  <td className="px-2 py-2 max-w-[130px]">
                    {isEditing ? (
                      <input value={editData.artist} onChange={e => setEditData({...editData, artist: e.target.value})}
                        className="w-full bg-[var(--color-surface)] border border-[var(--color-border-glow)] rounded px-2 py-0.5 text-[11px] font-mono text-[var(--color-text)]" />
                    ) : <span className="truncate block text-[var(--color-text-dim)]">{d.artist || ''}</span>}
                  </td>
                  <td className="px-2 py-2 text-right">
                    {hasAnalysis ? <span className="text-[var(--color-glow)]">{Math.round(d.bpm)}</span> : <span className="text-[var(--color-text-dim)]">—</span>}
                  </td>
                  <td className="px-2 py-2">
                    {hasAnalysis && keyDisplay ? <span className="text-[var(--color-glow)]">{keyDisplay}</span> : <span className="text-[var(--color-text-dim)]">—</span>}
                  </td>
                  <td className="px-2 py-2">
                    {isEditing ? (
                      <input value={editData.genre} onChange={e => setEditData({...editData, genre: e.target.value})}
                        className="w-full bg-[var(--color-surface)] border border-[var(--color-border-glow)] rounded px-2 py-0.5 text-[11px] font-mono text-[var(--color-text)]" />
                    ) : (
                      <button onClick={() => changeGenre(d.genre_folder)} className="text-[var(--color-text-dim)] hover:text-[var(--color-glow)] transition-colors">{d.genre_folder}</button>
                    )}
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex items-center gap-1 flex-wrap relative">
                      {(trackTagsMap[d.track_id] || []).map((tag: any) => (
                        <span key={tag.id}
                          className="px-1.5 py-0 rounded text-[9px] font-mono text-[var(--color-text)] cursor-pointer hover:opacity-70"
                          style={{ background: tag.color + '30', borderLeft: `2px solid ${tag.color}` }}
                          onClick={() => removeTag(d.track_id, tag.id)}
                          title={`Click to remove "${tag.name}"`}>
                          {tag.name}
                        </span>
                      ))}
                      <button onClick={() => setShowTagMenu(showTagMenu === d.track_id ? null : d.track_id)}
                        className="p-0.5 text-[var(--color-text-dim)] hover:text-[var(--color-glow)] transition-colors" title="Add tag">
                        <Plus size={10} />
                      </button>
                      {showTagMenu === d.track_id && tags.length > 0 && (
                        <div className="absolute top-full left-0 mt-1 z-20 bg-[var(--color-surface)] border border-[var(--color-border)] rounded shadow-lg py-1 min-w-[100px]">
                          {tags.filter(tag => !(trackTagsMap[d.track_id] || []).some((tt: any) => tt.id === tag.id)).map(tag => (
                            <button key={tag.id} onClick={() => assignTag(d.track_id, tag.id)}
                              className="w-full text-left px-3 py-1 text-[10px] font-mono text-[var(--color-text-dim)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-3)] flex items-center gap-2">
                              <span className="w-2 h-2 rounded-full" style={{ background: tag.color }} />
                              {tag.name}
                            </button>
                          ))}
                          {tags.filter(tag => !(trackTagsMap[d.track_id] || []).some((tt: any) => tt.id === tag.id)).length === 0 && (
                            <span className="px-3 py-1 text-[9px] font-mono text-[var(--color-text-dim)]">All tags assigned</span>
                          )}
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-2 py-2 text-right text-[var(--color-text-dim)]">{formatSize(d.file_size_bytes)}</td>
                  <td className="px-2 py-2">
                    <div className="flex items-center gap-0.5">
                      {isEditing ? (
                        <>
                          <button onClick={saveEdit} className="p-1 hover:bg-green-900/30 rounded"><Check size={12} className="text-green-400" /></button>
                          <button onClick={() => setEditingId(null)} className="p-1"><X size={12} className="text-[var(--color-text-dim)]" /></button>
                        </>
                      ) : (
                        <>
                          <button onClick={() => setDetailTrack(isDetailOpen ? null : d)}
                            className={`p-1 rounded ${isDetailOpen ? 'text-[var(--color-glow)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-glow)]'}`}
                            title="Waveform & Cues"><AudioWaveform size={12} /></button>
                          <button onClick={() => startEdit(d)} className="p-1 hover:bg-[var(--color-surface-3)] rounded" title="Edit"><Edit3 size={12} className="text-[var(--color-text-dim)]" /></button>
                          <button onClick={() => deleteDownload(d.id)} className="p-1 hover:bg-red-900/30 rounded" title="Delete"><Trash2 size={12} className="text-[var(--color-text-dim)] hover:text-red-400" /></button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr><td colSpan={10} className="px-4 py-10 text-center text-[var(--color-text-dim)]">
                {searchQuery ? 'NO MATCHING TRACKS' : 'NO DOWNLOADS FOUND'}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between mt-3 text-[11px] font-mono text-[var(--color-text-dim)]">
        <span>PAGE {page + 1}</span>
        <div className="flex gap-2">
          <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
            className="glow-btn px-3 py-1 rounded disabled:opacity-30 flex items-center gap-1">
            <ChevronLeft size={12} /> PREV
          </button>
          <button onClick={() => setPage(page + 1)} disabled={filtered.length < pageSize}
            className="glow-btn px-3 py-1 rounded disabled:opacity-30 flex items-center gap-1">
            NEXT <ChevronRight size={12} />
          </button>
        </div>
      </div>
    </div>
  );
}
