"""
Mod update checker dialog.
Shows which installed mods have updates available on Steam Workshop.
"""

import threading
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QProgressBar, QComboBox,
    QGroupBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QColor

from app.core.app_settings import AppSettings
from app.ui.styles import get_colors


class _CheckWorker(QObject):
    finished  = pyqtSignal(list)   # list[ModUpdateInfo]
    progress  = pyqtSignal(str)    # status message
    error     = pyqtSignal(str)


class ModUpdateDialog(QDialog):
    def __init__(self, parent, rw, data_root: Path,
                 download_manager=None):
        super().__init__(parent)
        self.rw               = rw
        self.data_root        = data_root
        self.download_manager = download_manager
        self._results         = []
        self._worker          = _CheckWorker(self)
        self._worker.finished.connect(self._on_results)
        self._worker.progress.connect(self._on_progress)
        self._worker.error.connect(self._on_error)

        self.setWindowTitle("Check for Mod Updates")
        self.setMinimumSize(600, 480)
        self._build()

    def _build(self):
        c  = get_colors(AppSettings.instance().theme)
        lo = QVBoxLayout(self)
        lo.setSpacing(8)

        # ── Settings row ──────────────────────────────────────────────────
        settings_row = QHBoxLayout()
        settings_row.addWidget(QLabel("Auto-check:"))
        self._mode_cb = QComboBox()
        self._mode_cb.addItem("On startup (background)", "auto")
        self._mode_cb.addItem("Manual only",             "manual")
        self._mode_cb.addItem("Disabled",                "disabled")
        current = AppSettings.instance().update_check_mode
        idx = self._mode_cb.findData(current)
        self._mode_cb.setCurrentIndex(max(0, idx))
        self._mode_cb.currentIndexChanged.connect(self._save_mode)
        settings_row.addWidget(self._mode_cb)
        settings_row.addStretch()
        lo.addLayout(settings_row)

        # ── Status ────────────────────────────────────────────────────────
        self._status_lbl = QLabel("Click 'Check Now' to scan for updates.")
        self._status_lbl.setObjectName("subheading")
        lo.addWidget(self._status_lbl)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)   # indeterminate
        self._progress_bar.hide()
        lo.addWidget(self._progress_bar)

        # ── Results list ──────────────────────────────────────────────────
        results_group = QGroupBox("Results")
        rg_lo = QVBoxLayout()

        self._summary_lbl = QLabel("")
        rg_lo.addWidget(self._summary_lbl)

        self._list = QListWidget()
        rg_lo.addWidget(self._list, 1)
        results_group.setLayout(rg_lo)
        lo.addWidget(results_group, 1)

        # ── Buttons ───────────────────────────────────────────────────────
        btns = QHBoxLayout()

        self._check_btn = QPushButton("Check Now")
        self._check_btn.setObjectName("primaryButton")
        self._check_btn.clicked.connect(self._start_check)
        btns.addWidget(self._check_btn)

        self._update_btn = QPushButton("Download All Updates")
        self._update_btn.setEnabled(False)
        self._update_btn.clicked.connect(self._download_updates)
        btns.addWidget(self._update_btn)

        btns.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)

        lo.addLayout(btns)

    def _save_mode(self):
        mode = self._mode_cb.currentData()
        AppSettings.instance().update_check_mode = mode
        AppSettings.instance().save()

    def _start_check(self):
        self._check_btn.setEnabled(False)
        self._update_btn.setEnabled(False)
        self._list.clear()
        self._progress_bar.show()
        self._status_lbl.setText("Fetching installed mod list…")

        worker  = self._worker
        rw      = self.rw
        dr      = self.data_root

        def _run():
            try:
                from app.core.app_settings import AppSettings
                from app.core.paths import mods_dir
                from app.core.mod_update_checker import (
                    ModTimestampStore, check_updates)

                _s     = AppSettings.instance()
                paths  = []
                if _s.data_root:
                    paths.append(str(mods_dir(Path(_s.data_root))))
                if _s.steam_workshop_path:
                    paths.append(_s.steam_workshop_path)

                installed  = rw.get_installed_mods(
                    extra_mod_paths=paths)
                store      = ModTimestampStore(dr)

                # Collect workshop mods only
                ws_ids:   list[str]       = []
                names:    dict[str, str]  = {}
                mod_paths: dict[str, str] = {}

                for pid, info in installed.items():
                    if info.workshop_id:
                        ws_ids.append(info.workshop_id)
                        names[info.workshop_id]     = info.name
                        mod_paths[info.workshop_id] = str(info.path)

                worker.progress.emit(
                    f"Checking {len(ws_ids)} Workshop mods…")

                results = check_updates(ws_ids, store, names, mod_paths)
                worker.finished.emit(results)

            except Exception as e:
                worker.error.emit(str(e))

        threading.Thread(target=_run, daemon=True).start()

    def _on_progress(self, msg: str):
        self._status_lbl.setText(msg)

    def _on_error(self, msg: str):
        self._progress_bar.hide()
        self._check_btn.setEnabled(True)
        self._status_lbl.setText(f"Error: {msg}")

    def _on_results(self, results: list):
        from app.core.mod_update_checker import ModUpdateInfo
        self._results   = results
        self._progress_bar.hide()
        self._check_btn.setEnabled(True)
        self._list.clear()

        c          = get_colors(AppSettings.instance().theme)
        updates    = [r for r in results if r.has_update]
        up_to_date = [r for r in results if not r.has_update]

        self._summary_lbl.setText(
            f"{len(updates)} update(s) available  |  "
            f"{len(up_to_date)} up to date  |  "
            f"{len(results)} total checked")

        # Updates first
        for r in sorted(updates, key=lambda x: x.name.lower()):
            from datetime import datetime
            try:
                remote_str = datetime.fromtimestamp(
                    r.remote_time).strftime("%b %d, %Y")
            except Exception:
                remote_str = "Unknown"
            try:
                local_str = datetime.fromtimestamp(
                    r.local_time).strftime("%b %d, %Y") if r.local_time else "Unknown"
            except Exception:
                local_str = "Unknown"

            it = QListWidgetItem(
                f"🔄  {r.name}  —  "
                f"local: {local_str}  →  workshop: {remote_str}")
            it.setData(Qt.ItemDataRole.UserRole, r)
            it.setForeground(QColor(c['warning']))
            self._list.addItem(it)

        # Up to date
        for r in sorted(up_to_date, key=lambda x: x.name.lower()):
            it = QListWidgetItem(f"✅  {r.name}")
            it.setData(Qt.ItemDataRole.UserRole, r)
            it.setForeground(QColor(c['success']))
            self._list.addItem(it)

        self._status_lbl.setText(
            f"Done — {len(updates)} update(s) available")
        self._update_btn.setEnabled(bool(updates))

    def _download_updates(self):
        updates = [r for r in self._results if r.has_update]
        if not updates or not self.download_manager:
            return
        pairs = [(r.workshop_id, r.name) for r in updates]
        self.download_manager.queue_and_show(pairs)
        self.accept()