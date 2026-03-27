"""
Saves GroupBox — lists .rws save files with
compatibility badges.
"""

import threading
from pathlib import Path

from PyQt6.QtCore import (  # pylint: disable=no-name-in-module
    QObject, pyqtSignal,
)
from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QGroupBox,
)

from app.core.app_settings import AppSettings
from app.core.instance import Instance
from app.core.rimworld import RimWorldDetector
from app.core.save_parser import (
    parse_save_header, compare_save_mods,
    diff_save_mods, SaveCompat,
)
from app.ui.detail.save_compat import (
    COMPAT_ICON, COMPAT_LABEL, compat_style,
)
from app.ui.styles import get_colors
from app.utils.file_utils import human_size


class _CompatWorker(QObject):
    """Marshal compat results from background
    threads to the main thread."""

    result_ready = pyqtSignal(
        str, str, str, str)


# ── DetailSaves ──────────────────────────────────

class DetailSaves(QWidget):
    """Displays save files for the selected instance
    with async compatibility badges.

    Each save row shows an icon (compatibility
    status), filename, and size.  The compatibility
    check is performed on a daemon thread and the
    badge is updated via a signal once complete.
    """

    _MAX_SHOWN = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)

        saves_group = QGroupBox("Saves")
        self._saves_lo = QVBoxLayout()
        saves_group.setLayout(self._saves_lo)
        lo.addWidget(saves_group)

        self._compat_labels: (
            dict[str, QLabel]) = {}
        self._worker = _CompatWorker(self)
        self._worker.result_ready.connect(
            self._apply_compat)

    def set_instance(
            self, inst: Instance,
            rw: RimWorldDetector | None = None,
    ) -> None:
        """Populate the saves list for inst,
        launching async compat checks per save."""
        self._clear()
        self._compat_labels.clear()

        saves = inst.get_save_files()
        if not saves:
            self._saves_lo.addWidget(
                QLabel("No saves yet"))
            return

        active_ids = list(inst.mods)

        if rw is not None:
            all_mod_ids: set[str] = set(
                rw.get_installed_mods().keys())
        else:
            all_mod_ids = {
                m.lower() for m in active_ids}

        for s in saves[:self._MAX_SHOWN]:
            self._build_save_row(
                s, active_ids, all_mod_ids)

        if len(saves) > self._MAX_SHOWN:
            self._saves_lo.addWidget(
                QLabel(
                    f"… +{len(saves)
                           - self._MAX_SHOWN}"
                    f" more"))

    def clear(self) -> None:
        """Clear the saves list and show the
        placeholder."""
        self._clear()
        self._compat_labels.clear()
        self._saves_lo.addWidget(
            QLabel("No saves yet"))

    def _build_save_row(
            self, s: dict,
            active_ids: list[str],
            all_mod_ids: set[str]) -> None:
        """Build one save row, register its compat
        label, and start the async check."""
        row = QHBoxLayout()
        row.setSpacing(6)
        save_path = Path(s['path'])

        c = get_colors(
            AppSettings.instance().theme)
        compat_lbl = QLabel("…")
        compat_lbl.setStyleSheet(
            f"color:{c['text_dim']}; "
            f"background:transparent;"
            f" padding:1px 4px;")
        compat_lbl.setToolTip(
            "Checking compatibility…")
        row.addWidget(compat_lbl)
        self._compat_labels[s['name']] = (
            compat_lbl)

        name_lbl = QLabel(f"📄 {s['name']}")
        name_lbl.setWordWrap(True)
        row.addWidget(name_lbl, 1)

        size_lbl = QLabel(
            human_size(s['size']))
        size_lbl.setStyleSheet(
            f"color:{c['text_dim']};"
            f" font-size:10px;")
        row.addWidget(size_lbl)

        container = QWidget()
        container.setLayout(row)
        self._saves_lo.addWidget(container)

        self._check_compat_async(
            save_path, active_ids,
            all_mod_ids, s['name'])

    def _clear(self) -> None:
        while self._saves_lo.count():
            child = self._saves_lo.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _check_compat_async(
            self, save_path: Path,
            active_ids: list[str],
            all_mod_ids: set[str],
            save_name: str) -> None:
        worker = self._worker

        def _run():
            header = parse_save_header(
                save_path)
            if header is not None:
                compat = compare_save_mods(
                    header, active_ids,
                    all_mod_ids)
                diff = diff_save_mods(
                    header, active_ids)
                added = len(diff['added'])
                tip = COMPAT_LABEL[compat]
                if added:
                    tip += (
                        f" • {added} added")
            else:
                compat = SaveCompat.UNKNOWN
                tip = COMPAT_LABEL[compat]
            worker.result_ready.emit(
                save_name,
                COMPAT_ICON[compat],
                compat_style(compat), tip)

        threading.Thread(
            target=_run, daemon=True).start()

    def _apply_compat(
            self, save_name: str, icon: str,
            style: str, tip: str) -> None:
        """Apply compat result to the label."""
        lbl = self._compat_labels.get(save_name)
        if lbl:
            lbl.setText(icon)
            lbl.setStyleSheet(style)
            lbl.setToolTip(tip)
