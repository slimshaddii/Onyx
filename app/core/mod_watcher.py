"""
File system watcher for mod directories.

Watches all configured mod paths and emits mods_changed when
any directory is added or removed. The main window connects
to mods_changed to trigger a debounced rescan.

Usage
-----
    watcher = ModWatcher(rw)
    watcher.mods_changed.connect(main_window._on_mods_changed_on_disk)
    watcher.update_paths(settings.extra_mod_paths,
                         settings.steam_workshop_path,
                         settings.rimworld_exe)
"""

from pathlib import Path
from PyQt6.QtCore import (  # pylint: disable=no-name-in-module
    QObject, pyqtSignal, QTimer, QFileSystemWatcher,
)


class ModWatcher(QObject):
    """
    Wraps QFileSystemWatcher with debouncing and path management.

    mods_changed is emitted at most once per 2 seconds regardless
    of how many filesystem events fire (handles rapid Steam downloads).
    """

    mods_changed = pyqtSignal()

    _DEBOUNCE_MS = 2000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_dir_changed)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(self._DEBOUNCE_MS)
        self._debounce.timeout.connect(self.mods_changed.emit)

        self._watched_paths: set[str] = set()

    def update_paths(self, extra_mod_paths: list[str] = None,
                     steam_workshop_path: str = '',
                     rimworld_exe: str = '') -> None:
        """
        Rebuild the watched path list from current settings.
        Call this whenever settings change.
        """
        new_paths: set[str] = set()

        if rimworld_exe:
            game_mods = Path(rimworld_exe).parent / 'Mods'
            if game_mods.exists():
                new_paths.add(str(game_mods))

        if steam_workshop_path and Path(steam_workshop_path).exists():
            new_paths.add(steam_workshop_path)

        for p in (extra_mod_paths or []):
            if Path(p).exists():
                new_paths.add(p)

        to_remove = self._watched_paths - new_paths
        if to_remove:
            self._watcher.removePaths(list(to_remove))

        to_add = new_paths - self._watched_paths
        if to_add:
            self._watcher.addPaths(list(to_add))

        self._watched_paths = new_paths

    def stop(self) -> None:
        """Stop all watching — call before app exit."""
        if self._watched_paths:
            self._watcher.removePaths(list(self._watched_paths))
        self._debounce.stop()

    def _on_dir_changed(self, _path: str) -> None:
        self._debounce.start()
        