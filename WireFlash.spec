# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para WireFlash (Windows y Linux).

Genera UN SOLO ejecutable autocontenido en dist/:
    Windows -> dist\\WireFlash.exe
    Linux   -> dist/WireFlash   (usado luego por build-appimage.sh)

Todas las dependencias (incluido PySide6 y el runtime de Python) quedan dentro
del ejecutable; no se necesita carpeta _internal ni nada extra al distribuir.

Uso:
    pyinstaller --noconfirm WireFlash.spec
"""

from PyInstaller.utils.hooks import collect_all

block_cipher = None

pyside6_datas, pyside6_binaries, pyside6_hiddenimports = collect_all('PySide6')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=pyside6_binaries,
    datas=[('wireflash/data', 'wireflash/data')] + pyside6_datas,
    hiddenimports=pyside6_hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'PySide6.scripts'],
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
    name='WireFlash',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
)
