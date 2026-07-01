const { app, BrowserWindow, dialog, shell } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const http = require('http')
const fs = require('fs')
const crypto = require('crypto')

// ─────────────────────────────────────────────────────────────────────────────
// Lokalo — powłoka desktopowa (Electron). Uruchamia lokalny backend FastAPI
// i wyświetla aplikację w oknie. Baza i sekrety trzymane są w katalogu danych
// użytkownika (writable), a NIE w katalogu instalacji (read-only w spakowanej appce).
// Backend: preferujemy spakowany plik wykonywalny (grafik-backend.exe) — wtedy na
// komputerze klienta NIE trzeba mieć Pythona. Fallback: uvicorn przez Pythona (dev).
// ─────────────────────────────────────────────────────────────────────────────

const PORT = Number(process.env.GRAFIK_PORT) || 8799   // wewnętrzny port backendu (rzadki, by nie kolidował)
const HOST = '127.0.0.1'

let mainWindow = null
let backendProcess = null
let isBackendReady = false

// ── ścieżki ──────────────────────────────────────────────────────────────────
function getBackendDir() {
  // Spakowana appka: backend leży w resources/backend (extraResources). Dev: ../backend.
  return app.isPackaged
    ? path.join(process.resourcesPath, 'backend')
    : path.join(__dirname, '..', 'backend')
}

function getDataDir() {
  // Katalog danych użytkownika (writable) — tu trzymamy bazę SQLite, .env, logi.
  const dir = path.join(app.getPath('userData'), 'dane')
  fs.mkdirSync(dir, { recursive: true })
  return dir
}

// Ścieżka do spakowanego backendu (PyInstaller). Zwraca null, gdy nie istnieje (tryb dev).
function getBackendExe() {
  const exe = process.platform === 'win32' ? 'grafik-backend.exe' : 'grafik-backend'
  const kandydaci = [
    path.join(getBackendDir(), 'dist', 'grafik-backend', exe),   // PyInstaller onedir
    path.join(getBackendDir(), 'dist', exe),                     // PyInstaller onefile
  ]
  return kandydaci.find((p) => fs.existsSync(p)) || null
}

// Katalog zbudowanego frontendu (statyki serwowane przez backend). Przekazujemy jawnie przez
// env, bo w spakowanej appce względne „../frontend/dist" z backendu nie trafia we właściwe miejsce.
function getFrontendDist() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'frontend', 'dist')
    : path.join(__dirname, '..', 'frontend', 'dist')
}

function getPythonPath() {
  if (process.env.GRAFIK_PYTHON) return process.env.GRAFIK_PYTHON
  for (const rel of [['.venv-test'], ['venv']]) {
    const base = path.join(getBackendDir(), ...rel)
    const cand = process.platform === 'win32'
      ? path.join(base, 'Scripts', 'python.exe')
      : path.join(base, 'bin', 'python')
    if (fs.existsSync(cand)) return cand
  }
  return process.platform === 'win32' ? 'python' : 'python3'
}

// ── sekrety (generowane raz, trwałe w katalogu danych) ────────────────────────
function wczytajLubUtworzSekrety() {
  const plik = path.join(getDataDir(), 'sekrety.json')
  try {
    return JSON.parse(fs.readFileSync(plik, 'utf-8'))
  } catch {
    const sekrety = {
      SECRET_KEY: crypto.randomBytes(48).toString('hex'),
      RCP_INGEST_TOKEN: crypto.randomBytes(24).toString('hex'),
    }
    fs.writeFileSync(plik, JSON.stringify(sekrety, null, 2), { mode: 0o600 })
    return sekrety
  }
}

function backendEnv() {
  const dataDir = getDataDir()
  const dbPath = path.join(dataDir, 'grafik.db').replace(/\\/g, '/')   // sqlite URL = forward slashes
  const sekrety = wczytajLubUtworzSekrety()
  return {
    ...process.env,
    APP_ENV: 'desktop',
    DATABASE_URL: `sqlite:///${dbPath}`,
    SECRET_KEY: sekrety.SECRET_KEY,
    RCP_INGEST_TOKEN: sekrety.RCP_INGEST_TOKEN,
    FRONTEND_DIST: getFrontendDist(),
    CORS_ORIGINS: `http://${HOST}:${PORT}`,
    PYTHONIOENCODING: 'utf-8',
    PYTHONUTF8: '1',
    GRAFIK_PORT: String(PORT),
  }
}

// ── start backendu ────────────────────────────────────────────────────────────
function startBackend() {
  const env = backendEnv()
  const backendDir = getBackendDir()
  const exe = getBackendExe()

  if (exe) {
    // Spakowany backend (PyInstaller) — bez wymogu Pythona na komputerze klienta.
    backendProcess = spawn(exe, ['--host', HOST, '--port', String(PORT)], { cwd: backendDir, env })
  } else {
    // Tryb deweloperski: uvicorn przez lokalnego Pythona.
    const python = getPythonPath()
    backendProcess = spawn(python, ['-m', 'uvicorn', 'main:app', '--host', HOST, '--port', String(PORT)],
      { cwd: backendDir, env })
  }

  backendProcess.stdout?.on('data', (d) => console.log('API:', d.toString()))
  backendProcess.stderr?.on('data', (d) => console.error('API:', d.toString()))
  backendProcess.on('error', (err) => {
    dialog.showErrorBox('Błąd serwera',
      `Nie udało się uruchomić serwera aplikacji.\n\n${err.message}\n\n` +
      (exe ? '' : 'Tryb deweloperski wymaga zainstalowanego Pythona z zależnościami backendu.'))
  })

  setTimeout(() => waitForBackend(40, createWindow), 800)
}

function waitForBackend(retries, callback) {
  if (isBackendReady) return
  const req = http.get({ host: HOST, port: PORT, path: '/api/health', timeout: 1000 }, (res) => {
    if (res.statusCode === 200 && !isBackendReady) {
      isBackendReady = true
      callback()
    } else if (res.statusCode !== 200) {
      retry(retries, callback)
    }
  })
  req.on('error', () => retry(retries, callback))
  req.on('timeout', () => { req.destroy(); retry(retries, callback) })
}

function retry(retries, callback) {
  if (isBackendReady) return
  if (retries <= 0) {
    dialog.showErrorBox('Przekroczono czas', 'Serwer aplikacji nie wystartował w wyznaczonym czasie.')
    app.quit()
    return
  }
  setTimeout(() => waitForBackend(retries - 1, callback), 1000)
}

// ── okno główne ─────────────────────────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 1024,
    minHeight: 700,
    title: 'Lokalo',
    icon: path.join(__dirname, 'assets', 'icon.ico'),
    backgroundColor: '#1C1C1E',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  })

  const targetUrl = process.env.VITE_DEV ? 'http://localhost:5173' : `http://${HOST}:${PORT}`
  mainWindow.webContents.session.clearCache().then(() => {
    mainWindow.loadURL(targetUrl, { extraHeaders: 'pragma: no-cache\ncache-control: no-cache\n' })
  })

  // Linki zewnętrzne (target=_blank) otwieramy w przeglądarce systemowej, nie w oknie appki.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http')) shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.setMenu(null)
  mainWindow.on('closed', () => { mainWindow = null })
}

// ── cykl życia ────────────────────────────────────────────────────────────────
// Pojedyncza instancja — drugie uruchomienie tylko podnosi istniejące okno.
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus() }
  })

  app.whenReady().then(() => {
    startBackend()
    app.on('activate', () => { if (mainWindow === null && isBackendReady) createWindow() })
  })
}

function zabijBackend() {
  if (backendProcess) {
    try { backendProcess.kill() } catch { /* już zamknięty */ }
    backendProcess = null
  }
}

app.on('window-all-closed', () => { zabijBackend(); app.quit() })
app.on('before-quit', zabijBackend)
process.on('exit', zabijBackend)
