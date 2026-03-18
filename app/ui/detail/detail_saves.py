"""Saves GroupBox — lists .rws save files for the current instance."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
)

from app.core.instance import Instance
from app.utils.file_utils import human_size


class DetailSaves(QWidget):
    _MAX_SHOWN = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)

        saves_group = QGroupBox("Saves")
        self._saves_lo = QVBoxLayout()
        saves_group.setLayout(self._saves_lo)
        lo.addWidget(saves_group)

    def set_instance(self, inst: Instance):
        self._clear()
        saves = inst.get_save_files()
        if not saves:
            self._saves_lo.addWidget(QLabel("No saves yet"))
            return

        for s in saves[:self._MAX_SHOWN]:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"📄 {s['name']}"))
            row.addStretch()
            row.addWidget(QLabel(human_size(s['size'])))
            container = QWidget()
            container.setLayout(row)
            self._saves_lo.addWidget(container)

        if len(saves) > self._MAX_SHOWN:
            self._saves_lo.addWidget(
                QLabel(f"… +{len(saves) - self._MAX_SHOWN} more"))

    def clear(self):
        self._clear()
        self._saves_lo.addWidget(QLabel("No saves yet"))

    def _clear(self):
        while self._saves_lo.count():
            child = self._saves_lo.takeAt(0)
            if child.widget():
                child.widget().deleteLater()