import { useEffect, useState, useRef, useCallback } from 'react';
import { Loader2, ZoomIn, ZoomOut, SkipBack } from 'lucide-react';
import { api } from '../api/client';
import { usePlayer } from './PlayerContext';

interface WaveformEditorProps {
  trackId: number;
  onClose: () => void;
}

export default function WaveformEditor({ trackId, onClose: _onClose }: WaveformEditorProps) {
  const [waveform, setWaveform] = useState<any>(null);
  const [beatgrid, setBeatgrid] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [scrollX, setScrollX] = useState(0);
  const [gridOffset, setGridOffset] = useState(0); // downbeat shift in seconds
  const [saving, setSaving] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const player = usePlayer();

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.getWaveform(trackId),
      api.getBeatgrid(trackId),
    ]).then(([w, b]) => {
      setWaveform(w);
      setBeatgrid(b);
      setLoading(false);
    });
  }, [trackId]);

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

    ctx.clearRect(0, 0, w, h);

    const { amplitudes, lows, mids, highs, duration } = waveform;
    const totalPoints = amplitudes.length;
    const visiblePoints = Math.floor(totalPoints / zoom);
    const startPoint = Math.floor(scrollX * (totalPoints - visiblePoints));
    const barWidth = w / visiblePoints;

    // Draw waveform bars with frequency coloring
    for (let i = 0; i < visiblePoints && (startPoint + i) < totalPoints; i++) {
      const idx = startPoint + i;
      const amp = amplitudes[idx];
      const low = lows[idx];
      const mid = mids[idx];
      const high = highs[idx];
      const x = i * barWidth;
      const barH = amp * midY * 0.9;

      // Color based on frequency dominance
      const r = Math.floor(high * 180 + 40);
      const g = Math.floor(mid * 200 + 55);
      const b_val = Math.floor(low * 220 + 35);
      ctx.fillStyle = `rgb(${r}, ${g}, ${b_val})`;

      // Draw symmetric bar
      ctx.fillRect(x, midY - barH, Math.max(barWidth - 0.5, 1), barH * 2);
    }

    // Draw beat grid
    if (beatgrid?.beats?.length) {
      const beats = beatgrid.beats;
      ctx.strokeStyle = 'rgba(0, 255, 200, 0.3)';
      ctx.lineWidth = 1;

      for (const beat of beats) {
        const adjustedBeat = beat + gridOffset;
        const pointIdx = (adjustedBeat / duration) * totalPoints;
        const screenIdx = pointIdx - startPoint;
        if (screenIdx < 0 || screenIdx >= visiblePoints) continue;
        const x = screenIdx * barWidth;

        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }

      // Draw downbeats (every 4th beat) more prominently
      ctx.strokeStyle = 'rgba(0, 255, 200, 0.7)';
      ctx.lineWidth = 2;
      for (let i = 0; i < beats.length; i += 4) {
        const adjustedBeat = beats[i] + gridOffset;
        const pointIdx = (adjustedBeat / duration) * totalPoints;
        const screenIdx = pointIdx - startPoint;
        if (screenIdx < 0 || screenIdx >= visiblePoints) continue;
        const x = screenIdx * barWidth;

        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
    }

    // Draw playhead if playing this track
    if (player.playingTrack?.track_id === trackId && player.progress > 0) {
      const playPos = (player.progress / duration) * totalPoints;
      const screenPos = playPos - startPoint;
      if (screenPos >= 0 && screenPos < visiblePoints) {
        const x = screenPos * barWidth;
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
    }
  }, [waveform, beatgrid, zoom, scrollX, gridOffset, player.progress, player.playingTrack, trackId]);

  useEffect(() => {
    draw();
    // Redraw on player progress
    const interval = setInterval(draw, 100);
    return () => clearInterval(interval);
  }, [draw]);

  useEffect(() => {
    const handleResize = () => draw();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [draw]);

  const handleCanvasClick = (e: React.MouseEvent) => {
    if (!waveform || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const totalPoints = waveform.amplitudes.length;
    const visiblePoints = Math.floor(totalPoints / zoom);
    const startPoint = Math.floor(scrollX * (totalPoints - visiblePoints));
    const clickedPoint = startPoint + (x / rect.width) * visiblePoints;
    const time = (clickedPoint / totalPoints) * waveform.duration;
    player.seek(time);
  };

  const handleScroll = (e: React.WheelEvent) => {
    if (e.deltaX !== 0 || e.shiftKey) {
      e.preventDefault();
      setScrollX(prev => Math.max(0, Math.min(1, prev + (e.deltaX || e.deltaY) * 0.001)));
    }
  };

  const saveBeatgrid = async () => {
    if (!beatgrid?.beats) return;
    setSaving(true);
    const adjusted = beatgrid.beats.map((b: number) => b + gridOffset);
    await fetch('/api/analysis/beatgrid', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track_id: trackId, beats: adjusted, bpm: beatgrid.bpm }),
    });
    setGridOffset(0);
    const b = await api.getBeatgrid(trackId);
    setBeatgrid(b);
    setSaving(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 size={20} className="animate-spin text-[var(--color-glow)]" />
        <span className="ml-2 text-xs font-mono text-[var(--color-text-dim)]">GENERATING WAVEFORM...</span>
      </div>
    );
  }

  if (waveform?.error) {
    return <p className="text-xs font-mono text-red-400 py-4">Error: {waveform.error}</p>;
  }

  return (
    <div className="bg-[var(--color-surface-2)] border border-[var(--color-border)] glow-border rounded-lg overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-[var(--color-border)]">
        <span className="text-[11px] font-mono text-[var(--color-glow)]">WAVEFORM</span>
        {beatgrid?.bpm && (
          <span className="text-[10px] font-mono text-[var(--color-text-dim)]">{Math.round(beatgrid.bpm)} BPM</span>
        )}

        <div className="flex-1" />

        <div className="flex items-center gap-1">
          <span className="text-[9px] font-mono text-[var(--color-text-dim)]">GRID SHIFT</span>
          <button onClick={() => setGridOffset(prev => prev - 0.01)}
            className="px-1.5 py-0.5 text-[10px] font-mono border border-[var(--color-border)] rounded text-[var(--color-text-dim)] hover:text-[var(--color-glow)]">-</button>
          <span className="text-[10px] font-mono text-[var(--color-text)] w-14 text-center">{gridOffset.toFixed(3)}s</span>
          <button onClick={() => setGridOffset(prev => prev + 0.01)}
            className="px-1.5 py-0.5 text-[10px] font-mono border border-[var(--color-border)] rounded text-[var(--color-text-dim)] hover:text-[var(--color-glow)]">+</button>
          <button onClick={() => setGridOffset(0)}
            className="p-1 text-[var(--color-text-dim)] hover:text-[var(--color-glow)]" title="Reset">
            <SkipBack size={11} />
          </button>
        </div>

        <div className="flex items-center gap-1 ml-2">
          <button onClick={() => setZoom(z => Math.max(1, z / 1.5))}
            className="p-1 text-[var(--color-text-dim)] hover:text-[var(--color-glow)]">
            <ZoomOut size={14} />
          </button>
          <span className="text-[10px] font-mono text-[var(--color-text-dim)] w-8 text-center">{zoom.toFixed(1)}x</span>
          <button onClick={() => setZoom(z => Math.min(20, z * 1.5))}
            className="p-1 text-[var(--color-text-dim)] hover:text-[var(--color-glow)]">
            <ZoomIn size={14} />
          </button>
        </div>

        {gridOffset !== 0 && (
          <button onClick={saveBeatgrid} disabled={saving}
            className="glow-btn px-3 py-1 rounded text-[10px] font-mono ml-2">
            {saving ? 'SAVING...' : 'SAVE GRID'}
          </button>
        )}
      </div>

      {/* Waveform canvas */}
      <div ref={containerRef} className="relative cursor-crosshair"
        onWheel={handleScroll}>
        <canvas ref={canvasRef} onClick={handleCanvasClick}
          className="w-full" style={{ height: '120px' }} />

        {/* Scroll bar for zoomed view */}
        {zoom > 1 && (
          <div className="h-2 bg-[var(--color-surface-3)] mx-4 mb-2 rounded-full cursor-pointer"
            onClick={e => {
              const rect = e.currentTarget.getBoundingClientRect();
              setScrollX((e.clientX - rect.left) / rect.width);
            }}>
            <div className="h-full bg-[var(--color-glow)] rounded-full opacity-40 transition-all"
              style={{
                width: `${Math.max(5, 100 / zoom)}%`,
                marginLeft: `${scrollX * (100 - 100 / zoom)}%`,
              }} />
          </div>
        )}
      </div>
    </div>
  );
}
