import { NavLink, Outlet } from 'react-router-dom';
import { LayoutDashboard, Music, Search, Users, Download, Settings, Radio, ListMusic } from 'lucide-react';
import { usePlayer } from './PlayerContext';
import PlayerBar from './PlayerBar';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/genres', icon: Music, label: 'Discover' },
  { to: '/search', icon: Search, label: 'Search' },
  { to: '/accounts', icon: Users, label: 'Channels' },
  { to: '/downloads', icon: Download, label: 'Library' },
  { to: '/playlists', icon: ListMusic, label: 'Playlists' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export default function Layout() {
  const player = usePlayer();
  const hasPlayer = !!(player.playingTrack || player.embedTrack);

  return (
    <div className="flex h-screen bg-[var(--color-surface)] text-[var(--color-text)]">
      <nav className="w-52 bg-[var(--color-surface-2)] border-r border-[var(--color-border)] flex flex-col relative scanlines">
        <div className="p-5 border-b border-[var(--color-border)]">
          <div className="flex items-center gap-2">
            <Radio size={18} className="text-[var(--color-glow)]" />
            <h1 className="text-base font-mono font-bold glow-text tracking-wider">DJX</h1>
          </div>
          <p className="text-[10px] font-mono text-[var(--color-text-dim)] mt-1 tracking-widest">DJ TOOLKIT</p>
        </div>
        <div className="flex-1 py-3">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-5 py-2.5 text-xs font-mono tracking-wide transition-all duration-200 ${
                  isActive
                    ? 'text-[var(--color-glow)] bg-[var(--color-glow-dim)] border-r-2 border-[var(--color-glow)]'
                    : 'text-[var(--color-text-dim)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-3)]'
                }`
              }
            >
              <Icon size={15} />
              {label.toUpperCase()}
            </NavLink>
          ))}
        </div>
      </nav>
      <main className={`flex-1 overflow-auto p-8 ${hasPlayer ? 'pb-24' : ''}`}>
        <Outlet />
      </main>
      <PlayerBar />
    </div>
  );
}
