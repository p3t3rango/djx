import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { PlayerProvider } from './components/PlayerContext';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import GenreBrowser from './pages/GenreBrowser';
import SearchPage from './pages/Search';
import CuratedAccounts from './pages/CuratedAccounts';
import Downloads from './pages/Downloads';
import Playlists from './pages/Playlists';
import Settings from './pages/Settings';

export default function App() {
  return (
    <BrowserRouter>
      <PlayerProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/genres" element={<GenreBrowser />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/accounts" element={<CuratedAccounts />} />
            <Route path="/downloads" element={<Downloads />} />
            <Route path="/playlists" element={<Playlists />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
        </Routes>
      </PlayerProvider>
    </BrowserRouter>
  );
}
