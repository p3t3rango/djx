import { useEffect, useState, useRef, useCallback } from 'react';
import { Loader2, ZoomIn, ZoomOut, SkipBack, X, Zap } from 'lucide-react';
import { api } from '../api/client';
import { usePlayer } from './PlayerContext';

interface Cue {
  name: string;
  type: string;
  start: number;
  end: number | null;
  num: number;
}

const CUE_COLORS = ['#ff0000', '#ff8800', '#ffff00', '#00ff00', '#00ffff', '#0088ff', '#8800ff', '#ff00ff'];

export default function TrackDetail({ track, onClose, onAnalyzed }: {
  track: any;
  onClose: () => void;
  onAnalyzed: () => void;
}) {
  const [waveform, setWaveform] = useState<any>(null);
  const [beats, setBeats] = useState<number[]>([]);
  const [bpm, setBpm] = useState<number | null>(null);
  const [cues, setCues] = useState<Cue[]>([]);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzed, setAnalyzed] = useState(track.bpm != null);
  const [zoom, setZoom] = useState(1);
  const [scrollX, setScrollX] = useState(0);
  const [gridOffset, setGridOffset] = useState(0);
  const [placingCue, setPlacingCue] = useState(false);
  const [namingCue, setNamingCue] = useState<number | null>(null); // index of cue being named
  const [cueNameInput, setCueNameInput] = useState('');
  const [editingCueName, setEditingCueName] = useState<number | null>(null);
  const [saved, setSaved] = useState(false);
  const [isScrubbing, setIsScrubbing] = useState(false);
  const [draggingCue, setDraggingCue] = useState<number | null>(null); // index of cue being dragged
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const player = usePlayer();

  useEffect(() => {
    setAnalyzed(track.bpm != null);
    if (track.bpm != null) loadWaveformAndCues();
  }, [track.track_id, track.bpm]);

  const loadWaveformAndCues = async () => {
    setLoading(true);
    const [w, bg, cueData] = await Promise.all([
      api.getWaveform(track.track_id),
      api.getBeatgrid(track.track_id),
      fetch(`/api/analysis/cues/${track.track_id}`).then(r => r.json()),
    ]);
    setWaveform(w);
    setBeats(bg.beats || []);
    setBpm(bg.bpm);
    setCues(Array.isArray(cueData) ? cueData : []);
    setLoading(false);
  };

  const analyzeTrack = async () => {
    setAnalyzing(true);
    const res = await fetch('/api/analysis/analyze', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track_ids: [track.track_id] }),
    });
    const { task_id } = await res.json();
    const poll = setInterval(async () => {
      const status = await fetch(`/api/analysis/status/${task_id}`).then(r => r.json());
      if (status.status === 'completed' || status.status === 'failed') {
        clearInterval(poll);
        setAnalyzing(false);
        setAnalyzed(true);
        onAnalyzed();
        loadWaveformAndCues();
      }
    }, 1500);
  };

  // --- Coordinate helpers ---
  const getTimeFromX = useCallback((clientX: number): number => {
    if (!waveform || !canvasRef.current) return 0;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const totalPoints = waveform.amplitudes.length;
    const visiblePoints = Math.floor(totalPoints / zoom);
    const startPoint = Math.floor(scrollX * Math.max(0, totalPoints - visiblePoints));
    const clickedPoint = startPoint + (x / rect.width) * visiblePoints;
    return Math.max(0, Math.min(waveform.duration, (clickedPoint / totalPoints) * waveform.duration));
  }, [waveform, zoom, scrollX]);

  const getCueAtX = useCallback((clientX: number): number | null => {
    if (!waveform || !canvasRef.current || !cues.length) return null;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const totalPoints = waveform.amplitudes.length;
    const visiblePoints = Math.floor(totalPoints / zoom);
    const startPoint = Math.floor(scrollX * Math.max(0, totalPoints - visiblePoints));
    const barWidth = rect.width / visiblePoints;

    for (let i = 0; i < cues.length; i++) {
      const cuePoint = (cues[i].start / waveform.duration) * totalPoints;
      const screenPos = (cuePoint - startPoint) * barWidth;
      if (Math.abs(x - screenPos) < 8) return i;
    }
    return null;
  }, [waveform, zoom, scrollX, cues]);

  // --- Mouse handlers ---
  const handleMouseDown = (e: React.MouseEvent) => {
    if (!waveform) return;

    // Check if clicking on a cue marker
    const cueIdx = getCueAtX(e.clientX);
    if (cueIdx !== null && !placingCue) {
      setDraggingCue(cueIdx);
      return;
    }

    if (placingCue) {
      const time = getTimeFromX(e.clientX);
      const newCue: Cue = { name: '', type: 'cue', start: Math.round(time * 100) / 100, end: null, num: cues.length };
      setCues([...cues, newCue]);
      setPlacingCue(false);
      setNamingCue(cues.length);
      setCueNameInput('');
      setTimeout(() => nameInputRef.current?.focus(), 50);
      return;
    }

    // Start scrubbing
    setIsScrubbing(true);
    const time = getTimeFromX(e.clientX);
    player.seek(time);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (draggingCue !== null) {
      const time = getTimeFromX(e.clientX);
      // Snap to nearest beat if close
      let snapped = time;
      if (beats.length) {
        const closest = beats.reduce((a, b) => Math.abs(b - time) < Math.abs(a - time) ? b : a);
        if (Math.abs(closest - time) < 0.05) snapped = closest;
      }
      const next = [...cues];
      next[draggingCue] = { ...next[draggingCue], start: Math.round(snapped * 100) / 100 };
      setCues(next);
      return;
    }

    if (isScrubbing) {
      const time = getTimeFromX(e.clientX);
      player.seek(time);
    }
  };

  const handleMouseUp = () => {
    setIsScrubbing(false);
    setDraggingCue(null);
  };

  const handleScroll = (e: React.WheelEvent) => {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) {
      setZoom(z => Math.max(1, Math.min(20, z * (e.deltaY < 0 ? 1.3 : 0.7))));
    } else {
      setScrollX(prev => Math.max(0, Math.min(1, prev + e.deltaY * 0.002)));
    }
  };

  // --- Cue naming ---
  const finishNaming = () => {
    if (namingCue !== null) {
      const next = [...cues];
      next[namingCue] = { ...next[namingCue], name: cueNameInput || `Cue ${namingCue + 1}` };
      setCues(next);
      setNamingCue(null);
    }
  };

  const startEditCueName = (idx: number) => {
    setEditingCueName(idx);
    setCueNameInput(cues[idx].name);
  };

  const finishEditCueName = () => {
    if (editingCueName !== null) {
      const next = [...cues];
      next[editingCueName] = { ...next[editingCueName], name: cueNameInput };
      setCues(next);
      setEditingCueName(null);
    }
  };

  // --- Cue playback ---
  const jumpToCue = (cue: Cue) => {
    player.seek(cue.start);
    // If not playing, start playback
    if (!player.isPlaying && player.playingTrack?.track_id === track.track_id) {
      player.togglePlayPause();
    } else if (!player.playingTrack || player.playingTrack.track_id !== track.track_id) {
      player.play(track);
      setTimeout(() => player.seek(cue.start), 200);
    }
  };

  // --- Drawing ---
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !waveform || waveform.error) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;
    const midY = h / 2;

    // Background
    ctx.fillStyle = '#050505';
    ctx.fillRect(0, 0, w, h);

    // Center line
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, midY);
    ctx.lineTo(w, midY);
    ctx.stroke();

    const { amplitudes, lows, mids, highs, duration } = waveform;
    const totalPoints = amplitudes.length;
    const visiblePoints = Math.floor(totalPoints / zoom);
    const startPoint = Math.floor(scrollX * Math.max(0, totalPoints - visiblePoints));
    const barWidth = w / visiblePoints;

    // --- CDJ/Serato-style stacked frequency waveform ---
    for (let i = 0; i < visiblePoints && (startPoint + i) < totalPoints; i++) {
      const idx = startPoint + i;
      const amp = amplitudes[idx];
      const low = lows[idx];
      const mid = mids[idx];
      const high = highs[idx];
      const x = i * barWidth;
      const totalH = amp * midY * 0.85;

      if (totalH < 0.5) continue;

      const sum = low + mid + high || 1;
      const lowH = (low / sum) * totalH;
      const midH = (mid / sum) * totalH;
      const highH = (high / sum) * totalH;

      // Draw mirrored from center — bottom to top: lows, mids, highs
      const bw = Math.max(barWidth - 0.3, 0.5);

      // Lows (bass) — blue
      ctx.fillStyle = `rgba(0, 100, 255, ${0.6 + low * 0.4})`;
      ctx.fillRect(x, midY - lowH, bw, lowH);
      ctx.fillRect(x, midY, bw, lowH);

      // Mids — green
      ctx.fillStyle = `rgba(0, 220, 120, ${0.5 + mid * 0.5})`;
      ctx.fillRect(x, midY - lowH - midH, bw, midH);
      ctx.fillRect(x, midY + lowH, bw, midH);

      // Highs — red/white
      ctx.fillStyle = `rgba(255, 80, 80, ${0.4 + high * 0.6})`;
      ctx.fillRect(x, midY - lowH - midH - highH, bw, highH);
      ctx.fillRect(x, midY + lowH + midH, bw, highH);
    }

    // --- Beat grid ---
    if (beats.length > 0) {
      let downbeatCount = 0;
      for (let i = 0; i < beats.length; i++) {
        const beat = beats[i] + gridOffset;
        const pointIdx = (beat / duration) * totalPoints;
        const screenIdx = pointIdx - startPoint;
        if (screenIdx < 0 || screenIdx >= visiblePoints) continue;
        const x = screenIdx * barWidth;
        const isDownbeat = i % 4 === 0;

        ctx.strokeStyle = isDownbeat ? 'rgba(0, 255, 200, 0.4)' : 'rgba(0, 255, 200, 0.1)';
        ctx.lineWidth = isDownbeat ? 1.5 : 0.5;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();

        // Downbeat numbers
        if (isDownbeat) {
          downbeatCount++;
          if (downbeatCount % 4 === 1) {
            ctx.fillStyle = 'rgba(0, 255, 200, 0.3)';
            ctx.font = '9px monospace';
            ctx.fillText(String(downbeatCount), x + 2, h - 3);
          }
        }
      }
    }

    // --- Cue markers ---
    for (let ci = 0; ci < cues.length; ci++) {
      const cue = cues[ci];
      const color = CUE_COLORS[cue.num % CUE_COLORS.length];
      const pointIdx = (cue.start / duration) * totalPoints;
      const screenIdx = pointIdx - startPoint;
      if (screenIdx < 0 || screenIdx >= visiblePoints) continue;
      const x = screenIdx * barWidth;
      const isDragging = draggingCue === ci;

      // Cue line
      ctx.strokeStyle = color;
      ctx.lineWidth = isDragging ? 3 : 2;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();

      // Glow on drag
      if (isDragging) {
        ctx.strokeStyle = color + '40';
        ctx.lineWidth = 8;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }

      // Triangle + label at top
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(x - 6, 0);
      ctx.lineTo(x + 6, 0);
      ctx.lineTo(x, 12);
      ctx.fill();

      // Cue name
      ctx.fillStyle = '#000';
      ctx.font = 'bold 8px monospace';
      const label = cue.name || `${ci + 1}`;
      ctx.fillText(label.slice(0, 6), x - 4, 9);

      // Loop fill
      if (cue.type === 'loop' && cue.end) {
        const endIdx = (cue.end / duration) * totalPoints;
        const endScreen = endIdx - startPoint;
        if (endScreen >= 0 && endScreen < visiblePoints) {
          const endX = endScreen * barWidth;
          ctx.fillStyle = color + '12';
          ctx.fillRect(x, 0, endX - x, h);
        }
      }
    }

    // --- Playhead ---
    if (player.playingTrack?.track_id === track.track_id && player.progress > 0) {
      const playPos = (player.progress / duration) * totalPoints;
      const screenPos = playPos - startPoint;
      if (screenPos >= 0 && screenPos < visiblePoints) {
        const x = screenPos * barWidth;

        // Glow
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
        ctx.lineWidth = 6;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();

        // Line
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();

        // Time overlay
        const mins = Math.floor(player.progress / 60);
        const secs = Math.floor(player.progress % 60);
        ctx.fillStyle = 'rgba(0,0,0,0.7)';
        ctx.fillRect(x + 4, 2, 34, 14);
        ctx.fillStyle = '#fff';
        ctx.font = '10px monospace';
        ctx.fillText(`${mins}:${String(secs).padStart(2, '0')}`, x + 6, 13);
      }
    }
  }, [waveform, beats, cues, zoom, scrollX, gridOffset, player.progress, player.playingTrack, track.track_id, draggingCue]);

  useEffect(() => {
    draw();
    const interval = setInterval(draw, 80);
    return () => clearInterval(interval);
  }, [draw]);

  // --- Save ---
  const saveCues = async () => {
    await fetch('/api/analysis/cues', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track_id: track.track_id, cues }),
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const saveGrid = async () => {
    const adjusted = beats.map(b => b + gridOffset);
    await fetch('/api/analysis/beatgrid', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track_id: track.track_id, beats: adjusted, bpm }),
    });
    setBeats(adjusted);
    setGridOffset(0);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  // Not analyzed
  if (!analyzed) {
    return (
      <div className="bg-[var(--color-surface-2)] border border-[var(--color-border)] glow-border rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-mono font-bold text-[var(--color-text)]">{track.title}</h3>
            <p className="text-[11px] font-mono text-[var(--color-text-dim)]">{track.artist}</p>
          </div>
          <button onClick={onClose} className="text-[var(--color-text-dim)]"><X size={16} /></button>
        </div>
        <div className="text-center py-8">
          <p className="text-xs font-mono text-[var(--color-text-dim)] mb-4">Analyze this track to view waveform, set cues, and edit the beat grid</p>
          <button onClick={analyzeTrack} disabled={analyzing}
            className="glow-btn px-6 py-3 rounded text-xs font-mono flex items-center gap-2 mx-auto">
            {analyzing ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
            {analyzing ? 'ANALYZING...' : 'ANALYZE NOW'}
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded-lg flex items-center justify-center py-12">
        <Loader2 size={20} className="animate-spin text-[var(--color-glow)]" />
        <span className="ml-2 text-xs font-mono text-[var(--color-text-dim)]">LOADING WAVEFORM...</span>
      </div>
    );
  }

  const cursorStyle = placingCue ? 'crosshair' : draggingCue !== null ? 'grabbing' : isScrubbing ? 'grabbing' : 'grab';

  return (
    <div className="bg-[var(--color-surface-2)] border border-[var(--color-border)] glow-border rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-4">
          <span className="text-xs font-mono text-[var(--color-text)]">{track.title}</span>
          <span className="text-[10px] font-mono text-[var(--color-text-dim)]">{track.artist}</span>
          {bpm && <span className="text-[10px] font-mono text-[var(--color-glow)]">{Math.round(bpm)} BPM</span>}
          {track.camelot_key && <span className="text-[10px] font-mono text-[var(--color-glow)]">{track.camelot_key}</span>}
        </div>
        <div className="flex items-center gap-2">
          {saved && <span className="text-[10px] font-mono text-[var(--color-glow)]">SAVED</span>}
          <button onClick={onClose} className="text-[var(--color-text-dim)] hover:text-[var(--color-text)]"><X size={14} /></button>
        </div>
      </div>

      {/* Waveform canvas */}
      <div className="relative" style={{ cursor: cursorStyle }}
        onWheel={handleScroll}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}>
        <canvas ref={canvasRef} className="w-full select-none" style={{ height: '160px' }} />

        {/* Cue naming overlay */}
        {namingCue !== null && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-[var(--color-surface)] border border-[var(--color-glow)] rounded px-2 py-1 flex items-center gap-2 z-10">
            <span className="text-[10px] font-mono text-[var(--color-glow)]">NAME:</span>
            <input ref={nameInputRef} value={cueNameInput} onChange={e => setCueNameInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') finishNaming(); if (e.key === 'Escape') { setNamingCue(null); setCues(cues.slice(0, -1)); } }}
              placeholder={`Cue ${(namingCue || 0) + 1}`}
              className="bg-transparent border-none outline-none text-xs font-mono text-[var(--color-text)] w-24" />
            <button onClick={finishNaming} className="text-[10px] font-mono text-[var(--color-glow)]">OK</button>
          </div>
        )}

        {/* Scroll bar */}
        {zoom > 1 && (
          <div className="absolute bottom-1 left-4 right-4 h-1.5 bg-[var(--color-surface-3)] rounded-full cursor-pointer opacity-60 hover:opacity-100"
            onClick={e => {
              const rect = e.currentTarget.getBoundingClientRect();
              setScrollX((e.clientX - rect.left) / rect.width);
            }}>
            <div className="h-full bg-[var(--color-glow)] rounded-full opacity-40"
              style={{ width: `${Math.max(5, 100 / zoom)}%`, marginLeft: `${scrollX * (100 - 100 / zoom)}%` }} />
          </div>
        )}
      </div>

      {/* Controls bar */}
      <div className="flex items-center gap-3 px-4 py-2 border-t border-[var(--color-border)] flex-wrap">
        {/* Zoom */}
        <div className="flex items-center gap-1">
          <button onClick={() => setZoom(z => Math.max(1, z / 1.5))}
            className="p-1 text-[var(--color-text-dim)] hover:text-[var(--color-glow)]"><ZoomOut size={13} /></button>
          <span className="text-[10px] font-mono text-[var(--color-text-dim)] w-8 text-center">{zoom.toFixed(1)}x</span>
          <button onClick={() => setZoom(z => Math.min(20, z * 1.5))}
            className="p-1 text-[var(--color-text-dim)] hover:text-[var(--color-glow)]"><ZoomIn size={13} /></button>
        </div>

        <div className="w-px h-4 bg-[var(--color-border)]" />

        {/* Grid */}
        <div className="flex items-center gap-1">
          <span className="text-[9px] font-mono text-[var(--color-text-dim)]">GRID</span>
          <button onClick={() => setGridOffset(o => o - 0.01)}
            className="px-1.5 py-0.5 text-[10px] font-mono border border-[var(--color-border)] rounded text-[var(--color-text-dim)] hover:text-[var(--color-glow)]">◀</button>
          <span className="text-[10px] font-mono text-[var(--color-text)] w-14 text-center">{gridOffset.toFixed(3)}s</span>
          <button onClick={() => setGridOffset(o => o + 0.01)}
            className="px-1.5 py-0.5 text-[10px] font-mono border border-[var(--color-border)] rounded text-[var(--color-text-dim)] hover:text-[var(--color-glow)]">▶</button>
          <button onClick={() => { setBpm(b => b ? b / 2 : b); setBeats(prev => prev.filter((_, i) => i % 2 === 0)); }}
            className="px-1.5 py-0.5 text-[9px] font-mono border border-[var(--color-border)] rounded text-[var(--color-text-dim)] hover:text-[var(--color-glow)]" title="Half BPM">½×</button>
          <button onClick={() => {
            setBpm(b => b ? b * 2 : b);
            setBeats(prev => {
              const doubled: number[] = [];
              for (let i = 0; i < prev.length - 1; i++) {
                doubled.push(prev[i]);
                doubled.push((prev[i] + prev[i + 1]) / 2);
              }
              doubled.push(prev[prev.length - 1]);
              return doubled;
            });
          }}
            className="px-1.5 py-0.5 text-[9px] font-mono border border-[var(--color-border)] rounded text-[var(--color-text-dim)] hover:text-[var(--color-glow)]" title="Double BPM">2×</button>
          {(gridOffset !== 0 || true) && (
            <button onClick={saveGrid} className="glow-btn px-2 py-0.5 rounded text-[9px] font-mono">SAVE</button>
          )}
          {gridOffset !== 0 && (
            <button onClick={() => setGridOffset(0)} className="p-1 text-[var(--color-text-dim)] hover:text-[var(--color-glow)]"><SkipBack size={11} /></button>
          )}
        </div>

        <div className="w-px h-4 bg-[var(--color-border)]" />

        {/* Cues */}
        <div className="flex items-center gap-1">
          <button onClick={() => setPlacingCue(!placingCue)}
            className={`px-2 py-0.5 rounded text-[9px] font-mono border transition-colors ${
              placingCue ? 'border-[var(--color-glow)] text-[var(--color-glow)] bg-[var(--color-glow-dim)]' : 'border-[var(--color-border)] text-[var(--color-text-dim)] hover:text-[var(--color-glow)]'
            }`}>
            {placingCue ? 'CLICK TO PLACE CUE' : '+ CUE'}
          </button>
          {cues.length > 0 && (
            <button onClick={saveCues} className="glow-btn px-2 py-0.5 rounded text-[9px] font-mono">SAVE CUES</button>
          )}
        </div>

        <div className="flex-1" />
        <span className="text-[8px] font-mono text-[var(--color-text-dim)] opacity-50">
          DRAG: scrub · ⌘SCROLL: zoom · SCROLL: pan · DRAG CUES: reposition
        </span>
      </div>

      {/* Cue list */}
      {cues.length > 0 && (
        <div className="border-t border-[var(--color-border)] px-4 py-2">
          <div className="flex gap-2 flex-wrap">
            {cues.map((cue, i) => (
              <div key={i} className="flex items-center gap-1.5 bg-[var(--color-surface-3)] rounded px-2 py-1 group"
                style={{ borderLeft: `3px solid ${CUE_COLORS[cue.num % CUE_COLORS.length]}` }}>
                {editingCueName === i ? (
                  <input value={cueNameInput} onChange={e => setCueNameInput(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') finishEditCueName(); if (e.key === 'Escape') setEditingCueName(null); }}
                    onBlur={finishEditCueName}
                    autoFocus
                    className="bg-transparent border-none outline-none text-[10px] font-mono text-[var(--color-text)] w-16" />
                ) : (
                  <button onClick={() => startEditCueName(i)}
                    className="text-[10px] font-mono text-[var(--color-text)] hover:text-[var(--color-glow)]" title="Click to rename">
                    {cue.name || `Cue ${i + 1}`}
                  </button>
                )}
                <span className="text-[9px] font-mono text-[var(--color-text-dim)]">{cue.start.toFixed(2)}s</span>
                <button onClick={() => jumpToCue(cue)}
                  className="text-[var(--color-text-dim)] hover:text-[var(--color-glow)]" title="Jump & play">▶</button>
                <button onClick={() => setCues(cues.filter((_, j) => j !== i))}
                  className="text-[var(--color-text-dim)] hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"><X size={10} /></button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
