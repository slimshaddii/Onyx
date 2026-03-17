"""
Auto-detection for RimWorld install, Steam, SteamCMD, workshop folders.
Scans registry, common paths, and Steam library configs.
"""

import os
import re
import platform
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

RIMWORLD_APP_ID = '294100'

RIMWORLD_EXE_NAMES = [
    'RimWorldWin64.exe',
    'RimWorldWin.exe',
    'RimWorld.exe',
]

STEAM_COMMON_PATHS_WIN = [
    r'C:\Program Files (x86)\Steam',
    r'C:\Program Files\Steam',
    r'D:\Steam',
    r'D:\SteamLibrary',
    r'E:\Steam',
    r'E:\SteamLibrary',
    r'F:\Steam',
    r'F:\SteamLibrary',
]

STEAMCMD_COMMON_PATHS_WIN = [
    r'C:\steamcmd',
    r'C:\SteamCMD',
    r'D:\steamcmd',
    r'D:\SteamCMD',
    os.path.expanduser(r'~\steamcmd'),
    os.path.expanduser(r'~\Desktop\steamcmd'),
    os.path.expanduser(r'~\Downloads\steamcmd'),
]

NON_STEAM_COMMON_PATHS = [
    r'C:\Games\RimWorld',
    r'D:\Games\RimWorld',
    r'E:\Games\RimWorld',
    r'C:\GOG Games\RimWorld',
    r'D:\GOG Games\RimWorld',
]


@dataclass
class DetectionResult:
    rimworld_exe: str = ''
    rimworld_path: str = ''
    steam_path: str = ''
    steam_workshop_path: str = ''
    steamcmd_path: str = ''
    is_steam_copy: bool = False
    extra_mod_paths: list[str] = field(default_factory=list)
    rimworld_version: str = ''
    detected_dlcs: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)

    @property
    def found_rimworld(self) -> bool:
        return bool(self.rimworld_exe)


def auto_detect_all() -> DetectionResult:
    result = DetectionResult()
    result.logs.append("Starting auto-detection...")

    # 1. Find Steam
    steam_path = _find_steam_install()
    if steam_path:
        result.steam_path = str(steam_path)
        result.logs.append(f"Found Steam: {steam_path}")
    else:
        result.logs.append("Steam not found via registry or common paths")

    # 2. Find Steam library folders
    library_folders = []
    if steam_path:
        library_folders = _find_steam_library_folders(Path(steam_path))
        for lf in library_folders:
            result.logs.append(f"Found Steam library: {lf}")

    # 3. Find RimWorld in Steam libraries
    for lib_path in library_folders:
        rw_path = lib_path / 'steamapps' / 'common' / 'RimWorld'
        if rw_path.exists():
            exe = _find_rimworld_exe(rw_path)
            if exe:
                result.rimworld_exe = str(exe)
                result.rimworld_path = str(rw_path)
                result.is_steam_copy = True
                result.logs.append(f"Found RimWorld (Steam): {exe}")
                break

    # 4. If not found in Steam, check common non-Steam paths
    if not result.rimworld_exe:
        for common_path in NON_STEAM_COMMON_PATHS:
            p = Path(common_path)
            if p.exists():
                exe = _find_rimworld_exe(p)
                if exe:
                    result.rimworld_exe = str(exe)
                    result.rimworld_path = str(p)
                    result.is_steam_copy = False
                    result.logs.append(f"Found RimWorld (non-Steam): {exe}")
                    break
        # Also do a broader search on common game drives
        if not result.rimworld_exe:
            for drive in ['C:', 'D:', 'E:', 'F:']:
                drive_path = Path(drive + '\\')
                if drive_path.exists():
                    found = _search_drive_for_rimworld(drive_path, max_depth=3)
                    if found:
                        result.rimworld_exe = str(found)
                        result.rimworld_path = str(found.parent)
                        result.is_steam_copy = _is_steam_copy(found.parent)
                        result.logs.append(f"Found RimWorld (drive scan): {found}")
                        break

    # 5. Find Workshop content folder
    if steam_path:
        workshop_path = _find_workshop_path(library_folders)
        if workshop_path:
            result.steam_workshop_path = str(workshop_path)
            result.extra_mod_paths.append(str(workshop_path))
            result.logs.append(f"Found Workshop folder: {workshop_path}")

    # 6. Find SteamCMD
    steamcmd = _find_steamcmd()
    if steamcmd:
        result.steamcmd_path = str(steamcmd)
        result.logs.append(f"Found SteamCMD: {steamcmd}")
    else:
        result.logs.append("SteamCMD not found")

    # 7. Add local mods path
    if result.rimworld_path:
        local_mods = Path(result.rimworld_path) / 'Mods'
        if local_mods.exists() and str(local_mods) not in result.extra_mod_paths:
            result.extra_mod_paths.append(str(local_mods))
            result.logs.append(f"Found local Mods folder: {local_mods}")

    # 8. Detect version
    if result.rimworld_path:
        version_file = Path(result.rimworld_path) / 'Version.txt'
        if version_file.exists():
            try:
                result.rimworld_version = version_file.read_text().strip()
                result.logs.append(f"RimWorld version: {result.rimworld_version}")
            except Exception:
                pass

    if not result.rimworld_exe:
        result.logs.append("Could not find RimWorld installation. Please set the path manually.")

    return result


def _find_steam_install() -> Optional[Path]:
    """Find Steam install via Windows registry, then common paths."""
    if platform.system() == 'Windows':
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
                except (WindowsError, FileNotFoundError):
                    continue

            # Also check HKEY_CURRENT_USER
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Valve\Steam')
                steam_path, _ = winreg.QueryValueEx(key, 'SteamPath')
                winreg.CloseKey(key)
                if steam_path and Path(steam_path).exists():
                    return Path(steam_path)
            except (WindowsError, FileNotFoundError):
                pass
        except ImportError:
            pass

    # Fallback: check common paths
    for p in STEAM_COMMON_PATHS_WIN:
        path = Path(p)
        if path.exists() and (path / 'steam.exe').exists():
            return path

    return None


def _find_steam_library_folders(steam_path: Path) -> list[Path]:
    """Parse libraryfolders.vdf to find all Steam library folders."""
    folders = [steam_path]
    vdf_path = steam_path / 'steamapps' / 'libraryfolders.vdf'

    if not vdf_path.exists():
        # Try alternate location
        vdf_path = steam_path / 'config' / 'libraryfolders.vdf'

    if vdf_path.exists():
        try:
            content = vdf_path.read_text(encoding='utf-8', errors='replace')
            # Match "path" entries in the VDF format
            paths = re.findall(r'"path"\s+"([^"]+)"', content)
            for p in paths:
                lib_path = Path(p.replace('\\\\', '\\'))
                if lib_path.exists() and lib_path not in folders:
                    folders.append(lib_path)
        except Exception:
            pass

    return folders


def _find_rimworld_exe(game_path: Path) -> Optional[Path]:
    """Look for RimWorld executable in a folder."""
    for exe_name in RIMWORLD_EXE_NAMES:
        exe_path = game_path / exe_name
        if exe_path.exists():
            return exe_path
    return None


def _is_steam_copy(game_path: Path) -> bool:
    """Check if this is a Steam copy by looking for steam_api.dll."""
    return (game_path / 'steam_api64.dll').exists() or \
           (game_path / 'steam_api.dll').exists() or \
           'steamapps' in str(game_path).lower()


def _find_workshop_path(library_folders: list[Path]) -> Optional[Path]:
    """Find the RimWorld workshop content folder."""
    for lib in library_folders:
        workshop = lib / 'steamapps' / 'workshop' / 'content' / RIMWORLD_APP_ID
        if workshop.exists():
            return workshop
    return None


def _find_steamcmd() -> Optional[Path]:
    """Find SteamCMD executable."""
    for p in STEAMCMD_COMMON_PATHS_WIN:
        path = Path(p)
        exe = path / 'steamcmd.exe'
        if exe.exists():
            return exe
        # Maybe they extracted it without a subfolder
        if path.exists() and path.name.lower() == 'steamcmd.exe':
            return path

    # Check PATH
    import shutil
    which = shutil.which('steamcmd')
    if which:
        return Path(which)

    return None


def _search_drive_for_rimworld(root: Path, max_depth: int = 3) -> Optional[Path]:
    """Limited-depth search for RimWorld on a drive."""
    if max_depth <= 0:
        return None

    try:
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            name_lower = entry.name.lower()

            # Skip system/hidden folders
            if name_lower.startswith('.') or name_lower in (
                'windows', 'programdata', '$recycle.bin',
                'system volume information', 'recovery',
                'perflogs', 'intel', 'nvidia', 'amd',
            ):
                continue

            # Check if this folder contains RimWorld
            if 'rimworld' in name_lower:
                exe = _find_rimworld_exe(entry)
                if exe:
                    return exe

            # Check subfolders
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
    """Quick detection of just the RimWorld exe path."""
    result = auto_detect_all()
    return result.rimworld_exe if result.found_rimworld else None


def detect_steam_workshop_folder() -> Optional[str]:
    """Quick detection of Steam Workshop content folder."""
    steam = _find_steam_install()
    if steam:
        libs = _find_steam_library_folders(steam)
        ws = _find_workshop_path(libs)
        if ws:
            return str(ws)
    return None