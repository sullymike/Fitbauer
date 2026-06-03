# -*- mode: python ; coding: utf-8 -*-
# Ejecutable de la GUI Qt (PySide6). Equivalente al de Tk (MossbauerFeFit.spec)
# pero con entrada mossbauer_qt.py. Construir con:  pyinstaller MossbauerFeFit-Qt.spec


a = Analysis(
    ['mossbauer_qt.py'],
    pathex=[],
    binaries=[],
    datas=[('locales', 'locales'), ('assets', 'assets')],
    hiddenimports=[
        'core', 'core.constants', 'core.physics', 'core.data_io',
        'core.folding', 'core.fit_engine', 'core.plot_styles', 'core.batch_fit',
        'mossbauer_i18n', 'mossbauer_help', 'mossbauer_distribution',
        'mossbauer_updater', 'mossbauer_updater_ui',
        # Plotly se importa de forma diferida al abrir/exportar el gráfico HTML.
        'plotly', 'plotly.graph_objects', 'plotly.subplots',
        # Visor HTML Plotly embebido en la propia aplicación Qt.
        'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore',
        # Importado de forma diferida por la GUI Qt (CHANGELOG_PATH).
        'mossbauer_fe33_gui_v2IA',
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
    name='MossbauerFeFit-Qt',
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
    name='MossbauerFeFit-Qt',
)
