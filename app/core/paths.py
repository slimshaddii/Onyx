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
    """Return the path to app_settings.json in the project data directory."""
    return Path(__file__).parent.parent.parent / 'data' / 'app_settings.json'


def get_default_data_root() -> Path:
    """Return the platform-appropriate default directory for Onyx data."""
    system = platform.system()
    if system == 'Windows':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    elif system == 'Darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME',
                    str(Path.home() / '.local' / 'share')))
    return base / 'OnyxLauncher'


def ensure_data_dirs(root: Path) -> None:
    """Create all required Onyx subdirectories under root."""
    for sub in ('instances', 'mods', 'icons', 'logs'):
        (root / sub).mkdir(parents=True, exist_ok=True)


def instances_dir(root: Path) -> Path:
    """Return and create root/instances."""
    return _ensure_subdir(root, 'instances')


def mods_dir(root: Path) -> Path:
    """Return and create root/mods."""
    return _ensure_subdir(root, 'mods')


def icons_dir(root: Path) -> Path:
    """Return and create root/icons."""
    return _ensure_subdir(root, 'icons')


def logs_dir(root: Path) -> Path:
    """Return and create root/logs."""
    return _ensure_subdir(root, 'logs')


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
        return (Path.home() / '.config' / 'unity3d' /
                'Ludeon Studios' / 'RimWorld by Ludeon Studios')


def _ensure_subdir(root: Path, name: str) -> Path:
    p = root / name
    p.mkdir(parents=True, exist_ok=True)
    return p
