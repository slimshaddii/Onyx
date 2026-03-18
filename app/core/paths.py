"""
Directory structure:
  Program dir   → where main.py lives
  Data dir      → where Onyx stores instances/mods/icons/logs
  Game dir      → where RimWorld is installed
"""

import os
import platform
from pathlib import Path


def settings_path() -> Path:
    return Path(__file__).parent.parent.parent / 'data' / 'app_settings.json'


def get_default_data_root() -> Path:
    system = platform.system()
    if system == 'Windows':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    elif system == 'Darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        # Linux — respect XDG_DATA_HOME
        base = Path(os.environ.get('XDG_DATA_HOME',
                    str(Path.home() / '.local' / 'share')))
    return base / 'OnyxLauncher'


def ensure_data_dirs(root: Path):
    for sub in ('instances', 'mods', 'icons', 'logs'):
        (root / sub).mkdir(parents=True, exist_ok=True)


def instances_dir(root: Path) -> Path:
    p = root / 'instances'
    p.mkdir(parents=True, exist_ok=True)
    return p


def mods_dir(root: Path) -> Path:
    p = root / 'mods'
    p.mkdir(parents=True, exist_ok=True)
    return p


def icons_dir(root: Path) -> Path:
    p = root / 'icons'
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir(root: Path) -> Path:
    p = root / 'logs'
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_default_rw_data() -> Path:
    """Default RimWorld save data location (without -savedatafolder)."""
    system = platform.system()
    if system == 'Windows':
        appdata = Path(os.environ.get('APPDATA', str(Path.home())))
        return (appdata / '..' / 'LocalLow' /
                'Ludeon Studios' / 'RimWorld by Ludeon Studios')
    elif system == 'Darwin':
        return (Path.home() / 'Library' / 'Application Support' /
                'RimWorld by Ludeon Studios')
    else:
        # Linux
        return (Path.home() / '.config' / 'unity3d' /
                'Ludeon Studios' / 'RimWorld by Ludeon Studios')