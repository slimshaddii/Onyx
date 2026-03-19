"""
Centralized application settings — single source of truth.

Usage
-----
    from app.core.app_settings import AppSettings
    s = AppSettings.instance()
    exe = s.rimworld_exe
    s.rimworld_exe = '/new/path'
    s.save()
"""

from __future__ import annotations
from typing import Optional
from app.core.paths import settings_path
from app.utils.file_utils import load_json, save_json

_DEFAULTS: dict = {
    'rimworld_exe':          '',
    'data_root':             '',
    'steam_api_key':         '',
    'steamcmd_path':         '',
    'steamcmd_username':     '',
    'steam_workshop_path':   '',
    'extra_mod_paths':       [],
    'download_method':       'steamcmd',
    'is_steam_copy':         False,
    'window':                {'width': 1200, 'height': 720, 'x': 80, 'y': 60},
    'auto_backup_on_launch': True,
    'backup_count':          3,
    'offered_import':        False,
    'update_check_mode':     'manual',
    'theme':                 'dark',
}


class AppSettings:
    """
    Singleton application settings backed by app_settings.json.

    Access via AppSettings.instance(). All properties read from and write
    to an in-memory dict; call save() to persist changes to disk.
    """

    _instance: Optional['AppSettings'] = None

    def __init__(self):
        self._data: dict = load_json(settings_path(), {})
        for k, v in _DEFAULTS.items():
            self._data.setdefault(k, v)

    @classmethod
    def instance(cls) -> 'AppSettings':
        """Return the shared AppSettings instance, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reload(cls) -> None:
        """Discard the cached instance and reload from disk on next access."""
        cls._instance = cls()

    def save(self) -> None:
        """Persist current settings to disk."""
        save_json(settings_path(), self._data)

    def update(self, d: dict) -> None:
        """Merge d into settings and save."""
        self._data.update(d)
        self.save()

    def as_dict(self) -> dict:
        """Return a shallow copy of all settings."""
        return dict(self._data)

    def get(self, key: str, default=None):
        """Return the value for key, or default if absent."""
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        """Set an arbitrary key without saving."""
        self._data[key] = value

    @property
    def rimworld_exe(self) -> str:
        """Path to the RimWorld executable."""
        return self._data.get('rimworld_exe', '')

    @rimworld_exe.setter
    def rimworld_exe(self, v: str) -> None:
        self._data['rimworld_exe'] = v

    @property
    def data_root(self) -> str:
        """Root directory for Onyx data (instances, mods, cache)."""
        return self._data.get('data_root', '')

    @data_root.setter
    def data_root(self, v: str) -> None:
        self._data['data_root'] = v

    @property
    def steamcmd_path(self) -> str:
        """Path to the SteamCMD executable."""
        return self._data.get('steamcmd_path', '')

    @steamcmd_path.setter
    def steamcmd_path(self, v: str) -> None:
        self._data['steamcmd_path'] = v

    @property
    def steamcmd_username(self) -> str:
        """SteamCMD login username."""
        return self._data.get('steamcmd_username', '')

    @steamcmd_username.setter
    def steamcmd_username(self, v: str) -> None:
        self._data['steamcmd_username'] = v

    @property
    def steam_workshop_path(self) -> str:
        """Path to the Steam Workshop content directory for RimWorld."""
        return self._data.get('steam_workshop_path', '')

    @steam_workshop_path.setter
    def steam_workshop_path(self, v: str) -> None:
        self._data['steam_workshop_path'] = v

    @property
    def steam_api_key(self) -> str:
        """Steam Web API key for Workshop queries."""
        return self._data.get('steam_api_key', '')

    @steam_api_key.setter
    def steam_api_key(self, v: str) -> None:
        self._data['steam_api_key'] = v

    @property
    def extra_mod_paths(self) -> list[str]:
        """Additional mod search directories beyond the default locations."""
        return list(self._data.get('extra_mod_paths', []))

    @extra_mod_paths.setter
    def extra_mod_paths(self, v: list[str]) -> None:
        self._data['extra_mod_paths'] = list(v)

    @property
    def download_method(self) -> str:
        """Preferred mod download method ('steamcmd' or other)."""
        return self._data.get('download_method', 'steamcmd')

    @download_method.setter
    def download_method(self, v: str) -> None:
        self._data['download_method'] = v

    @property
    def is_steam_copy(self) -> bool:
        """True if the detected RimWorld installation is a Steam copy."""
        return bool(self._data.get('is_steam_copy', False))

    @is_steam_copy.setter
    def is_steam_copy(self, v: bool) -> None:
        self._data['is_steam_copy'] = v

    @property
    def auto_backup_on_launch(self) -> bool:
        """True if saves should be backed up automatically before each launch."""
        return bool(self._data.get('auto_backup_on_launch', True))

    @auto_backup_on_launch.setter
    def auto_backup_on_launch(self, v: bool) -> None:
        self._data['auto_backup_on_launch'] = v

    @property
    def backup_count(self) -> int:
        """Maximum number of save backups to retain per instance."""
        return int(self._data.get('backup_count', 3))

    @backup_count.setter
    def backup_count(self, v: int) -> None:
        self._data['backup_count'] = v

    @property
    def offered_import(self) -> bool:
        """True if the first-run import offer has already been shown."""
        return bool(self._data.get('offered_import', False))

    @offered_import.setter
    def offered_import(self, v: bool) -> None:
        self._data['offered_import'] = v

    @property
    def update_check_mode(self) -> str:
        """Mod update check mode: 'auto', 'manual', or 'disabled'."""
        return self._data.get('update_check_mode', 'manual')

    @update_check_mode.setter
    def update_check_mode(self, v: str) -> None:
        self._data['update_check_mode'] = v

    @property
    def window(self) -> dict:
        """Window geometry dict with keys: width, height, x, y."""
        return dict(self._data.get('window',
                    {'width': 1200, 'height': 720, 'x': 80, 'y': 60}))

    @window.setter
    def window(self, v: dict) -> None:
        self._data['window'] = v

    @property
    def theme(self) -> str:
        """UI theme name: 'dark' or 'light'."""
        return self._data.get('theme', 'dark')

    @theme.setter
    def theme(self, v: str) -> None:
        self._data['theme'] = v
