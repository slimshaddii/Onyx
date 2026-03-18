"""
Saves GroupBox — lists .rws save files with compatibility badges.

Each save is checked against the instance's active mod list.
Parsing is done on a daemon thread per save to avoid blocking the UI.
"""

import threading
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
)
from PyQt6.QtCore import QTimer, QObject, pyqtSignal, Qt

from app.core.instance import Instance
from app.core.save_parser import (
    parse_save_header, compare_save_mods, SaveCompat,
)
from app.ui.detail.save_compat import (
    COMPAT_ICON, COMPAT_LABEL, compat_style,
)
from app.utils.file_utils import human_size


class _CompatWorker(QObject):
    """
    Lives on the main thread. Receives results from background threads
    via a queued signal connection — the safest way to marshal data
    from a daemon thread back to Qt widgets.
    """
    result_ready = pyqtSignal(str, str, str, str)
    # args: save_name, icon, style, tooltip


class DetailSaves(QWidget):
    _MAX_SHOWN = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)

        saves_group    = QGroupBox("Saves")
        self._saves_lo = QVBoxLayout()
        saves_group.setLayout(self._saves_lo)
        lo.addWidget(saves_group)

        self._compat_labels: dict[str, QLabel] = {}

        # Worker lives on the main thread — signal connection is auto-queued
        # across threads so the slot always runs on the main thread.
        self._worker = _CompatWorker()
        self._worker.result_ready.connect(self._apply_compat)

    # ── Public API ────────────────────────────────────────────────────────

    def set_instance(self, inst: Instance):
        self._clear()
        self._compat_labels.clear()

        saves = inst.get_save_files()
        if not saves:
            self._saves_lo.addWidget(QLabel("No saves yet"))
            return

        active_ids = list(inst.mods)

        for s in saves[:self._MAX_SHOWN]:
            row       = QHBoxLayout()
            save_path = Path(s['path'])

            compat_lbl = QLabel("…")
            compat_lbl.setStyleSheet(
                "color:#888; background:transparent; padding:1px 4px;")
            compat_lbl.setToolTip("Checking compatibility…")
            row.addWidget(compat_lbl)
            self._compat_labels[s['name']] = compat_lbl

            row.addWidget(QLabel(f"📄 {s['name']}"))
            row.addStretch()
            row.addWidget(QLabel(human_size(s['size'])))

            container = QWidget()
            container.setLayout(row)
            self._saves_lo.addWidget(container)

            self._check_compat_async(save_path, active_ids, s['name'])

        if len(saves) > self._MAX_SHOWN:
            self._saves_lo.addWidget(
                QLabel(f"… +{len(saves) - self._MAX_SHOWN} more"))

    def clear(self):
        self._clear()
        self._compat_labels.clear()
        self._saves_lo.addWidget(QLabel("No saves yet"))

    # ── Internals ─────────────────────────────────────────────────────────

    def _clear(self):
        while self._saves_lo.count():
            child = self._saves_lo.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _check_compat_async(self, save_path: Path,
                             active_ids: list[str],
                             save_name: str):
        """
        Parse save header on a daemon thread.
        Emits result_ready signal (queued connection) so the slot
        always runs on the main thread — no QTimer hack needed.
        """
        worker = self._worker   # capture reference for thread closure

        def _run():
            header = parse_save_header(save_path)
            if header is None:
                compat = SaveCompat.UNKNOWN
            else:
                # Use the save's own mod_ids as proxy for "installed"
                # so CHANGED shows correctly. Full MISSING detection
                # (with real installed set) happens in launch_dialog.
                all_ids = set(m.lower() for m in active_ids)
                compat  = compare_save_mods(header, active_ids, all_ids)

            icon  = COMPAT_ICON[compat]
            style = compat_style(compat)
            tip   = COMPAT_LABEL[compat]

            # Signal emission from background thread is safe when the
            # connection type is Qt.ConnectionType.QueuedConnection,
            # which is the default for cross-thread signal connections.
            worker.result_ready.emit(save_name, icon, style, tip)

        threading.Thread(target=_run, daemon=True).start()

    def _apply_compat(self, save_name: str, icon: str,
                      style: str, tip: str):
        """Slot — always runs on main thread via queued connection."""
        lbl = self._compat_labels.get(save_name)
        if lbl:
            lbl.setText(icon)
            lbl.setStyleSheet(style)
            lbl.setToolTip(tip)