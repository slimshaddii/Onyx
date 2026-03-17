"""
Steam native integration — open workshop pages, subscribe via Steam client.
For users with a Steam copy of RimWorld.
"""

import subprocess
import webbrowser
import os
from pathlib import Path
from typing import Optional
from enum import Enum


class DownloadMethod(Enum):
    STEAMCMD = "steamcmd"
    STEAM_NATIVE = "steam_native"


STEAM_WORKSHOP_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={}"
STEAM_WORKSHOP_BROWSE = "https://steamcommunity.com/app/294100/workshop/"


def open_in_steam(workshop_id: str) -> bool:
    """Open a workshop item in the Steam client."""
    try:
        url = f"steam://url/CommunityFilePage/{workshop_id}"
        if os.name == 'nt':
            os.startfile(url)
        else:
            webbrowser.open(url)
        return True
    except Exception:
        return False


def subscribe_via_steam(workshop_id: str) -> bool:
    """Attempt to subscribe to a workshop item via Steam protocol."""
    try:
        url = f"steam://openurl/https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}"
        if os.name == 'nt':
            os.startfile(url)
        else:
            webbrowser.open(url)
        return True
    except Exception:
        return False


def open_workshop_page(workshop_id: str):
    """Open the Steam Workshop page in default browser."""
    url = STEAM_WORKSHOP_URL.format(workshop_id)
    webbrowser.open(url)


def open_workshop_browse():
    """Open the RimWorld Workshop browse page."""
    webbrowser.open(STEAM_WORKSHOP_BROWSE)


def is_steam_running() -> bool:
    """Check if Steam is running (Windows)."""
    if os.name == 'nt':
        try:
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq steam.exe'],
                capture_output=True, text=True, timeout=5
            )
            return 'steam.exe' in result.stdout.lower()
        except Exception:
            return False
    return False


def find_steam_exe() -> Optional[str]:
    """Find Steam executable."""
    if os.name == 'nt':
        common = [
            r'C:\Program Files (x86)\Steam\steam.exe',
            r'C:\Program Files\Steam\steam.exe',
            r'D:\Steam\steam.exe',
        ]
        for p in common:
            if os.path.isfile(p):
                return p

        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r'SOFTWARE\WOW6432Node\Valve\Steam')
            path, _ = winreg.QueryValueEx(key, 'InstallPath')
            winreg.CloseKey(key)
            exe = os.path.join(path, 'steam.exe')
            if os.path.isfile(exe):
                return exe
        except Exception:
            pass
    return None


def launch_steam_download(workshop_ids: list[str]) -> bool:
    """
    Launch Steam and tell it to download workshop items.
    This opens each item's page in Steam for the user to subscribe.
    """
    for wid in workshop_ids:
        if not open_in_steam(wid):
            return False
    return True