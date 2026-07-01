#requires -version 5
<#
.SYNOPSIS
  Buduje instalator aplikacji desktopowej "Grafik Pracy" na Windows.

.DESCRIPTION
  Trzy kroki:
    1) Frontend  — Vite build -> frontend\dist
    2) Backend   — PyInstaller pakuje serwer FastAPI do dist\grafik-backend\grafik-backend.exe
                   (dzieki temu na komputerze klienta NIE trzeba Pythona)
    3) Instalator— electron-builder (NSIS) -> electron\dist-installer\GrafikPracy-Setup-<wersja>.exe

.PARAMETER SkipBackend
  Pomija pakowanie backendu (instalator zadziala wtedy tylko tam, gdzie jest Python z zaleznosciami).

.PARAMETER Python
  Komenda interpretera do stworzenia venv builda (domyslnie 'py -3.11', fallback 'python').

.EXAMPLE
  .\build-desktop.ps1
#>
param(
  [switch]$SkipBackend,
  [string]$Python = ""
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Write-Host "== Grafik Pracy - build instalatora desktopowego ==" -ForegroundColor Cyan

# 1) FRONTEND ------------------------------------------------------------------
Write-Host "[1/3] Build frontendu (Vite)..." -ForegroundColor Yellow
npm --prefix "$root\frontend" ci
npm --prefix "$root\frontend" run build

# 2) BACKEND -> EXE ------------------------------------------------------------
if (-not $SkipBackend) {
  Write-Host "[2/3] Pakowanie backendu (PyInstaller)..." -ForegroundColor Yellow
  $venv = Join-Path $root "backend\.venv-build"
  if (-not (Test-Path $venv)) {
    if ($Python -ne "") { Invoke-Expression "$Python -m venv `"$venv`"" }
    else { py -3.11 -m venv $venv }
  }
  $py = Join-Path $venv "Scripts\python.exe"
  & $py -m pip install --upgrade pip
  & $py -m pip install -r (Join-Path $root "backend\requirements.txt") pyinstaller
  Push-Location (Join-Path $root "backend")
  try { & $py -m PyInstaller grafik-backend.spec --noconfirm } finally { Pop-Location }
} else {
  Write-Host "[2/3] Pomijam backend (-SkipBackend)." -ForegroundColor DarkYellow
  New-Item -ItemType Directory -Force -Path (Join-Path $root "backend\dist") | Out-Null
}

# 3) INSTALATOR ----------------------------------------------------------------
Write-Host "[3/3] Instalator (electron-builder NSIS)..." -ForegroundColor Yellow
npm --prefix "$root\electron" install
npm --prefix "$root\electron" run dist

Write-Host "== Gotowe. Instalator: electron\dist-installer\ ==" -ForegroundColor Green
