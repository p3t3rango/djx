import { useState } from 'react';
import { Volume2, VolumeX, Play, Pause, SkipBack, SkipForward, ExternalLink, X, Download, Loader2, Check } from 'lucide-react';
import { usePlayer } from './PlayerContext';
import { api } from '../api/client';

function formatTime(s: number) {
  if (!s || !isFinite(s)) return '0:00';
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

export default function PlayerBar() {
  const p = usePlayer();
  const [dlState, setDlState] = useState<'idle' | 'loading' | 'done'>('idle');
  const [lastDlId, setLastDlId] = useState<number | null>(null);

  if (!p.playingTrack && !p.embedTrack) return null;

  const track = p.playingTrack || p.embedTrack;
  if (!track) return null;

  // Reset download state when track changes
  if (track.track_id !== lastDlId && dlState !== 'idle') {
    setDlState('idle');
    setLastDlId(null);
  }

  const handleDownload = async () => {
    if (dlState !== 'idle') return;
    setDlState('loading');
    setLastDlId(track.track_id);
    try {
      const { task_id } = await api.downloadTracks([track.track_id], 'downloads', true);
      // Poll until done
      const poll = setInterval(async () => {
        const status = await api.getDownloadStatus(task_id);
        if (status.status === 'completed' || status.status === 'failed') {
          clearInterval(poll);
          setDlState(status.status === 'completed' ? 'done' : 'idle');
        }
      }, 1500);
    } catch {
      setDlState('idle');
    }
  };

  const embedUrl = (permalink: string) =>
    `https://w.soundcloud.com/player/?url=${encodeURIComponent(permalink)}&color=%2300ffc8&auto_play=true&hide_related=true&show_comments=false&show_user=true&show_reposts=false&show_teaser=false`;

  // Embed fallback mode
  if (p.embedTrack && !p.isPlaying) {
    return (
      <div className="fixed bottom-0 left-52 right-0 z-50 bg-[var(--color-surface-2)] border-t border-[var(--color-border-glow)]"
        style={{ boxShadow: '0 -4px 30px rgba(0,255,200,0.05)' }}>
        <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--color-border)]">
          <div className="flex items-center gap-3 min-w-0">
            <Volume2 size={14} className="text-[var(--color-glow)] shrink-0" />
            <span className="text-[11px] font-mono text-[var(--color-text)] truncate">{track.title}</span>
            <span className="text-[10px] font-mono text-[var(--color-text-dim)] truncate">— {track.artist}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {p.queue.length > 1 && (
              <>
                <button onClick={p.previous} disabled={p.queueIndex <= 0}
                  className="p-1 text-[var(--color-text-dim)] hover:text-[var(--color-glow)] disabled:opacity-30 transition-colors">
                  <SkipBack size={14} />
                </button>
                <button onClick={p.next} disabled={p.queueIndex >= p.queue.length - 1}
                  className="p-1 text-[var(--color-text-dim)] hover:text-[var(--color-glow)] disabled:opacity-30 transition-colors">
                  <SkipForward size={14} />
                </button>
              </>
            )}
            {track.track_id > 0 && (
              <button onClick={handleDownload} disabled={dlState !== 'idle'}
                className={`p-1 rounded transition-colors ${dlState === 'done' ? 'text-[var(--color-glow)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-glow)]'}`}
                title={dlState === 'done' ? 'Downloaded' : 'Download'}>
                {dlState === 'loading' ? <Loader2 size={12} className="animate-spin" /> :
                 dlState === 'done' ? <Check size={12} /> : <Download size={12} />}
              </button>
            )}
            <a href={track.permalink_url} target="_blank" rel="noopener noreferrer"
              className="text-[10px] font-mono text-[var(--color-text-dim)] hover:text-[var(--color-glow)] flex items-center gap-1 transition-colors">
              SC <ExternalLink size={9} />
            </a>
            <button onClick={p.stop}
              className="p-1 rounded hover:bg-[var(--color-surface-3)] text-[var(--color-text-dim)] transition-colors">
              <X size={14} />
            </button>
          </div>
        </div>
        <iframe width="100%" height="80" scrolling="no" frameBorder="no" allow="autoplay"
          src={embedUrl(track.permalink_url)} className="block" />
      </div>
    );
  }

  // Stream mode
  const progressPct = p.duration ? (p.progress / p.duration) * 100 : 0;
  const hasQueue = p.queue.length > 1;
  const canPrev = p.queueIndex > 0 || p.progress > 3;
  const canNext = p.queueIndex < p.queue.length - 1;

  return (
    <div className="fixed bottom-0 left-52 right-0 z-50 bg-[var(--color-surface-2)] border-t border-[var(--color-border-glow)] h-[72px]"
      style={{ boxShadow: '0 -4px 30px rgba(0,255,200,0.05)' }}>

      {/* Progress bar */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-[var(--color-surface-3)] cursor-pointer group"
        onClick={e => {
          const rect = e.currentTarget.getBoundingClientRect();
          const pct = (e.clientX - rect.left) / rect.width;
          p.seek(pct * p.duration);
        }}>
        <div className="h-full bg-[var(--color-glow)] transition-all duration-150 relative"
          style={{ width: `${progressPct}%` }}>
          <div className="absolute right-0 top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-[var(--color-glow)] opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ boxShadow: '0 0 8px var(--color-glow)' }} />
        </div>
      </div>

      <div className="flex items-center h-full px-4 pt-1 gap-3">

        {/* Transport controls */}
        <div className="flex items-center gap-1">
          <button onClick={p.previous} disabled={!canPrev}
            className="p-1.5 text-[var(--color-text-dim)] hover:text-[var(--color-glow)] disabled:opacity-20 transition-colors">
            <SkipBack size={16} />
          </button>

          <button onClick={() => p.togglePlayPause()}
            className="w-10 h-10 rounded-full border border-[var(--color-glow)] flex items-center justify-center text-[var(--color-glow)] hover:bg-[var(--color-glow-dim)] transition-all"
            style={{ boxShadow: '0 0 12px rgba(0,255,200,0.15)' }}>
            {p.isPlaying ? <Pause size={18} /> : <Play size={18} className="ml-0.5" />}
          </button>

          <button onClick={p.next} disabled={!canNext}
            className="p-1.5 text-[var(--color-text-dim)] hover:text-[var(--color-glow)] disabled:opacity-20 transition-colors">
            <SkipForward size={16} />
          </button>
        </div>

        {/* Track info */}
        <div className="flex-1 min-w-0 mx-2">
          <div className="text-xs font-mono text-[var(--color-text)] truncate">{track.title}</div>
          <div className="text-[10px] font-mono text-[var(--color-text-dim)] truncate">{track.artist}</div>
        </div>

        {/* Time */}
        <div className="text-[10px] font-mono text-[var(--color-text-dim)] tabular-nums whitespace-nowrap">
          {formatTime(p.progress)} / {formatTime(p.duration)}
        </div>

        {/* Queue position */}
        {hasQueue && (
          <div className="text-[10px] font-mono text-[var(--color-glow)] opacity-60 whitespace-nowrap">
            {p.queueIndex + 1} / {p.queue.length}
          </div>
        )}

        {/* Volume */}
        <div className="flex items-center gap-1.5 ml-1">
          <button onClick={() => p.setVolume(p.volume > 0 ? 0 : 0.8)}
            className="text-[var(--color-text-dim)] hover:text-[var(--color-glow)] transition-colors">
            {p.volume === 0 ? <VolumeX size={14} /> : <Volume2 size={14} />}
          </button>
          <input type="range" min="0" max="1" step="0.05" value={p.volume}
            onChange={e => p.setVolume(parseFloat(e.target.value))}
            className="w-16 h-1 appearance-none bg-[var(--color-surface-3)] rounded-full cursor-pointer
              [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-2.5 [&::-webkit-slider-thumb]:h-2.5
              [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-[var(--color-glow)]
              [&::-webkit-slider-thumb]:shadow-[0_0_6px_var(--color-glow)]" />
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 ml-1">
          {track.track_id > 0 && (
            <button onClick={handleDownload} disabled={dlState !== 'idle'}
              className={`p-1.5 rounded hover:bg-[var(--color-surface-3)] transition-colors ${dlState === 'done' ? 'text-[var(--color-glow)]' : 'text-[var(--color-text-dim)] hover:text-[var(--color-glow)]'}`}
              title={dlState === 'done' ? 'Downloaded' : 'Download to library'}>
              {dlState === 'loading' ? <Loader2 size={13} className="animate-spin" /> :
               dlState === 'done' ? <Check size={13} /> : <Download size={13} />}
            </button>
          )}
          <a href={track.permalink_url} target="_blank" rel="noopener noreferrer"
            className="p-1.5 rounded hover:bg-[var(--color-surface-3)] text-[var(--color-text-dim)] hover:text-[var(--color-glow)] transition-colors"
            title="Open in SoundCloud">
            <ExternalLink size={13} />
          </a>
          <button onClick={p.stop}
            className="p-1.5 rounded hover:bg-[var(--color-surface-3)] text-[var(--color-text-dim)] hover:text-red-400 transition-colors"
            title="Close">
            <X size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}
