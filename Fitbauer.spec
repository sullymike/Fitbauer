# -*- mode: python ; coding: utf-8 -*-
# Ejecutable de la GUI Qt (PySide6), entrada mossbauer_qt.py.
# Construir con:  pyinstaller Fitbauer.spec


a = Analysis(
    ['mossbauer_qt.py'],
    pathex=[],
    binaries=[],
    # Los ficheros de licencia viajan con el ejecutable: la LGPLv3 de Qt/PySide6
    # obliga a entregar su texto junto a los binarios (ver THIRD-PARTY-LICENSES.md).
    datas=[
        ('locales', 'locales'),
        ('assets', 'assets'),
        ('licenses', 'licenses'),
        ('LICENSE', '.'),
        ('NOTICE', '.'),
        ('THIRD-PARTY-LICENSES.md', '.'),
    ],
    hiddenimports=[
        'core', 'core.constants', 'core.physics', 'core.data_io',
        'core.folding', 'core.fit_engine', 'core.plot_styles', 'core.batch_fit',
        'core.session', 'layout.presets',
        'mossbauer_i18n', 'mossbauer_help', 'mossbauer_distribution',
        'mossbauer_updater',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Fitbauer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Fitbauer',
)
