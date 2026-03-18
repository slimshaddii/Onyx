"""
Action button row for the instance detail panel.

Signals are exposed as plain pyqtSignal attributes so the parent
(InstanceDetailPanel) can connect them without knowing internals.
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PyQt6.QtCore import pyqtSignal


class DetailActions(QWidget):
    launch_clicked      = pyqtSignal()
    edit_mods_clicked   = pyqtSignal()
    duplicate_clicked   = pyqtSignal()
    folder_clicked      = pyqtSignal()
    export_pack_clicked = pyqtSignal()
    delete_clicked      = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(6)

        self.launch_btn = QPushButton("▶  Launch")
        self.launch_btn.setObjectName("primaryButton")
        self.launch_btn.clicked.connect(self.launch_clicked)
        lo.addWidget(self.launch_btn)

        self.edit_mods_btn = QPushButton("📦  Edit Mods")
        self.edit_mods_btn.clicked.connect(self.edit_mods_clicked)
        lo.addWidget(self.edit_mods_btn)

        self.duplicate_btn = QPushButton("📋  Duplicate")
        self.duplicate_btn.clicked.connect(self.duplicate_clicked)
        lo.addWidget(self.duplicate_btn)

        self.folder_btn = QPushButton("📁  Folder")
        self.folder_btn.clicked.connect(self.folder_clicked)
        lo.addWidget(self.folder_btn)

        self.export_pack_btn = QPushButton("◆")
        self.export_pack_btn.setFixedWidth(42)
        self.export_pack_btn.setToolTip("Export as .onyx pack")
        self.export_pack_btn.clicked.connect(self.export_pack_clicked)
        lo.addWidget(self.export_pack_btn)

        self.delete_btn = QPushButton("🗑")
        self.delete_btn.setObjectName("dangerButton")
        self.delete_btn.setFixedWidth(42)
        self.delete_btn.setToolTip("Delete this instance")
        self.delete_btn.clicked.connect(self.delete_clicked)
        lo.addWidget(self.delete_btn)

        self.set_enabled(False)

    def set_enabled(self, on: bool):
        for btn in (self.launch_btn, self.edit_mods_btn, self.duplicate_btn,
                    self.folder_btn, self.export_pack_btn, self.delete_btn):
            btn.setEnabled(on)