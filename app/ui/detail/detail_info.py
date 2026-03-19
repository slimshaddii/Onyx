"""
Details GroupBox — Version, Active Mods, Inactive Mods,
Save Files, Instance Size, Created, Last Played, Playtime.

Also owns the missing-mods warning label since it relates
to mod/instance health info.
"""

import threading
from datetime import datetime

from PyQt6.QtCore import QTimer  # pylint: disable=no-name-in-module
from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QWidget, QVBoxLayout, QLabel, QGroupBox, QGridLayout,
)

from app.core.app_settings import AppSettings
from app.core.instance import Instance
from app.core.rimworld import RimWorldDetector
from app.ui.styles import get_colors
from app.utils.file_utils import human_size, get_folder_size

_ROWS = (
    'Version', 'Active Mods', 'Inactive Mods', 'Save Files',
    'Instance Size', 'Created', 'Last Played', 'Playtime',
)


class DetailInfo(QWidget):
    """
    Displays a Details grid with instance metadata and a missing-mods warning.

    The Instance Size field is populated asynchronously to avoid blocking the UI.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(4)

        det_group = QGroupBox("Details")
        grid      = QGridLayout()
        grid.setVerticalSpacing(6)

        self._labels: dict[str, QLabel] = {}
        c = get_colors(AppSettings.instance().theme)
        for row, key in enumerate(_ROWS):
            lbl = QLabel(f"{key}:")
            lbl.setStyleSheet(f"font-weight:bold; color:{c['text_dim']};")
            val = QLabel("—")
            grid.addWidget(lbl, row, 0)
            grid.addWidget(val, row, 1)
            self._labels[key] = val

        det_group.setLayout(grid)
        lo.addWidget(det_group)

        self.missing_label = QLabel("")
        self.missing_label.setStyleSheet("color:#c62828; font-weight:bold;")
        self.missing_label.setWordWrap(True)
        self.missing_label.hide()
        lo.addWidget(self.missing_label)

    def set_instance(self, inst: Instance, rw: RimWorldDetector | None) -> None:
        """Populate all fields from inst, triggering an async size calculation."""
        d = self._labels
        d['Version'].setText(inst.rimworld_version or '—')
        d['Active Mods'].setText(str(inst.mod_count))
        d['Inactive Mods'].setText(str(len(inst.inactive_mods)))
        d['Save Files'].setText(str(inst.save_count))
        d['Created'].setText(_fmt_date(inst.created))
        d['Last Played'].setText(_fmt_date(inst.last_played) or 'Never')
        h, m = divmod(inst.total_playtime_minutes, 60)
        d['Playtime'].setText(f"{h}h {m}m" if h else f"{m}m")

        self._start_size_calc(inst.path, d['Instance Size'])
        self._update_missing(inst, rw)

    def clear(self) -> None:
        """Reset all fields to '—' and hide the missing-mods warning."""
        for lbl in self._labels.values():
            lbl.setText('—')
        self.missing_label.hide()

    def _start_size_calc(self, path, size_label: QLabel) -> None:
        """Calculate folder size on a daemon thread and update size_label on completion."""
        size_label.setText('…')

        def _calc():
            try:
                text = human_size(get_folder_size(path))
            except (OSError, TypeError):
                text = '—'
            QTimer.singleShot(0, lambda: size_label.setText(text))

        threading.Thread(target=_calc, daemon=True).start()

    def _update_missing(self, inst: Instance, rw: RimWorldDetector | None) -> None:
        if rw and inst.mods:
            missing = rw.find_missing_mods(inst.mods)
            if missing:
                short = ", ".join(missing[:8])
                extra = f" +{len(missing) - 8} more" if len(missing) > 8 else ""
                self.missing_label.setText(
                    f"⚠ {len(missing)} mod(s) missing: {short}{extra}")
                self.missing_label.show()
                return
        self.missing_label.hide()


def _fmt_date(iso: str) -> str:
    if not iso:
        return ''
    try:
        return datetime.fromisoformat(iso).strftime("%b %d, %Y  %H:%M")
    except (ValueError, TypeError):
        return iso[:16]
