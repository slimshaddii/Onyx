"""
Directory structure:
  Program dir   → where main.py lives
  Data dir      → where Onyx stores instances/mods/icons/logs
  Game dir      → where RimWorld is installed
"""

import os
from pathlib import Path


# ── FIX #1: Single source of truth for settings file location ────
def settings_path() -> Path:
    """Path to the application settings JSON file."""
    return Path(__file__).parent.parent.parent / 'data' / 'app_settings.json'


def get_default_data_root() -> Path:
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    else:
        base = Path.home() / '.local' / 'share'
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
    if os.name == 'nt':
        appdata = Path(os.environ.get('APPDATA', str(Path.home())))
        return appdata / '..' / 'LocalLow' / 'Ludeon Studios' / 'RimWorld by Ludeon Studios'
    return Path.home() / '.config' / 'unity3d' / 'Ludeon Studios' / 'RimWorld by Ludeon Studios'