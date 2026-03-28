import { createContext, useContext, useRef, useState, useEffect, useCallback, type ReactNode } from 'react';
import Hls from 'hls.js';

export interface PlayerTrack {
  track_id: number;
  title: string;
  artist: string;
  permalink_url: string;
  artwork_url?: string;
}

interface PlayerState {
  // Current state
  playingTrack: PlayerTrack | null;
  isPlaying: boolean;
  isLoading: boolean;
  failed: boolean;
  progress: number;
  duration: number;
  volume: number;
  embedTrack: PlayerTrack | null;

  // Queue
  queue: PlayerTrack[];
  queueIndex: number;

  // Actions
  play: (track: PlayerTrack) => void;
  playFromQueue: (tracks: PlayerTrack[], startIndex: number) => void;
  stop: () => void;
  togglePlayPause: () => void;
  next: () => void;
  previous: () => void;
  seek: (time: number) => void;
  setVolume: (v: number) => void;
  closeEmbed: () => void;
}

const PlayerContext = createContext<PlayerState>(null!);

export function usePlayer() {
  return useContext(PlayerContext);
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const [playingTrack, setPlayingTrack] = useState<PlayerTrack | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolumeState] = useState(0.8);
  const [embedTrack, setEmbedTrack] = useState<PlayerTrack | null>(null);
  const [queue, setQueue] = useState<PlayerTrack[]>([]);
  const [queueIndex, setQueueIndex] = useState(-1);

  const cleanup = useCallback(() => {
    hlsRef.current?.destroy();
    hlsRef.current = null;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = '';
      audioRef.current.load();
      audioRef.current.ontimeupdate = null;
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current.oncanplay = null;
    }
    audioRef.current = null;
    setIsPlaying(false);
    setProgress(0);
    setDuration(0);
  }, []);

  const loadTrack = useCallback(async (track: PlayerTrack) => {
    cleanup();
    setFailed(false);
    setEmbedTrack(null);
    setPlayingTrack(track);
    setIsLoading(true);

    try {
      const res = await fetch(`/api/stream/${track.track_id}`);
      const data = await res.json();

      if (data.error || data.type === 'embed' || !data.url) {
        setIsLoading(false);
        setFailed(true);
        if (data.type === 'embed') setEmbedTrack(track);
        return;
      }

      const audio = new Audio();
      audio.volume = volume;
      audioRef.current = audio;

      audio.ontimeupdate = () => {
        setProgress(audio.currentTime);
        setDuration(audio.duration || 0);
      };

      audio.onended = () => {
        setIsPlaying(false);
        setProgress(0);
        // Auto-advance to next track
        setQueueIndex(prev => {
          const nextIdx = prev + 1;
          if (nextIdx < queue.length) {
            setTimeout(() => loadTrack(queue[nextIdx]), 100);
            return nextIdx;
          }
          return prev;
        });
      };

      const onError = () => {
        cleanup();
        setIsLoading(false);
        setFailed(true);
      };

      audio.onerror = onError;
      audio.oncanplay = () => { setIsLoading(false); setIsPlaying(true); };

      if (data.type === 'mp3') {
        audio.src = data.url;
        audio.play().catch(onError);
      } else if (data.type === 'hls' && Hls.isSupported()) {
        const hls = new Hls();
        hlsRef.current = hls;
        hls.loadSource(data.url);
        hls.attachMedia(audio);
        hls.on(Hls.Events.MANIFEST_PARSED, () => audio.play().catch(onError));
        hls.on(Hls.Events.ERROR, (_, d) => { if (d.fatal) onError(); });
      } else {
        audio.src = data.url;
        audio.play().catch(onError);
      }
    } catch {
      setIsLoading(false);
      setFailed(true);
    }
  }, [cleanup, volume, queue]);

  const togglePlayPause = useCallback(() => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play();
      setIsPlaying(true);
    }
  }, [isPlaying]);

  const play = useCallback((track: PlayerTrack) => {
    // Same track — toggle pause/resume
    if (playingTrack?.track_id === track.track_id) {
      if (isLoading) return; // still loading, ignore
      if (audioRef.current) {
        togglePlayPause();
        return;
      }
    }
    // New track — cleanup first
    cleanup();
    setQueue([track]);
    setQueueIndex(0);
    loadTrack(track);
  }, [playingTrack, isLoading, togglePlayPause, loadTrack, cleanup]);

  const playFromQueue = useCallback((tracks: PlayerTrack[], startIndex: number) => {
    // Same track — toggle pause/resume
    if (playingTrack?.track_id === tracks[startIndex]?.track_id) {
      if (isLoading) return; // still loading, ignore
      if (audioRef.current) {
        togglePlayPause();
        return;
      }
    }
    // New track — cleanup first
    cleanup();
    setQueue(tracks);
    setQueueIndex(startIndex);
    loadTrack(tracks[startIndex]);
  }, [playingTrack, isLoading, togglePlayPause, loadTrack, cleanup]);

  const stop = useCallback(() => {
    cleanup();
    setPlayingTrack(null);
    setEmbedTrack(null);
    setFailed(false);
  }, [cleanup]);

  const next = useCallback(() => {
    if (queueIndex < queue.length - 1) {
      const nextIdx = queueIndex + 1;
      setQueueIndex(nextIdx);
      loadTrack(queue[nextIdx]);
    }
  }, [queueIndex, queue, loadTrack]);

  const previous = useCallback(() => {
    // If more than 3 seconds in, restart current track
    if (progress > 3 && audioRef.current) {
      audioRef.current.currentTime = 0;
      setProgress(0);
      return;
    }
    if (queueIndex > 0) {
      const prevIdx = queueIndex - 1;
      setQueueIndex(prevIdx);
      loadTrack(queue[prevIdx]);
    }
  }, [queueIndex, queue, progress, loadTrack]);

  const seek = useCallback((time: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = time;
      setProgress(time);
    }
  }, []);

  const setVolume = useCallback((v: number) => {
    setVolumeState(v);
    if (audioRef.current) audioRef.current.volume = v;
  }, []);

  const closeEmbed = useCallback(() => {
    setEmbedTrack(null);
    setFailed(false);
  }, []);

  useEffect(() => () => cleanup(), [cleanup]);

  return (
    <PlayerContext.Provider value={{
      playingTrack, isPlaying, isLoading, failed, progress, duration, volume, embedTrack,
      queue, queueIndex,
      play, playFromQueue, stop, togglePlayPause, next, previous, seek, setVolume, closeEmbed,
    }}>
      {children}
    </PlayerContext.Provider>
  );
}
