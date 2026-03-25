import { useEffect, useState } from 'react';
import { Loader2, Zap, Play, Pause, ToggleLeft, ToggleRight, Upload, FolderOpen, X, Plus, Trash2, AudioWaveform } from 'lucide-react';
import { usePlayer, type PlayerTrack } from '../components/PlayerContext';
import WaveformEditor from '../components/WaveformEditor';

interface Cue {
  name: string;
  type: string;
  start: number;
  end: number | null;
  num: number;
  color: string | null;
}

export default function Analyze() {
  const [tracks, setTracks] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [filter, setFilter] = useState<'all' | 'analyzed' | 'unanalyzed'>('all');
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeMsg, setAnalyzeMsg] = useState('');
  const [camelotMode, setCamelotMode] = useState(true);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [exporting, setExporting] = useState(false);
  const [exportMsg, setExportMsg] = useState('');
  const [expandedTrack, setExpandedTrack] = useState<number | null>(null);
  const [cues, setCues] = useState<Cue[]>([]);
  const [showImport, setShowImport] = useState(false);
  const [importPath, setImportPath] = useState('');
  const [importGenre, setImportGenre] = useState('imported');
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState('');
  const player = usePlayer();

  useEffect(() => { loadData(); }, [filter]);

  const loadData = () => {
    const analyzed = filter === 'analyzed' ? true : filter === 'unanalyzed' ? false : undefined;
    fetch(`/api/analysis/tracks?${analyzed !== undefined ? `analyzed=${analyzed}&` : ''}limit=200`)
      .then(r => r.json()).then(setTracks);
    fetch('/api/analysis/stats').then(r => r.json()).then(setStats);
  };

  const analyzeSelected = () => startAnalysis({ track_ids: Array.from(selected) });
  const analyzeAll = () => startAnalysis({ all_unanalyzed: true });
  const analyzeSingle = (trackId: number) => startAnalysis({ track_ids: [trackId] });

  const startAnalysis = async (body: any) => {
    setAnalyzing(true);
    setAnalyzeMsg('Starting analysis...');
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
        loadData();
        if (status.result) setAnalyzeMsg(`Done: ${status.result.success} analyzed, ${status.result.failed} failed`);
      }
    }, 2000);
  };

  const exportToRekordbox = async () => {
    setExporting(true);
    setExportMsg('Exporting...');
    const body: any = {};
    if (selected.size > 0 && selected.size < tracks.length) body.track_ids = Array.from(selected);
    const res = await fetch('/api/analysis/export-rekordbox', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    setExportMsg(data.error ? `Error: ${data.error}` : `Exported ${data.exported} tracks to ${data.path}`);
    setExporting(false);
  };

  // Track detail panel
  const openTrackDetail = async (trackId: number) => {
    if (expandedTrack === trackId) { setExpandedTrack(null); return; }
    setExpandedTrack(trackId);
    const res = await fetch(`/api/analysis/cues/${trackId}`);
    const data = await res.json();
    setCues(data.length ? data : []);
  };

  const addCue = () => setCues([...cues, { name: `Cue ${cues.length + 1}`, type: 'cue', start: 0, end: null, num: cues.length, color: null }]);
  const removeCue = (idx: number) => setCues(cues.filter((_, i) => i !== idx));
  const updateCue = (idx: number, field: string, value: any) => {
    const next = [...cues];
    (next[idx] as any)[field] = value;
    setCues(next);
  };
  const saveCues = async () => {
    await fetch('/api/analysis/cues', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track_id: expandedTrack, cues }),
    });
    loadData();
  };

  // File import
  const importFiles = async () => {
    if (!importPath.trim()) return;
    setImporting(true);
    setImportMsg('Importing...');
    const res = await fetch('/api/analysis/import-folder', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder_path: importPath, genre_folder: importGenre }),
    });
    const data = await res.json();
    setImportMsg(data.error ? `Error: ${data.error}` : `Imported ${data.imported}, ${data.skipped} skipped`);
    setImporting(false);
    loadData();
  };

  const toggleSelect = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const expandedTrackData = tracks.find(t => t.track_id === expandedTrack);

  return (
    <div>
      <h2 className="text-xl font-mono font-bold tracking-wider mb-6 glow-text">ANALYZE</h2>

      {/* Stats */}
      {stats && (
        <div className="flex items-center gap-6 mb-6 text-[11px] font-mono">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-[var(--color-glow)]" />
            <span className="text-[var(--color-glow)]">{stats.analyzed} ANALYZED</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-[var(--color-text-dim)]" />
            <span className="text-[var(--color-text-dim)]">{stats.unanalyzed} PENDING</span>
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <div className="flex gap-1">
          {(['all', 'analyzed', 'unanalyzed'] as const).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded text-[11px] font-mono tracking-wide ${filter === f ? 'bg-[var(--color-surface-3)] text-[var(--color-text)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-text)]'}`}>
              {f.toUpperCase()}
            </button>
          ))}
        </div>

        <button onClick={() => setCamelotMode(!camelotMode)}
          className="flex items-center gap-1.5 text-[10px] font-mono text-[var(--color-text-dim)] hover:text-[var(--color-glow)] transition-colors">
          {camelotMode ? <ToggleRight size={14} className="text-[var(--color-glow)]" /> : <ToggleLeft size={14} />}
          {camelotMode ? 'CAMELOT' : 'TRADITIONAL'}
        </button>

        <div className="flex-1" />

        <button onClick={() => setShowImport(!showImport)}
          className="px-3 py-1.5 rounded text-[11px] font-mono flex items-center gap-1.5 border border-[var(--color-border)] text-[var(--color-text-dim)] hover:text-[var(--color-text)] hover:border-[var(--color-border-glow)] transition-colors">
          <FolderOpen size={12} /> IMPORT
        </button>

        {selected.size > 0 && (
          <button onClick={analyzeSelected} disabled={analyzing}
            className="glow-btn px-4 py-2 rounded text-[11px] font-mono flex items-center gap-2">
            {analyzing ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
            ANALYZE {selected.size}
          </button>
        )}

        {stats?.unanalyzed > 0 && (
          <button onClick={analyzeAll} disabled={analyzing}
            className="glow-btn px-4 py-2 rounded text-[11px] font-mono flex items-center gap-2">
            {analyzing ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
            ANALYZE ALL ({stats.unanalyzed})
          </button>
        )}

        {stats?.analyzed > 0 && (
          <button onClick={exportToRekordbox} disabled={exporting}
            className="px-3 py-1.5 rounded text-[11px] font-mono flex items-center gap-1.5 border border-[var(--color-border)] text-[var(--color-text-dim)] hover:text-[var(--color-text)] hover:border-[var(--color-border-glow)] transition-colors">
            {exporting ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
            EXPORT REKORDBOX
          </button>
        )}
      </div>

      {/* Import panel */}
      {showImport && (
        <div className="mb-5 bg-[var(--color-surface-2)] border border-[var(--color-border)] glow-border rounded p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[11px] font-mono text-[var(--color-glow)]">IMPORT AUDIO FILES</span>
            <button onClick={() => setShowImport(false)} className="text-[var(--color-text-dim)]"><X size={14} /></button>
          </div>
          <div className="flex gap-2">
            <input value={importPath} onChange={e => setImportPath(e.target.value)}
              placeholder="Folder path (e.g., ~/Music/DJ Tracks)"
              className="flex-1 bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-3 py-2 text-xs font-mono text-[var(--color-text)] placeholder-[var(--color-text-dim)] focus:outline-none focus:border-[var(--color-border-glow)]" />
            <button onClick={async () => {
              const res = await fetch('/api/pick-folder'); const data = await res.json();
              if (data.path) setImportPath(data.path);
            }} className="px-3 py-2 rounded text-[10px] font-mono border border-[var(--color-border)] text-[var(--color-text-dim)] hover:text-[var(--color-text)]">BROWSE</button>
            <input value={importGenre} onChange={e => setImportGenre(e.target.value)} placeholder="Genre"
              className="w-28 bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-3 py-2 text-xs font-mono text-[var(--color-text)]" />
            <button onClick={importFiles} disabled={importing || !importPath.trim()}
              className="glow-btn px-4 py-2 rounded text-[11px] font-mono disabled:opacity-40">
              {importing ? <Loader2 size={12} className="animate-spin" /> : 'IMPORT'}
            </button>
          </div>
          {importMsg && <p className="text-[10px] font-mono text-[var(--color-glow)] mt-2">{importMsg}</p>}
        </div>
      )}

      {(analyzeMsg || exportMsg) && (
        <p className="text-[10px] font-mono text-[var(--color-glow)] mb-3">{analyzeMsg || exportMsg}</p>
      )}

      {/* Track Table */}
      <div className="bg-[var(--color-surface-2)] rounded border border-[var(--color-border)] overflow-hidden">
        <table className="w-full text-[11px] font-mono">
          <thead>
            <tr className="border-b border-[var(--color-border)] text-[var(--color-text-dim)]">
              <th className="w-8 px-2 py-2.5">
                <input type="checkbox" checked={selected.size === tracks.length && tracks.length > 0}
                  onChange={() => selected.size === tracks.length ? setSelected(new Set()) : setSelected(new Set(tracks.map(t => t.track_id)))} />
              </th>
              <th className="w-8"></th>
              <th className="text-left px-2 py-2.5 tracking-wider">TITLE</th>
              <th className="text-left px-2 py-2.5 tracking-wider">ARTIST</th>
              <th className="text-right px-2 py-2.5 tracking-wider">BPM</th>
              <th className="text-left px-3 py-2.5 tracking-wider">KEY</th>
              <th className="text-left px-2 py-2.5 tracking-wider">GENRE</th>
              <th className="w-20"></th>
            </tr>
          </thead>
          <tbody>
            {tracks.map((t: any, idx: number) => {
              const isActive = player.playingTrack?.track_id === t.track_id;
              const isPlaying = isActive && player.isPlaying;
              const isLoading = isActive && player.isLoading;
              const hasAnalysis = t.bpm != null;
              const keyDisplay = camelotMode ? t.camelot_key : t.musical_key;
              const isExpanded = expandedTrack === t.track_id;
              const cueCount = t.cues_json ? JSON.parse(t.cues_json).length : 0;

              return (
                <tr key={t.track_id}
                  className={`border-b border-[var(--color-border)]/30 transition-all duration-150 ${isExpanded ? 'bg-[var(--color-glow-dim)]' : isActive ? 'bg-[var(--color-glow-dim)]/50' : 'hover:bg-[var(--color-surface-3)]'}`}>
                  <td className="px-2 py-2 text-center">
                    <input type="checkbox" checked={selected.has(t.track_id)} onChange={() => toggleSelect(t.track_id)} />
                  </td>
                  <td className="px-1 py-2">
                    <button onClick={() => player.playFromQueue(tracks as PlayerTrack[], idx)}
                      className={`p-1 rounded-full transition-all ${isActive ? 'text-[var(--color-glow)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-glow)]'}`}>
                      {isLoading ? <Loader2 size={13} className="animate-spin" /> :
                       isPlaying ? <Pause size={13} /> : <Play size={13} />}
                    </button>
                  </td>
                  <td className="px-2 py-2 max-w-[200px]">
                    <button onClick={() => openTrackDetail(t.track_id)}
                      className="truncate block text-left text-[var(--color-text)] hover:text-[var(--color-glow)] transition-colors w-full">
                      {t.title || 'Unknown'}
                    </button>
                  </td>
                  <td className="px-2 py-2 max-w-[120px] truncate text-[var(--color-text-dim)]">{t.artist || 'Unknown'}</td>
                  <td className="px-2 py-2 text-right">
                    {hasAnalysis ? <span className="text-[var(--color-glow)]">{Math.round(t.bpm)}</span> : <span className="text-[var(--color-text-dim)]">—</span>}
                  </td>
                  <td className="px-3 py-2">
                    {hasAnalysis && keyDisplay ? <span className="text-[var(--color-glow)]">{keyDisplay}</span> : <span className="text-[var(--color-text-dim)]">—</span>}
                  </td>
                  <td className="px-2 py-2 text-[var(--color-text-dim)]">{t.genre_folder || ''}</td>
                  <td className="px-2 py-2">
                    <div className="flex items-center gap-1">
                      {hasAnalysis && (
                        <button onClick={() => openTrackDetail(t.track_id)}
                          className={`p-1 rounded transition-colors ${isExpanded ? 'text-[var(--color-glow)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-glow)]'}`}
                          title="Waveform & Cues">
                          <AudioWaveform size={13} />
                        </button>
                      )}
                      {!hasAnalysis && (
                        <button onClick={() => analyzeSingle(t.track_id)} disabled={analyzing}
                          className="p-1 rounded text-[var(--color-text-dim)] hover:text-[var(--color-glow)] transition-colors" title="Analyze">
                          <Zap size={13} />
                        </button>
                      )}
                      {cueCount > 0 && (
                        <span className="text-[9px] text-[var(--color-glow)] opacity-60">{cueCount}</span>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Expanded Track Detail Panel */}
      {expandedTrack && expandedTrackData && (
        <div className="mt-4 space-y-4">
          {/* Track header */}
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-mono font-bold text-[var(--color-text)]">{expandedTrackData.title}</h3>
              <p className="text-[11px] font-mono text-[var(--color-text-dim)]">
                {expandedTrackData.artist}
                {expandedTrackData.bpm && <> · {Math.round(expandedTrackData.bpm)} BPM</>}
                {expandedTrackData.camelot_key && <> · {expandedTrackData.camelot_key}</>}
              </p>
            </div>
            <button onClick={() => setExpandedTrack(null)}
              className="text-[var(--color-text-dim)] hover:text-[var(--color-text)]"><X size={16} /></button>
          </div>

          {/* Waveform */}
          {expandedTrackData.bpm && (
            <WaveformEditor trackId={expandedTrack} onClose={() => setExpandedTrack(null)} />
          )}

          {/* Hot Cues Editor */}
          <div className="bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-[11px] font-mono text-[var(--color-glow)] tracking-wider">HOT CUES & LOOPS</span>
              <div className="flex items-center gap-2">
                <button onClick={addCue}
                  className="flex items-center gap-1 text-[10px] font-mono text-[var(--color-text-dim)] hover:text-[var(--color-glow)] transition-colors">
                  <Plus size={11} /> ADD
                </button>
                <button onClick={saveCues}
                  className="glow-btn px-3 py-1 rounded text-[10px] font-mono">SAVE</button>
              </div>
            </div>

            {cues.length === 0 && (
              <p className="text-[10px] font-mono text-[var(--color-text-dim)] py-2">No cues set. Click ADD to create one.</p>
            )}

            <div className="space-y-2">
              {cues.map((cue, i) => (
                <div key={i} className="flex items-center gap-2 bg-[var(--color-surface-3)] rounded px-3 py-2">
                  <span className="text-[10px] font-mono text-[var(--color-glow)] w-5">{i + 1}</span>
                  <select value={cue.type} onChange={e => updateCue(i, 'type', e.target.value)}
                    className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-2 py-1 text-[10px] font-mono text-[var(--color-text)]">
                    <option value="cue">CUE</option>
                    <option value="loop">LOOP</option>
                  </select>
                  <input value={cue.name} onChange={e => updateCue(i, 'name', e.target.value)}
                    placeholder="Name"
                    className="flex-1 bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-2 py-1 text-[10px] font-mono text-[var(--color-text)]" />
                  <span className="text-[9px] font-mono text-[var(--color-text-dim)]">START</span>
                  <input type="number" step="0.1" value={cue.start}
                    onChange={e => updateCue(i, 'start', parseFloat(e.target.value) || 0)}
                    className="w-20 bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-2 py-1 text-[10px] font-mono text-[var(--color-text)]" />
                  {cue.type === 'loop' && (
                    <>
                      <span className="text-[9px] font-mono text-[var(--color-text-dim)]">END</span>
                      <input type="number" step="0.1" value={cue.end || ''}
                        onChange={e => updateCue(i, 'end', parseFloat(e.target.value) || null)}
                        className="w-20 bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-2 py-1 text-[10px] font-mono text-[var(--color-text)]" />
                    </>
                  )}
                  <button onClick={() => removeCue(i)}
                    className="p-1 hover:bg-red-900/30 rounded">
                    <Trash2 size={11} className="text-[var(--color-text-dim)] hover:text-red-400" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {tracks.length === 0 && (
        <div className="bg-[var(--color-surface-2)] rounded border border-[var(--color-border)] px-4 py-10 text-center text-[var(--color-text-dim)] text-[11px] font-mono">
          {filter === 'analyzed' ? 'NO ANALYZED TRACKS YET' : 'NO TRACKS TO SHOW'}
        </div>
      )}
    </div>
  );
}
