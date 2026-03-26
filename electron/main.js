const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');
const fs = require('fs');

let mainWindow = null;
let pythonProcess = null;
const PORT = 8000;
const isDev = !app.isPackaged;

// Data directory
const dataDir = path.join(app.getPath('userData'), 'data');
const downloadsDir = path.join(app.getPath('music'), 'DJX');

function ensureDirectories() {
  [dataDir, downloadsDir].forEach(dir => {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  });
}

function getBackendPath() {
  if (isDev) {
    return path.join(__dirname, '..');
  }
  return path.join(process.resourcesPath, 'backend');
}

function getFrontendPath() {
  if (isDev) {
    return path.join(__dirname, '..', 'frontend', 'dist');
  }
  return path.join(process.resourcesPath, 'frontend');
}

function findPython() {
  // Only search known system paths — never user-writable directories
  const candidates = ['/usr/bin/python3', '/usr/local/bin/python3',
    '/opt/homebrew/bin/python3', '/Library/Developer/CommandLineTools/usr/bin/python3'];
  for (const cmd of candidates) {
    try {
      const { status } = require('child_process').spawnSync(cmd, ['--version'], { stdio: 'ignore' });
      if (status === 0) return cmd;
    } catch {}
  }
  return null;
}

function checkDeps(python) {
  try {
    const { status } = require('child_process').spawnSync(
      python, ['-c', 'import soundcloud; import fastapi; import essentia'],
      { stdio: 'ignore', env: { ...process.env, PYTHONPATH: getBackendPath() } }
    );
    return status === 0;
  } catch {
    return false;
  }
}

function installDeps(python) {
  return new Promise((resolve, reject) => {
    const reqPath = path.join(getBackendPath(), 'requirements.txt');
    const proc = spawn(python, ['-m', 'pip', 'install', '--user', '-r', reqPath], {
      stdio: 'pipe'
    });

    let output = '';
    proc.stdout.on('data', d => { output += d.toString(); });
    proc.stderr.on('data', d => { output += d.toString(); });

    proc.on('close', code => {
      if (code === 0) resolve();
      else reject(new Error(`pip install failed (code ${code}): ${output.slice(-500)}`));
    });
  });
}

function startPython(python) {
  const backendPath = getBackendPath();
  const dbPath = path.join(dataDir, 'djx.db');

  // Set environment — only pass required vars (principle of least privilege)
  const env = {
    PATH: process.env.PATH,
    HOME: process.env.HOME,
    LANG: process.env.LANG || 'en_US.UTF-8',
    PYTHONPATH: backendPath,
    DJX_DB_PATH: dbPath,
    DJX_DOWNLOAD_DIR: downloadsDir,
    DJX_FRONTEND_DIR: getFrontendPath(),
  };

  pythonProcess = spawn(python, [
    '-m', 'uvicorn', 'api.main:app',
    '--host', '127.0.0.1',
    '--port', String(PORT),
  ], {
    cwd: backendPath,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  pythonProcess.stdout.on('data', d => console.log('[python]', d.toString().trim()));
  pythonProcess.stderr.on('data', d => console.log('[python]', d.toString().trim()));

  pythonProcess.on('close', code => {
    console.log(`Python process exited with code ${code}`);
    pythonProcess = null;
  });
}

function waitForServer(timeout = 30000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const check = () => {
      const req = http.get(`http://127.0.0.1:${PORT}/api/health`, res => {
        if (res.statusCode === 200) resolve();
        else setTimeout(check, 500);
      });
      req.on('error', () => {
        if (Date.now() - start > timeout) reject(new Error('Server start timeout'));
        else setTimeout(check, 500);
      });
      req.end();
    };
    check();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 600,
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#0a0a0a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      enableRemoteModule: false,
    },
  });

  mainWindow.loadURL(`http://127.0.0.1:${PORT}`);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

async function boot() {
  ensureDirectories();

  // Find Python
  const python = findPython();
  if (!python) {
    dialog.showErrorBox('Python Not Found',
      'DJX requires Python 3.9+. Please install it from python.org or via Xcode Command Line Tools:\n\nxcode-select --install');
    app.quit();
    return;
  }
  console.log('Using Python:', python);

  // Check/install dependencies
  if (!checkDeps(python)) {
    console.log('Installing Python dependencies...');
    try {
      // Show a loading window
      const loadWin = new BrowserWindow({
        width: 400, height: 200, frame: false,
        backgroundColor: '#0a0a0a', resizable: false,
      });
      loadWin.loadURL(`data:text/html,
        <html><body style="background:#0a0a0a;color:#00ffc8;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
        <div style="text-align:center"><p style="font-size:14px">Installing dependencies...</p><p style="font-size:11px;color:#666">This only happens once</p></div>
        </body></html>`);

      await installDeps(python);
      loadWin.close();
    } catch (err) {
      dialog.showErrorBox('Install Failed', err.message);
      app.quit();
      return;
    }
  }

  // Start Python backend
  console.log('Starting backend...');
  startPython(python);

  try {
    await waitForServer();
    console.log('Backend ready');
  } catch {
    dialog.showErrorBox('Server Error', 'Failed to start the DJX backend. Check the logs.');
    app.quit();
    return;
  }

  createWindow();
}

app.whenReady().then(boot);

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
  app.quit();
});

app.on('before-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
});

app.on('activate', () => {
  if (mainWindow === null && pythonProcess) {
    createWindow();
  }
});
