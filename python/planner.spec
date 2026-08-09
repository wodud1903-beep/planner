# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 스펙 — 단일 exe (일정관리기)

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# holidays 라이브러리는 국가별 서브모듈을 동적으로 import 하므로 모두 포함
_hidden = collect_submodules('holidays')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('planner.ico', '.')],
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets', 'PySide6.Qt3DCore', 'PySide6.QtMultimedia',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtPdf',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='일정관리기',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 콘솔 창 없음 (GUI 전용)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='planner.ico',
)
