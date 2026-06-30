const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');
const fs = require('fs');

let mainWindow = null;
let backendProcess = null;
let isBackendReady = false; // Hamulec bezpieczeństwa zapobiegający pętli

// ── ścieżki ──────────────────────────────────────────────────────────────
function getBackendPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'backend');
  }
  return path.join(__dirname, '..', 'backend');
}

function getPythonPath() {
  // Interpreter Pythona backendu. Ustaw zmienną GRAFIK_PYTHON na ścieżkę do venv, np.
  //   .../backend/venv/bin/python (Linux/macOS)  •  ...\backend\venv\Scripts\python.exe (Windows)
  // Domyślnie próbujemy venv obok katalogu backendu, a w razie braku — Pythona z PATH.
  if (process.env.GRAFIK_PYTHON) return process.env.GRAFIK_PYTHON;
  const venvDir = path.join(getBackendPath(), '..', 'venv');
  const candidate = process.platform === 'win32'
    ? path.join(venvDir, 'Scripts', 'python.exe')
    : path.join(venvDir, 'bin', 'python');
  if (fs.existsSync(candidate)) return candidate;
  return process.platform === 'win32' ? 'python' : 'python3';
}

// ── start backendu ───────────────────────────────────────────────────────
function startBackend() {
  const python = getPythonPath();
  const backendDir = getBackendPath();

  console.log('Python:', python);
  console.log('Backend:', backendDir);

  const dbPath = path.join(backendDir, 'scheduler.db');
  if (!fs.existsSync(dbPath)) {
    console.log('Brak bazy — uruchamiam seed...');
    const seed = spawn(python, ['seed.py'], { cwd: backendDir });
    seed.stdout.on('data', d => console.log('SEED:', d.toString()));
    seed.stderr.on('data', d => console.error('SEED ERR:', d.toString()));
    seed.on('close', () => startUvicorn(python, backendDir));
  } else {
    startUvicorn(python, backendDir);
  }
}

function startUvicorn(python, backendDir) {
  backendProcess = spawn(python, [
    '-m', 'uvicorn',
    'main:app',
    '--port', '8000',
    '--host', '127.0.0.1'
  ], {
    cwd: backendDir,
  });

  backendProcess.stdout.on('data', d => console.log('API:', d.toString()));
  backendProcess.stderr.on('data', d => console.error('API ERR:', d.toString()));
  
  backendProcess.on('error', (err) => {
    dialog.showErrorBox(
      'Błąd backendu',
      `Nie można uruchomić serwera Python.\n\n${err.message}`
    );
  });

  setTimeout(() => {
    waitForBackend(30, createWindow);
  }, 1000);
}

function waitForBackend(retries, callback) {
  if (isBackendReady) return;

  const options = {
    host: '127.0.0.1',
    port: 8000,
    path: '/api/health',
    timeout: 1000
  };

  const req = http.get(options, (res) => {
    if (res.statusCode === 200) {
      if (!isBackendReady) {
        isBackendReady = true; 
        console.log('Backend gotowy! Otwieram okno...');
        callback();
      }
    } else {
      retry(retries, callback);
    }
  });

  req.on('error', () => {
    retry(retries, callback);
  });

  req.on('timeout', () => {
    req.destroy();
    retry(retries, callback);
  });
}

function retry(retries, callback) {
  if (isBackendReady) return;

  if (retries <= 0) {
    dialog.showErrorBox('Timeout', 'Backend nie wystartował w ciągu 30 sekund.');
    app.quit();
    return;
  }
  setTimeout(() => waitForBackend(retries - 1, callback), 1000);
}

// ── okno główne ──────────────────────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    title: 'Grafik Pracy',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // W trybie deweloperskim (VITE_DEV=1) ładujemy serwer Vite z hot-reloadem,
  // w przeciwnym razie zbudowany frontend serwowany przez FastAPI na :8000.
  const targetUrl = process.env.VITE_DEV ? 'http://localhost:5173' : 'http://127.0.0.1:8000';

  // POPRAWKA CACHE: Twarde wyczyszczenie pamięci podręcznej i zablokowanie cache w nagłówkach HTTP
  mainWindow.webContents.session.clearCache().then(() => {
    mainWindow.loadURL(targetUrl, {
      extraHeaders: 'pragma: no-cache\ncache-control: no-cache\n'
    });
  });

  // OPCJONALNIE: Automatyczne otwieranie narzędzi deweloperskich w celu wykrywania błędów JS
  // mainWindow.webContents.openDevTools();

  mainWindow.setMenu(null);
  
  mainWindow.on('closed', () => { 
    mainWindow = null; 
    // POPRAWKA MACOS: Jeśli zamykamy okno główne, upewnijmy się, że backend Pythona nie zostanie jako wiszący proces w tle
    if (backendProcess) {
      backendProcess.kill();
      backendProcess = null;
    }
  });
}

// ── cykl życia ───────────────────────────────────────────────────────────
app.whenReady().then(() => {
  startBackend();

  app.on('activate', () => {
    if (mainWindow === null) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
  // Zamykamy aplikację całkowicie (również na macOS), aby zapobiec blokowaniu portu 8000 przy kolejnym uruchomieniu
  app.quit();
});