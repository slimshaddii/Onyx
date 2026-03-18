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
    'theme':                 'dark',
}


class AppSettings:
    _instance: Optional['AppSettings'] = None

    def __init__(self):
        self._data: dict = load_json(settings_path(), {})
        for k, v in _DEFAULTS.items():
            self._data.setdefault(k, v)

    @classmethod
    def instance(cls) -> 'AppSettings':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reload(cls):
        cls._instance = cls()

    def save(self):
        save_json(settings_path(), self._data)

    def update(self, d: dict):
        self._data.update(d)
        self.save()

    def as_dict(self) -> dict:
        return dict(self._data)

    @property
    def rimworld_exe(self) -> str:
        return self._data.get('rimworld_exe', '')

    @rimworld_exe.setter
    def rimworld_exe(self, v: str):
        self._data['rimworld_exe'] = v

    @property
    def data_root(self) -> str:
        return self._data.get('data_root', '')

    @data_root.setter
    def data_root(self, v: str):
        self._data['data_root'] = v

    @property
    def steamcmd_path(self) -> str:
        return self._data.get('steamcmd_path', '')

    @steamcmd_path.setter
    def steamcmd_path(self, v: str):
        self._data['steamcmd_path'] = v

    @property
    def steamcmd_username(self) -> str:
        return self._data.get('steamcmd_username', '')

    @steamcmd_username.setter
    def steamcmd_username(self, v: str):
        self._data['steamcmd_username'] = v

    @property
    def steam_workshop_path(self) -> str:
        return self._data.get('steam_workshop_path', '')

    @steam_workshop_path.setter
    def steam_workshop_path(self, v: str):
        self._data['steam_workshop_path'] = v

    @property
    def steam_api_key(self) -> str:
        return self._data.get('steam_api_key', '')

    @steam_api_key.setter
    def steam_api_key(self, v: str):
        self._data['steam_api_key'] = v

    @property
    def extra_mod_paths(self) -> list[str]:
        return list(self._data.get('extra_mod_paths', []))

    @extra_mod_paths.setter
    def extra_mod_paths(self, v: list[str]):
        self._data['extra_mod_paths'] = list(v)

    @property
    def download_method(self) -> str:
        return self._data.get('download_method', 'steamcmd')

    @download_method.setter
    def download_method(self, v: str):
        self._data['download_method'] = v

    @property
    def is_steam_copy(self) -> bool:
        return bool(self._data.get('is_steam_copy', False))

    @is_steam_copy.setter
    def is_steam_copy(self, v: bool):
        self._data['is_steam_copy'] = v

    @property
    def auto_backup_on_launch(self) -> bool:
        return bool(self._data.get('auto_backup_on_launch', True))

    @auto_backup_on_launch.setter
    def auto_backup_on_launch(self, v: bool):
        self._data['auto_backup_on_launch'] = v

    @property
    def backup_count(self) -> int:
        return int(self._data.get('backup_count', 3))

    @backup_count.setter
    def backup_count(self, v: int):
        self._data['backup_count'] = v

    @property
    def offered_import(self) -> bool:
        return bool(self._data.get('offered_import', False))

    @offered_import.setter
    def offered_import(self, v: bool):
        self._data['offered_import'] = v

    @property
    def window(self) -> dict:
        return dict(self._data.get('window',
                    {'width': 1200, 'height': 720, 'x': 80, 'y': 60}))

    @window.setter
    def window(self, v: dict):
        self._data['window'] = v

    @property
    def theme(self) -> str:
        return self._data.get('theme', 'dark')

    @theme.setter
    def theme(self, v: str):
        self._data['theme'] = v

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value