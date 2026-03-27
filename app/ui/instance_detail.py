"""
Instance detail panel — right-side panel showing info for the selected instance.

Delegates all rendering to focused sub-widgets in app/ui/detail/:
    DetailHeader   — name + path
    DetailActions  — button row
    DetailInfo     — stats grid + missing-mods warning
    DetailSaves    — save file list
    DetailNotes    — notes editor with autosave
"""

import os
import subprocess
from datetime import datetime

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea  # pylint: disable=no-name-in-module
from PyQt6.QtCore import pyqtSignal, Qt  # pylint: disable=no-name-in-module

from app.core.instance import Instance
from app.core.launcher import Launcher
from app.core.rimworld import RimWorldDetector
from app.ui.detail import (
    DetailHeader, DetailActions, DetailInfo, DetailSaves, DetailNotes,
)


class InstanceDetailPanel(QWidget):
    """Right-side panel showing details for the selected instance."""

    launch_requested      = pyqtSignal(object)
    edit_mods_requested   = pyqtSignal(object)
    duplicate_requested   = pyqtSignal(object)
    delete_requested      = pyqtSignal(object)
    export_pack_requested = pyqtSignal(object)
    instance_updated      = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_instance: Instance | None = None
        self.header:  DetailHeader | None  = None
        self.actions: DetailActions | None = None
        self.info:    DetailInfo | None    = None
        self.saves:   DetailSaves | None   = None
        self.notes:   DetailNotes | None   = None
        self._build_ui()

    def _build_ui(self):
        """Build the detail panel layout and sub-widgets."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        lo = QVBoxLayout(content)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(10)

        self.header  = DetailHeader(self)
        self.actions = DetailActions(self)
        self.info    = DetailInfo(self)
        self.saves   = DetailSaves(self)
        self.notes   = DetailNotes(self)

        lo.addWidget(self.header)
        lo.addWidget(self.actions)
        lo.addWidget(self.info)
        lo.addWidget(self.saves)
        lo.addWidget(self.notes)
        lo.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

        self.actions.launch_clicked.connect(self._emit_launch)
        self.actions.edit_mods_clicked.connect(
            self._emit_edit_mods)
        self.actions.duplicate_clicked.connect(self._emit_dup)
        self.actions.folder_clicked.connect(self._open_folder)
        self.actions.export_pack_clicked.connect(
            self._emit_export_pack)
        self.actions.delete_clicked.connect(self._emit_del)

    def set_instance(self, inst: Instance,
                     rw: RimWorldDetector | None = None):
        """Populate the panel with data for the given instance."""
        self.current_instance = inst
        self.header.set_instance(inst.name, str(inst.path))
        self.actions.set_enabled(True)
        self.info.set_instance(inst, rw)
        self.saves.set_instance(inst, rw)
        self.notes.set_instance(inst)
        self._check_untracked_playtime(inst)

    def _check_untracked_playtime(self, inst: Instance):
        """Detect and record playtime from sessions outside the
        launcher."""
        log_path = inst.path / 'Player.log'
        if not log_path.exists():
            return
        try:
            log_mtime = os.path.getmtime(log_path)
            log_dt    = datetime.fromtimestamp(log_mtime)

            if inst.last_played:
                last = datetime.fromisoformat(inst.last_played)
            else:
                return

            diff_minutes = (log_dt - last).total_seconds() / 60
            if diff_minutes > 2:
                mins = Launcher.get_session_minutes_from_log(
                    inst.path)
                if mins > 0:
                    inst.total_playtime_minutes += mins
                    inst.last_played = log_dt.isoformat()
                    inst.save()
        except Exception:  # pylint: disable=broad-exception-caught
            # Playtime detection must not crash the detail panel.
            pass

    def clear(self):
        """Clear the panel and disable actions."""
        self.current_instance = None
        self.header.clear()
        self.actions.set_enabled(False)
        self.info.clear()
        self.saves.clear()
        self.notes.clear()

    def _emit_launch(self):
        """Forward launch request for the current instance."""
        if self.current_instance:
            self.launch_requested.emit(self.current_instance)

    def _emit_edit_mods(self):
        """Forward edit-mods request for the current instance."""
        if self.current_instance:
            self.edit_mods_requested.emit(self.current_instance)

    def _emit_dup(self):
        """Forward duplicate request for the current instance."""
        if self.current_instance:
            self.duplicate_requested.emit(self.current_instance)

    def _emit_del(self):
        """Forward delete request for the current instance."""
        if self.current_instance:
            self.delete_requested.emit(self.current_instance)

    def _emit_export_pack(self):
        """Forward export-pack request for the current instance."""
        if self.current_instance:
            self.export_pack_requested.emit(self.current_instance)

    def _open_folder(self):
        """Open the instance folder in the system file manager."""
        if not self.current_instance:
            return
        p = str(self.current_instance.path)
        if os.name == 'nt':
            subprocess.Popen(['explorer', p])
        else:
            subprocess.Popen(['xdg-open', p])
