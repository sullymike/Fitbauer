# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['mossbauer_fe33_gui_v2IA.py'],
    pathex=[],
    binaries=[],
    datas=[('locales', 'locales')],
    hiddenimports=[
        'mossbauer_app',
        'core', 'core.constants', 'core.physics', 'core.data_io',
        'layout', 'layout.manager', 'layout.presets', 'layout.configurator',
        'panels', 'panels.base', 'panels.header', 'panels.file_info',
        'panels.info_display', 'panels.calibration', 'panels.reference',
        'panels.sim_panel', 'panels.plot_panel',
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
    name='MossbauerFeFit',
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
    name='MossbauerFeFit',
)
