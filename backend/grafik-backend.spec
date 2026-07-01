# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — spakowanie backendu FastAPI/uvicorn do samodzielnego pliku wykonywalnego,
# aby aplikacja desktopowa (Electron) nie wymagała Pythona na komputerze klienta.
#
# Budowanie (w katalogu backend/, w aktywnym venv z zależnościami produkcyjnymi + pyinstaller):
#     pip install pyinstaller
#     pyinstaller grafik-backend.spec --noconfirm
# Wynik: dist/grafik-backend/grafik-backend.exe (onedir — szybki start).

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

here = os.path.abspath(os.getcwd())

# Dane potrzebne w runtime: konfiguracja + migracje Alembica (init_db robi upgrade head).
datas = [
    ('alembic.ini', '.'),
    ('migrations', 'migrations'),
]
datas += collect_data_files('openpyxl')

# uvicorn ładuje pętlę/protokoły dynamicznie → trzeba je jawnie dołączyć.
hiddenimports = [
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.protocols.websockets.websockets_impl',
    'anyio._backends._asyncio',
    'passlib.handlers.bcrypt',
]
hiddenimports += collect_submodules('routers')

a = Analysis(
    ['desktop_launcher.py'],
    pathex=[here],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'tests', 'factories'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='grafik-backend',
    console=False,          # bez okna konsoli — Electron zarządza procesem
    disable_windowed_traceback=False,
    argv_emulation=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name='grafik-backend',
)
