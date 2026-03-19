"""
Auto-detection for RimWorld install, Steam, SteamCMD, and workshop folders.
Supports Windows, Linux, and Steam Deck (including Flatpak Steam).
"""

import os
import re
import platform
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# winreg is Windows-only; import once at module level to satisfy pylint C0415.
if platform.system() == 'Windows':
    try:
        import winreg as _WINREG
    except ImportError:
        _WINREG = None  # type: ignore[assignment]
else:
    _WINREG = None  # type: ignore[assignment]

RIMWORLD_APP_ID = '294100'

# ── Executable names per platform ─────────────────────────────────────────────
RIMWORLD_EXE_NAMES = [
    'RimWorldWin64.exe',  # Windows 64-bit
    'RimWorldWin.exe',    # Windows 32-bit
    'RimWorld.exe',       # Windows generic
    'RimWorldLinux',      # Linux native
    'RimWorld.sh',        # Linux shell wrapper
    'rimworld',           # Linux lowercase
]

# ── Windows common paths ──────────────────────────────────────────────────────
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

# ── Linux / Steam Deck common paths ───────────────────────────────────────────
STEAM_COMMON_PATHS_LINUX = [
    str(Path.home() / '.steam' / 'steam'),
    str(Path.home() / '.steam' / 'root'),
    str(Path.home() / '.local' / 'share' / 'Steam'),
    '/usr/share/steam',
    '/opt/steam',
    '/home/deck/.local/share/Steam',  # Steam Deck
    str(Path.home() / '.var' / 'app' / 'com.valvesoftware.Steam'
        / 'data' / 'Steam'),           # Flatpak Steam
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

# ── macOS common paths ────────────────────────────────────────────────────────
STEAM_COMMON_PATHS_MAC = [
    str(Path.home() / 'Library' / 'Application Support' / 'Steam'),
]

STEAMCMD_COMMON_PATHS_MAC = [
    str(Path.home() / 'steamcmd' / 'steamcmd'),
    '/usr/local/bin/steamcmd',
]

# Directories to skip during Windows drive scans (performance + safety)
_DRIVE_SCAN_SKIP = frozenset({
    'windows', 'programdata', '$recycle.bin',
    'system volume information', 'recovery',
    'perflogs', 'intel', 'nvidia', 'amd',
})

# Directories worth descending into during Windows drive scans
_DRIVE_SCAN_DESCEND = frozenset({
    'games', 'steam', 'steamlibrary', 'gog games',
    'epic games', 'program files', 'program files (x86)',
    'steamapps', 'common',
})


@dataclass
class DetectionResult:
    """Holds the results of auto-detecting RimWorld, Steam, and SteamCMD."""

    rimworld_exe:        str = ''
    rimworld_path:       str = ''
    steam_path:          str = ''
    steam_workshop_path: str = ''
    steamcmd_path:       str = ''
    is_steam_copy:       bool = False
    extra_mod_paths:     list[str] = field(default_factory=list)
    rimworld_version:    str = ''
    detected_dlcs:       list[str] = field(default_factory=list)
    logs:                list[str] = field(default_factory=list)

    @property
    def found_rimworld(self) -> bool:
        """Return True if a RimWorld executable was located."""
        return bool(self.rimworld_exe)


# ── Public API ────────────────────────────────────────────────────────────────

def auto_detect_all() -> DetectionResult:
    """
    Run full auto-detection for RimWorld, Steam, workshop, and SteamCMD.

    Detection order:
      1. Steam install and library folders
      2. RimWorld inside Steam libraries
      3. RimWorld at known non-Steam paths
      4. RimWorld via drive scan (Windows only, last resort)
      5. Steam Workshop folder
      6. SteamCMD
      7. Local Mods folder
      8. RimWorld version string

    Returns a populated DetectionResult; check .found_rimworld before use.
    """
    result = DetectionResult()
    result.logs.append("Starting auto-detection...")

    steam_path, library_folders = _detect_steam_and_libraries(result)

    _detect_rimworld(result, library_folders)
    _detect_workshop(result, steam_path, library_folders)
    _detect_steamcmd(result)
    _detect_local_mods(result)
    _detect_version(result)

    if not result.rimworld_exe:
        result.logs.append(
            "Could not find RimWorld. Please set the path manually.")

    return result


def detect_rimworld_exe_only() -> Optional[str]:
    """Run full auto-detection and return the RimWorld executable path, or None."""
    result = auto_detect_all()
    return result.rimworld_exe if result.found_rimworld else None


def detect_steam_workshop_folder() -> Optional[str]:
    """Locate the Steam Workshop content folder for RimWorld, or return None."""
    steam = _find_steam_install()
    if steam:
        libs = _find_steam_library_folders(steam)
        ws   = _find_workshop_path(libs)
        if ws:
            return str(ws)
    return None


# ── auto_detect_all sub-steps ─────────────────────────────────────────────────

def _detect_steam_and_libraries(
        result: DetectionResult) -> tuple[Optional[Path], list[Path]]:
    """Find Steam and enumerate all library folders. Mutates result.logs."""
    steam_path = _find_steam_install()
    if steam_path:
        result.steam_path = str(steam_path)
        result.logs.append(f"Found Steam: {steam_path}")
    else:
        result.logs.append("Steam not found")

    library_folders: list[Path] = []
    if steam_path:
        library_folders = _find_steam_library_folders(steam_path)
        for lf in library_folders:
            result.logs.append(f"Found Steam library: {lf}")

    return steam_path, library_folders


def _detect_rimworld(result: DetectionResult,
                     library_folders: list[Path]) -> None:
    """
    Populate result with RimWorld exe/path/is_steam_copy.

    Tries Steam libraries first, then known non-Steam paths,
    then a drive scan (Windows only).
    """
    # Steam libraries
    for lib_path in library_folders:
        rw_path = lib_path / 'steamapps' / 'common' / 'RimWorld'
        if rw_path.exists():
            exe = _find_rimworld_exe(rw_path)
            if exe:
                result.rimworld_exe  = str(exe)
                result.rimworld_path = str(rw_path)
                result.is_steam_copy = True
                result.logs.append(f"Found RimWorld (Steam): {exe}")
                return

    # Known non-Steam paths
    for common_path in _get_non_steam_paths():
        p = Path(common_path)
        if p.exists():
            exe = _find_rimworld_exe(p)
            if exe:
                result.rimworld_exe  = str(exe)
                result.rimworld_path = str(p)
                result.is_steam_copy = _is_steam_copy(p)
                result.logs.append(f"Found RimWorld (non-Steam): {exe}")
                return

    # Drive scan (Windows last resort)
    if platform.system() == 'Windows':
        for drive in ['C:', 'D:', 'E:', 'F:']:
            drive_path = Path(drive + '\\')
            if drive_path.exists():
                found = _search_drive_for_rimworld(drive_path, max_depth=3)
                if found:
                    result.rimworld_exe  = str(found)
                    result.rimworld_path = str(found.parent)
                    result.is_steam_copy = _is_steam_copy(found.parent)
                    result.logs.append(f"Found RimWorld (drive scan): {found}")
                    return


def _detect_workshop(result: DetectionResult,
                     steam_path: Optional[Path],
                     library_folders: list[Path]) -> None:
    """Find the Steam Workshop content folder and add it to extra_mod_paths."""
    if not steam_path:
        return
    workshop_path = _find_workshop_path(library_folders)
    if workshop_path:
        result.steam_workshop_path = str(workshop_path)
        result.extra_mod_paths.append(str(workshop_path))
        result.logs.append(f"Found Workshop: {workshop_path}")


def _detect_steamcmd(result: DetectionResult) -> None:
    """Find SteamCMD and record its path."""
    steamcmd = _find_steamcmd()
    if steamcmd:
        result.steamcmd_path = str(steamcmd)
        result.logs.append(f"Found SteamCMD: {steamcmd}")
    else:
        result.logs.append("SteamCMD not found")


def _detect_local_mods(result: DetectionResult) -> None:
    """Add the game's local Mods folder to extra_mod_paths if it exists."""
    if not result.rimworld_path:
        return
    local_mods = Path(result.rimworld_path) / 'Mods'
    if local_mods.exists() and str(local_mods) not in result.extra_mod_paths:
        result.extra_mod_paths.append(str(local_mods))
        result.logs.append(f"Found local Mods: {local_mods}")


def _detect_version(result: DetectionResult) -> None:
    """Read Version.txt from the RimWorld folder and store the version string."""
    if not result.rimworld_path:
        return
    version_file = Path(result.rimworld_path) / 'Version.txt'
    if version_file.exists():
        try:
            result.rimworld_version = version_file.read_text(
                encoding='utf-8').strip()
            result.logs.append(f"RimWorld version: {result.rimworld_version}")
        except OSError:
            pass


# ── Low-level finders ─────────────────────────────────────────────────────────

def _get_non_steam_paths() -> list[str]:
    """Return the list of non-Steam install paths for the current platform."""
    system = platform.system()
    if system == 'Windows':
        return NON_STEAM_COMMON_PATHS_WIN
    if system == 'Darwin':
        return []
    return NON_STEAM_COMMON_PATHS_LINUX


def _find_steam_install() -> Optional[Path]:
    """
    Locate the Steam installation directory for the current platform.

    Windows: checks registry keys first, then common paths.
    Linux:   checks common paths and Flatpak locations.
    macOS:   checks the standard Application Support location.
    """
    system = platform.system()

    if system == 'Windows':
        return _find_steam_windows()
    if system == 'Darwin':
        return _find_steam_macos()
    return _find_steam_linux()


def _find_steam_windows() -> Optional[Path]:
    """Locate Steam on Windows via registry, then common paths."""
    if _WINREG is not None:
        for hive, key_path, value in [
            (_WINREG.HKEY_LOCAL_MACHINE,
             r'SOFTWARE\Valve\Steam', 'InstallPath'),
            (_WINREG.HKEY_LOCAL_MACHINE,
             r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'),
            (_WINREG.HKEY_CURRENT_USER,
             r'SOFTWARE\Valve\Steam', 'SteamPath'),
        ]:
            try:
                key         = _WINREG.OpenKey(hive, key_path)
                path_str, _ = _WINREG.QueryValueEx(key, value)
                _WINREG.CloseKey(key)
                candidate = Path(path_str)
                if candidate.exists():
                    return candidate
            except OSError:
                continue

    for p in STEAM_COMMON_PATHS_WIN:
        path = Path(p)
        if path.exists() and (path / 'steam.exe').exists():
            return path

    return None


def _find_steam_macos() -> Optional[Path]:
    """Locate Steam on macOS."""
    for p in STEAM_COMMON_PATHS_MAC:
        path = Path(p)
        if path.exists():
            return path
    return None


def _find_steam_linux() -> Optional[Path]:
    """Locate Steam on Linux or Steam Deck, including Flatpak installs."""
    for p in STEAM_COMMON_PATHS_LINUX:
        path = Path(p)
        if not path.exists():
            continue
        if ((path / 'steam.sh').exists() or
                (path / 'ubuntu12_32' / 'steam').exists() or
                (path / 'steamapps').exists()):
            return path
    return None


def _find_steam_library_folders(steam_path: Path) -> list[Path]:
    """
    Parse libraryfolders.vdf to find all Steam library locations.

    Always includes steam_path itself as the primary library.
    """
    folders: list[Path] = [steam_path]
    vdf_name = 'libraryfolders.vdf'

    for sub in ('steamapps', 'config'):
        vdf_path = steam_path / sub / vdf_name
        if not vdf_path.exists():
            continue
        try:
            content = vdf_path.read_text(encoding='utf-8', errors='replace')
            for p in re.findall(r'"path"\s+"([^"]+)"', content):
                lib_path = Path(p.replace('\\\\', '\\'))
                if lib_path.exists() and lib_path not in folders:
                    folders.append(lib_path)
        except (OSError, ValueError):
            pass

    return folders


def _find_rimworld_exe(game_path: Path) -> Optional[Path]:
    """Return the first matching RimWorld executable in game_path, or None."""
    for exe_name in RIMWORLD_EXE_NAMES:
        exe_path = game_path / exe_name
        if exe_path.exists():
            return exe_path
    return None


def _is_steam_copy(game_path: Path) -> bool:
    """Return True if game_path appears to be a Steam installation."""
    return (
        (game_path / 'steam_api64.dll').exists() or
        (game_path / 'steam_api.dll').exists() or
        'steamapps' in str(game_path).lower()
    )


def _find_workshop_path(library_folders: list[Path]) -> Optional[Path]:
    """Search library folders for the RimWorld Workshop content directory."""
    for lib in library_folders:
        workshop = lib / 'steamapps' / 'workshop' / 'content' / RIMWORLD_APP_ID
        if workshop.exists():
            return workshop
    return None


def _find_steamcmd() -> Optional[Path]:
    """
    Locate the SteamCMD executable for the current platform.

    Checks platform-specific known paths first, then falls back to PATH.
    """
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
            if path.is_file():
                return path
    else:
        for p in STEAMCMD_COMMON_PATHS_LINUX:
            path = Path(p)
            if path.is_file():
                return path

    exe_name = 'steamcmd.exe' if system == 'Windows' else 'steamcmd'
    which    = shutil.which(exe_name)
    if which:
        return Path(which)

    return None


def _search_drive_for_rimworld(root: Path,
                                max_depth: int = 3) -> Optional[Path]:
    """
    Recursively scan a drive root for a RimWorld executable (Windows only).

    Skips system and irrelevant directories for performance.
    Only descends into directories that are likely to contain games.
    """
    if max_depth <= 0:
        return None
    try:
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            name_lower = entry.name.lower()
            if name_lower.startswith('.') or name_lower in _DRIVE_SCAN_SKIP:
                continue
            if 'rimworld' in name_lower:
                exe = _find_rimworld_exe(entry)
                if exe:
                    return exe
            if max_depth > 1 and name_lower in _DRIVE_SCAN_DESCEND:
                found = _search_drive_for_rimworld(entry, max_depth - 1)
                if found:
                    return found
    except PermissionError:
        pass
    return None
