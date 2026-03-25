import { useEffect, useState } from 'react';
import { Save, Loader2 } from 'lucide-react';
import { api } from '../api/client';

const FIELDS = [
  { key: 'tracks_per_genre', label: 'TRACKS PER GENRE', type: 'number' },
  { key: 'download_dir', label: 'DOWNLOAD DIRECTORY', type: 'text' },
  { key: 'min_playback_count', label: 'MIN PLAY COUNT', type: 'number' },
  { key: 'min_duration_sec', label: 'MIN DURATION (SEC)', type: 'number' },
  { key: 'max_duration_sec', label: 'MAX DURATION (SEC)', type: 'number' },
  { key: 'api_delay', label: 'API DELAY (SEC)', type: 'number' },
  { key: 'trending_recency_days', label: 'TRENDING WINDOW (DAYS)', type: 'number' },
  { key: 'auto_analyze', label: 'AUTO-ANALYZE ON DOWNLOAD', type: 'toggle' },
];

export default function Settings() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => { api.getSettings().then(setSettings); }, []);

  const save = async () => {
    setSaving(true);
    await api.updateSettings(settings);
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div>
      <h2 className="text-xl font-mono font-bold tracking-wider mb-6 glow-text">SETTINGS</h2>

      <div className="max-w-md space-y-5">
        {FIELDS.map(({ key, label, type }) => (
          <div key={key}>
            <label className="block text-[10px] font-mono text-[var(--color-text-dim)] tracking-widest mb-1.5">{label}</label>
            {type === 'toggle' ? (
              <button onClick={() => setSettings({ ...settings, [key]: settings[key] === 'true' ? 'false' : 'true' })}
                className={`flex items-center gap-2 px-3 py-2 rounded border font-mono text-xs transition-colors ${
                  settings[key] === 'true'
                    ? 'bg-[var(--color-glow-dim)] border-[var(--color-glow)] text-[var(--color-glow)]'
                    : 'bg-[var(--color-surface-3)] border-[var(--color-border)] text-[var(--color-text-dim)]'
                }`}>
                {settings[key] === 'true' ? 'ON — BPM + KEY detected after each download' : 'OFF — Analyze manually from the Analyze page'}
              </button>
            ) : (
              <input type={type} value={settings[key] || ''}
                onChange={e => setSettings({ ...settings, [key]: e.target.value })}
                className="w-full bg-[var(--color-surface-3)] border border-[var(--color-border)] rounded px-3 py-2 text-sm font-mono text-[var(--color-text)] focus:outline-none focus:border-[var(--color-border-glow)]" />
            )}
          </div>
        ))}

        <button onClick={save} disabled={saving}
          className="glow-btn px-6 py-2.5 rounded text-xs font-mono flex items-center gap-2 mt-6">
          {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          {saved ? 'SAVED' : 'SAVE SETTINGS'}
        </button>
      </div>
    </div>
  );
}
