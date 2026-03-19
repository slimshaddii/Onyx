"""
Steam native integration — open workshop pages, subscribe via Steam client.
For users with a Steam copy of RimWorld.
"""

import os
import platform
import subprocess
import webbrowser
from enum import Enum
from typing import Optional

if platform.system() == 'Windows':
    try:
        import winreg as _winreg
    except ImportError:
        _winreg = None  # type: ignore[assignment]
else:
    _winreg = None  # type: ignore[assignment]

STEAM_WORKSHOP_URL    = "https://steamcommunity.com/sharedfiles/filedetails/?id={}"
STEAM_WORKSHOP_BROWSE = "https://steamcommunity.com/app/294100/workshop/"

_STEAM_COMMON_PATHS = [
    r'C:\Program Files (x86)\Steam\steam.exe',
    r'C:\Program Files\Steam\steam.exe',
    r'D:\Steam\steam.exe',
]


class DownloadMethod(Enum):
    """Supported mod download methods."""

    STEAMCMD     = "steamcmd"
    STEAM_NATIVE = "steam_native"


def open_in_steam(workshop_id: str) -> bool:
    """Open a workshop item in the Steam client."""
    url = f"steam://url/CommunityFilePage/{workshop_id}"
    try:
        if os.name == 'nt':
            os.startfile(url)  # pylint: disable=no-member
        else:
            webbrowser.open(url)
        return True
    except OSError:
        return False


def subscribe_via_steam(workshop_id: str) -> bool:
    """Attempt to subscribe to a workshop item via Steam protocol."""
    url = (
        "steam://openurl/"
        f"https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}"
    )
    try:
        if os.name == 'nt':
            os.startfile(url)  # pylint: disable=no-member
        else:
            webbrowser.open(url)
        return True
    except OSError:
        return False


def open_workshop_page(workshop_id: str) -> None:
    """Open the Steam Workshop page in the default browser."""
    webbrowser.open(STEAM_WORKSHOP_URL.format(workshop_id))


def open_workshop_browse() -> None:
    """Open the RimWorld Workshop browse page in the default browser."""
    webbrowser.open(STEAM_WORKSHOP_BROWSE)


def is_steam_running() -> bool:
    """Return True if steam.exe is running (Windows only)."""
    if os.name != 'nt':
        return False
    try:
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq steam.exe'],
            capture_output=True, text=True, timeout=5, check=False)
        return 'steam.exe' in result.stdout.lower()
    except (OSError, FileNotFoundError):
        return False


def find_steam_exe() -> Optional[str]:
    """Find the Steam executable on Windows. Returns None on non-Windows or if not found."""
    if os.name != 'nt':
        return None

    for p in _STEAM_COMMON_PATHS:
        if os.path.isfile(p):
            return p

    if _winreg is not None:
        try:
            key = _winreg.OpenKey(
                _winreg.HKEY_LOCAL_MACHINE,
                r'SOFTWARE\WOW6432Node\Valve\Steam')
            path, _ = _winreg.QueryValueEx(key, 'InstallPath')
            _winreg.CloseKey(key)
            exe = os.path.join(path, 'steam.exe')
            if os.path.isfile(exe):
                return exe
        except OSError:
            pass

    return None


def launch_steam_download(workshop_ids: list[str]) -> bool:
    """
    Open each workshop item in the Steam client for the user to subscribe.

    Returns False on the first failure, True if all items were opened.
    """
    for wid in workshop_ids:
        if not open_in_steam(wid):
            return False
    return True
