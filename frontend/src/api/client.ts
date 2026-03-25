const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  return res.json();
}

export const api = {
  // Discovery
  getGenres: () => request<Record<string, { display_name: string; folder: string }>>('/discovery/genres'),
  discover: (genre: string, count: number, include_remixes: boolean, sort = 'trending') =>
    request<{ task_id: string }>('/discovery/discover', {
      method: 'POST',
      body: JSON.stringify({ genre, count, include_remixes, sort }),
    }),
  discoverRelated: (track_id: number, limit = 50) =>
    request<{ task_id: string }>('/discovery/related', {
      method: 'POST',
      body: JSON.stringify({ track_id, limit }),
    }),
  getTopTracks: (limit = 10) => request<any[]>(`/discovery/top?limit=${limit}`),
  getDiscoveryStatus: (taskId: string) => request<any>(`/discovery/status/${taskId}`),

  // Downloads
  getDownloads: (genre?: string, limit = 50, offset = 0) =>
    request<any[]>(`/downloads/?${genre ? `genre=${genre}&` : ''}limit=${limit}&offset=${offset}`),
  getDownloadStats: () => request<any>('/downloads/stats'),
  batchDownload: (genre: string, count: number, include_remixes: boolean) =>
    request<{ task_id: string }>('/downloads/batch', {
      method: 'POST',
      body: JSON.stringify({ genre, count, include_remixes }),
    }),
  getDownloadStatus: (taskId: string) => request<any>(`/downloads/status/${taskId}`),
  downloadTracks: (track_ids: number[], genre_folder: string) =>
    request<{ task_id: string }>('/downloads/', {
      method: 'POST',
      body: JSON.stringify({ track_ids, genre_folder }),
    }),
  resolveUrl: (url: string) =>
    request<any>('/downloads/resolve-url', {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),
  downloadFromUrl: (url: string, genre_folder = 'downloads', analyze_after = false) =>
    request<{ task_id: string }>('/downloads/url', {
      method: 'POST',
      body: JSON.stringify({ url, genre_folder, analyze_after }),
    }),
  deleteDownload: (id: number) =>
    request<any>(`/downloads/${id}`, { method: 'DELETE' }),
  editMetadata: (trackId: number, data: { title?: string; artist?: string; genre?: string }) =>
    request<any>(`/downloads/metadata/${trackId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  // USB Export
  exportUSB: (target_path: string, track_ids?: number[], playlist_name?: string) =>
    request<{ task_id: string }>('/analysis/export-usb', {
      method: 'POST',
      body: JSON.stringify({ target_path, track_ids, playlist_name }),
    }),

  // Tags
  getTags: () => request<any[]>('/downloads/tags'),
  createTag: (name: string, color = '#00ffc8') =>
    request<any>('/downloads/tags', { method: 'POST', body: JSON.stringify({ name, color }) }),
  deleteTag: (tagId: number) =>
    request<any>(`/downloads/tags/${tagId}`, { method: 'DELETE' }),
  tagTrack: (track_id: number, tag_id: number) =>
    request<any>('/downloads/tags/assign', { method: 'POST', body: JSON.stringify({ track_id, tag_id }) }),
  untagTrack: (track_id: number, tag_id: number) =>
    request<any>('/downloads/tags/remove', { method: 'POST', body: JSON.stringify({ track_id, tag_id }) }),
  getTrackTags: (trackId: number) => request<any[]>(`/downloads/tags/track/${trackId}`),

  // Playlists
  getPlaylists: () => request<any[]>('/downloads/playlists'),
  createPlaylist: (name: string, track_ids: number[], export_folder?: string) =>
    request<any>('/downloads/playlists', {
      method: 'POST',
      body: JSON.stringify({ name, track_ids, export_folder }),
    }),
  updatePlaylist: (id: number, data: { name?: string; track_ids?: number[] }) =>
    request<any>(`/downloads/playlists/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deletePlaylist: (id: number) =>
    request<any>(`/downloads/playlists/${id}`, { method: 'DELETE' }),

  // Waveform
  getWaveform: (trackId: number) => request<any>(`/analysis/waveform/${trackId}`),
  getBeatgrid: (trackId: number) => request<any>(`/analysis/beatgrid/${trackId}`),

  // Search
  searchTracks: (q: string, limit = 50) => request<any[]>(`/search/tracks?q=${encodeURIComponent(q)}&limit=${limit}`),
  searchArtists: (q: string) => request<any[]>(`/search/artists?q=${encodeURIComponent(q)}`),
  getArtistTracks: (userId: number, sort = 'popular') =>
    request<any[]>(`/search/artists/${userId}/tracks?sort=${sort}`),

  // Accounts
  getAccounts: (genre?: string, status?: string) =>
    request<any[]>(`/accounts/?${genre ? `genre=${genre}&` : ''}${status ? `status=${status}` : ''}`),
  suggestAccounts: (genre: string, limit = 10) =>
    request<any[]>('/accounts/suggest', {
      method: 'POST',
      body: JSON.stringify({ genre, limit }),
    }),
  approveAccount: (userId: number) => request<any>(`/accounts/${userId}/approve`, { method: 'PUT' }),
  rejectAccount: (userId: number) => request<any>(`/accounts/${userId}/reject`, { method: 'PUT' }),
  getAccountTracks: (userId: number) => request<any[]>(`/accounts/${userId}/tracks`),
  deleteAccount: (userId: number) => request<any>(`/accounts/${userId}`, { method: 'DELETE' }),

  // Settings
  getSettings: () => request<Record<string, string>>('/settings/'),
  updateSettings: (settings: Record<string, string>) =>
    request<any>('/settings/', {
      method: 'PUT',
      body: JSON.stringify({ settings }),
    }),
};
