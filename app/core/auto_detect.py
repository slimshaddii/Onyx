"""
Auto-detection for RimWorld install, Steam, SteamCMD, workshop folders.
Supports Windows, Linux, and Steam Deck.
"""

import os
import re
import platform
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

RIMWORLD_APP_ID = '294100'

# ── Executable names per platform ────────────────────────────────────────────
RIMWORLD_EXE_NAMES = [
    'RimWorldWin64.exe',   # Windows 64-bit
    'RimWorldWin.exe',     # Windows 32-bit
    'RimWorld.exe',        # Windows generic
    'RimWorldLinux',       # Linux native
    'RimWorld.sh',         # Linux shell wrapper
    'rimworld',            # Linux lowercase
]

# ── Windows paths ─────────────────────────────────────────────────────────────
STEAM_COMMON_PATHS_WIN = [
    r'C:\Program Files (x86)\Steam',
    r'C:\Program Files\Steam',
    r'D:\Steam', r'D:\SteamLibrary',
    r'E:\Steam', r'E:\SteamLibrary',
    r'F:\Steam', r'F:\SteamLibrary',
]

STEAMCMD_COMMON_PATHS_WIN = [
    r'C:\steamcmd', r'C:\SteamCMD',
    r'D:\steamcmd', r'D:\SteamCMD',
    os.path.expanduser(r'~\steamcmd'),
    os.path.expanduser(r'~\Desktop\steamcmd'),
    os.path.expanduser(r'~\Downloads\steamcmd'),
]

NON_STEAM_COMMON_PATHS_WIN = [
    r'C:\Games\RimWorld', r'D:\Games\RimWorld',
    r'E:\Games\RimWorld', r'C:\GOG Games\RimWorld',
    r'D:\GOG Games\RimWorld',
]

# ── Linux / Steam Deck paths ──────────────────────────────────────────────────
STEAM_COMMON_PATHS_LINUX = [
    str(Path.home() / '.steam' / 'steam'),
    str(Path.home() / '.steam' / 'root'),
    str(Path.home() / '.local' / 'share' / 'Steam'),
    '/usr/share/steam',
    '/opt/steam',
    # Steam Deck
    '/home/deck/.local/share/Steam',
    str(Path.home() / '.var' / 'app' / 'com.valvesoftware.Steam'
        / 'data' / 'Steam'),   # Flatpak Steam
]

STEAMCMD_COMMON_PATHS_LINUX = [
    str(Path.home() / 'steamcmd' / 'steamcmd'),
    str(Path.home() / '.steamcmd' / 'steamcmd'),
    '/usr/games/steamcmd',
    '/usr/bin/steamcmd',
    '/opt/steamcmd/steamcmd',
]

NON_STEAM_COMMON_PATHS_LINUX = [
    str(Path.home() / 'Games' / 'RimWorld'),
    str(Path.home() / 'games' / 'RimWorld'),
    '/opt/RimWorld',
]

# ── macOS paths ───────────────────────────────────────────────────────────────
STEAM_COMMON_PATHS_MAC = [
    str(Path.home() / 'Library' / 'Application Support' / 'Steam'),
]

STEAMCMD_COMMON_PATHS_MAC = [
    str(Path.home() / 'steamcmd' / 'steamcmd'),
    '/usr/local/bin/steamcmd',
]


@dataclass
class DetectionResult:
    rimworld_exe:         str = ''
    rimworld_path:        str = ''
    steam_path:           str = ''
    steam_workshop_path:  str = ''
    steamcmd_path:        str = ''
    is_steam_copy:        bool = False
    extra_mod_paths:      list[str] = field(default_factory=list)
    rimworld_version:     str = ''
    detected_dlcs:        list[str] = field(default_factory=list)
    logs:                 list[str] = field(default_factory=list)

    @property
    def found_rimworld(self) -> bool:
        return bool(self.rimworld_exe)


def auto_detect_all() -> DetectionResult:
    result = DetectionResult()
    result.logs.append("Starting auto-detection...")

    steam_path = _find_steam_install()
    if steam_path:
        result.steam_path = str(steam_path)
        result.logs.append(f"Found Steam: {steam_path}")
    else:
        result.logs.append("Steam not found")

    library_folders = []
    if steam_path:
        library_folders = _find_steam_library_folders(Path(steam_path))
        for lf in library_folders:
            result.logs.append(f"Found Steam library: {lf}")

    # Find RimWorld in Steam libraries
    for lib_path in library_folders:
        rw_path = lib_path / 'steamapps' / 'common' / 'RimWorld'
        if rw_path.exists():
            exe = _find_rimworld_exe(rw_path)
            if exe:
                result.rimworld_exe  = str(exe)
                result.rimworld_path = str(rw_path)
                result.is_steam_copy = True
                result.logs.append(f"Found RimWorld (Steam): {exe}")
                break

    # Non-Steam paths
    if not result.rimworld_exe:
        non_steam_paths = _get_non_steam_paths()
        for common_path in non_steam_paths:
            p = Path(common_path)
            if p.exists():
                exe = _find_rimworld_exe(p)
                if exe:
                    result.rimworld_exe  = str(exe)
                    result.rimworld_path = str(p)
                    result.is_steam_copy = _is_steam_copy(p)
                    result.logs.append(f"Found RimWorld (non-Steam): {exe}")
                    break

    # Drive scan (Windows only)
    if not result.rimworld_exe and platform.system() == 'Windows':
        for drive in ['C:', 'D:', 'E:', 'F:']:
            drive_path = Path(drive + '\\')
            if drive_path.exists():
                found = _search_drive_for_rimworld(drive_path, max_depth=3)
                if found:
                    result.rimworld_exe  = str(found)
                    result.rimworld_path = str(found.parent)
                    result.is_steam_copy = _is_steam_copy(found.parent)
                    result.logs.append(f"Found RimWorld (drive scan): {found}")
                    break

    # Workshop
    if steam_path:
        workshop_path = _find_workshop_path(library_folders)
        if workshop_path:
            result.steam_workshop_path = str(workshop_path)
            result.extra_mod_paths.append(str(workshop_path))
            result.logs.append(f"Found Workshop: {workshop_path}")

    # SteamCMD
    steamcmd = _find_steamcmd()
    if steamcmd:
        result.steamcmd_path = str(steamcmd)
        result.logs.append(f"Found SteamCMD: {steamcmd}")
    else:
        result.logs.append("SteamCMD not found")

    # Local Mods folder
    if result.rimworld_path:
        local_mods = Path(result.rimworld_path) / 'Mods'
        if local_mods.exists() and str(local_mods) not in result.extra_mod_paths:
            result.extra_mod_paths.append(str(local_mods))
            result.logs.append(f"Found local Mods: {local_mods}")

    # Version
    if result.rimworld_path:
        version_file = Path(result.rimworld_path) / 'Version.txt'
        if version_file.exists():
            try:
                result.rimworld_version = version_file.read_text().strip()
                result.logs.append(f"RimWorld version: {result.rimworld_version}")
            except Exception:
                pass

    if not result.rimworld_exe:
        result.logs.append(
            "Could not find RimWorld. Please set the path manually.")

    return result


# ── Platform helpers ──────────────────────────────────────────────────────────

def _get_non_steam_paths() -> list[str]:
    system = platform.system()
    if system == 'Windows':
        return NON_STEAM_COMMON_PATHS_WIN
    elif system == 'Darwin':
        return []
    else:
        return NON_STEAM_COMMON_PATHS_LINUX


def _find_steam_install() -> Optional[Path]:
    system = platform.system()

    if system == 'Windows':
        try:
            import winreg
            for key_path in [
                r'SOFTWARE\Valve\Steam',
                r'SOFTWARE\WOW6432Node\Valve\Steam',
            ]:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                    install_path, _ = winreg.QueryValueEx(key, 'InstallPath')
                    winreg.CloseKey(key)
                    if install_path and Path(install_path).exists():
                        return Path(install_path)
                except (OSError, FileNotFoundError):
                    continue
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                     r'SOFTWARE\Valve\Steam')
                steam_path, _ = winreg.QueryValueEx(key, 'SteamPath')
                winreg.CloseKey(key)
                if steam_path and Path(steam_path).exists():
                    return Path(steam_path)
            except (OSError, FileNotFoundError):
                pass
        except ImportError:
            pass
        for p in STEAM_COMMON_PATHS_WIN:
            path = Path(p)
            if path.exists() and (path / 'steam.exe').exists():
                return path

    elif system == 'Darwin':
        for p in STEAM_COMMON_PATHS_MAC:
            path = Path(p)
            if path.exists():
                return path

    else:
        # Linux / Steam Deck
        for p in STEAM_COMMON_PATHS_LINUX:
            path = Path(p)
            if not path.exists():
                continue
            # Check for steam executable or key subdirs
            if ((path / 'steam.sh').exists() or
                    (path / 'ubuntu12_32' / 'steam').exists() or
                    (path / 'steamapps').exists()):
                return path

    return None


def _find_steam_library_folders(steam_path: Path) -> list[Path]:
    folders = [steam_path]
    for vdf_name in ('libraryfolders.vdf',):
        for sub in ('steamapps', 'config'):
            vdf_path = steam_path / sub / vdf_name
            if vdf_path.exists():
                try:
                    content = vdf_path.read_text(
                        encoding='utf-8', errors='replace')
                    paths = re.findall(r'"path"\s+"([^"]+)"', content)
                    for p in paths:
                        lib_path = Path(p.replace('\\\\', '\\'))
                        if lib_path.exists() and lib_path not in folders:
                            folders.append(lib_path)
                except Exception:
                    pass
    return folders


def _find_rimworld_exe(game_path: Path) -> Optional[Path]:
    for exe_name in RIMWORLD_EXE_NAMES:
        exe_path = game_path / exe_name
        if exe_path.exists():
            return exe_path
    return None


def _is_steam_copy(game_path: Path) -> bool:
    return (
        (game_path / 'steam_api64.dll').exists() or
        (game_path / 'steam_api.dll').exists() or
        'steamapps' in str(game_path).lower()
    )


def _find_workshop_path(library_folders: list[Path]) -> Optional[Path]:
    for lib in library_folders:
        workshop = (lib / 'steamapps' / 'workshop' /
                    'content' / RIMWORLD_APP_ID)
        if workshop.exists():
            return workshop
    return None


def _find_steamcmd() -> Optional[Path]:
    system = platform.system()

    if system == 'Windows':
        for p in STEAMCMD_COMMON_PATHS_WIN:
            path = Path(p)
            exe  = path / 'steamcmd.exe'
            if exe.exists():
                return exe
            if path.exists() and path.suffix.lower() == '.exe':
                return path
    elif system == 'Darwin':
        for p in STEAMCMD_COMMON_PATHS_MAC:
            path = Path(p)
            if path.exists() and path.is_file():
                return path
    else:
        # Linux
        for p in STEAMCMD_COMMON_PATHS_LINUX:
            path = Path(p)
            if path.exists() and path.is_file():
                return path

    # Check PATH on all platforms
    exe_name = 'steamcmd.exe' if platform.system() == 'Windows' else 'steamcmd'
    which = shutil.which(exe_name)
    if which:
        return Path(which)

    return None


def _search_drive_for_rimworld(root: Path,
                                max_depth: int = 3) -> Optional[Path]:
    """Windows-only drive scan."""
    if max_depth <= 0:
        return None
    try:
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            name_lower = entry.name.lower()
            if name_lower.startswith('.') or name_lower in (
                'windows', 'programdata', '$recycle.bin',
                'system volume information', 'recovery',
                'perflogs', 'intel', 'nvidia', 'amd',
            ):
                continue
            if 'rimworld' in name_lower:
                exe = _find_rimworld_exe(entry)
                if exe:
                    return exe
            if max_depth > 1 and name_lower in (
                'games', 'steam', 'steamlibrary', 'gog games',
                'epic games', 'program files', 'program files (x86)',
                'steamapps', 'common',
            ):
                found = _search_drive_for_rimworld(entry, max_depth - 1)
                if found:
                    return found
    except PermissionError:
        pass
    return None


def detect_rimworld_exe_only() -> Optional[str]:
    result = auto_detect_all()
    return result.rimworld_exe if result.found_rimworld else None


def detect_steam_workshop_folder() -> Optional[str]:
    steam = _find_steam_install()
    if steam:
        libs = _find_steam_library_folders(steam)
        ws   = _find_workshop_path(libs)
        if ws:
            return str(ws)
    return None