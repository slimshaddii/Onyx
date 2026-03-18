# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[
        # App resources
        ('app/ui/resources/onyx_icon.png',  'app/ui/resources'),
        ('app/ui/resources/onyx_icon.ico',  'app/ui/resources'),
        ('app/ui/resources/onyx_icon.icns', 'app/ui/resources'),
        # Data files
        ('data/known_conflicts.json', 'data'),
        # Include app_settings.json only if it exists
        # (it will be created on first run if missing)
    ],
    hiddenimports=[
        # PyQt6 modules that PyInstaller may miss
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebChannel',
        'PyQt6.sip',
        # toposort
        'toposort',
        # App modules
        'app.core.app_settings',
        'app.core.instance',
        'app.core.instance_manager',
        'app.core.launcher',
        'app.core.mod_sort',
        'app.core.mod_cache',
        'app.core.mod_history',
        'app.core.mod_linker',
        'app.core.mod_watcher',
        'app.core.modlist',
        'app.core.rimworld',
        'app.core.save_parser',
        'app.core.conflict_db',
        'app.core.def_scanner',
        'app.core.dep_resolver',
        'app.core.log_parser',
        'app.core.onyxpack',
        'app.core.paths',
        'app.core.steam_integration',
        'app.core.steamcmd',
        'app.ui.styles',
        'app.ui.main_window',
        'app.ui.instance_list',
        'app.ui.instance_detail',
        'app.ui.instance_edit',
        'app.ui.instance_new_dialog',
        'app.ui.launch_dialog',
        'app.ui.log_viewer',
        'app.ui.mod_search_dialog',
        'app.ui.settings_dialog',
        'app.ui.modeditor.dialog',
        'app.ui.modeditor.drag_list',
        'app.ui.modeditor.item_builder',
        'app.ui.modeditor.issue_checker',
        'app.ui.modeditor.mod_actions',
        'app.ui.modeditor.mod_context',
        'app.ui.modeditor.mod_fixes',
        'app.ui.modeditor.mod_io',
        'app.ui.modeditor.preview_panel',
        'app.ui.modeditor.history_panel',
        'app.ui.modeditor.conflict_dialog',
        'app.ui.modeditor.def_scan_dialog',
        'app.ui.modeditor.library_dialog',
        'app.ui.modeditor.download_dialog',
        'app.ui.detail.detail_header',
        'app.ui.detail.detail_actions',
        'app.ui.detail.detail_info',
        'app.ui.detail.detail_saves',
        'app.ui.detail.detail_notes',
        'app.ui.detail.save_compat',
        'app.utils.file_utils',
        'app.utils.xml_utils',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude things we don't need to keep size down
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'test',
        'unittest',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure, cipher=block_cipher)

# ── Platform-specific icon path ───────────────────────────────────────────────
if sys.platform == 'win32':
    icon = 'app/ui/resources/onyx_icon.ico'
elif sys.platform == 'darwin':
    icon = 'app/ui/resources/onyx_icon.icns'  # need .icns for Mac
else:
    icon = 'app/ui/resources/onyx_icon.png'   # Linux uses PNG

exe = EXE(
    pyz,
    a.scripts,
    [],                         # No binaries merged — folder build
    exclude_binaries=True,      # Keep as folder, not single EXE
    name='OnyxLauncher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        # Don't compress Qt libs — breaks them
        'Qt6*.dll',
        'Qt6*.so',
        'libQt6*.so*',
    ],
    console=False,              # No CMD window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        'Qt6*.dll',
        'Qt6*.so',
        'libQt6*.so*',
    ],
    name='OnyxLauncher-Beta',   # Output folder name in dist/
)