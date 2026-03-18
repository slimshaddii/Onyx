"""
Action button row for the instance detail panel.
"""

from app.core.app_settings import AppSettings
from app.ui.styles import get_colors
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PyQt6.QtCore import pyqtSignal


def _get_styles() -> tuple[str, str, str]:
    """Return (primary, danger, default) styles for current theme."""
    c = get_colors(AppSettings.instance().theme)
    primary = f"""
        QPushButton {{
            background: {c['accent']}; color: {c['bg']};
            border: none; border-radius: 5px;
            padding: 5px 14px; font-weight: 700; font-size: 11px;
        }}
        QPushButton:hover    {{ background: {c['accent']}dd; }}
        QPushButton:pressed  {{ background: {c['accent']}aa; }}
        QPushButton:disabled {{ background: {c['border']}; color: {c['text_dim']}; }}
    """
    danger = f"""
        QPushButton {{
            background: {c['error']}; color: #ffffff;
            border: none; border-radius: 5px;
            padding: 5px 14px; font-weight: 600; font-size: 11px;
        }}
        QPushButton:hover    {{ background: {c['error']}dd; }}
        QPushButton:pressed  {{ background: {c['error']}aa; }}
        QPushButton:disabled {{ background: {c['border']}; color: {c['text_dim']}; }}
    """
    default = f"""
        QPushButton {{
            background: {c['bg_mid']}; color: {c['text']};
            border: 1px solid {c['border']}; border-radius: 5px;
            padding: 5px 14px; font-weight: 600; font-size: 11px;
        }}
        QPushButton:hover    {{ background: {c['bg_card']}; }}
        QPushButton:pressed  {{ background: {c['border']}; }}
        QPushButton:disabled {{ background: {c['bg_panel']}; color: {c['text_dim']}; }}
    """
    return primary, danger, default


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

        primary, danger, default = _get_styles()

        self.launch_btn = QPushButton("▶  Launch")
        self.launch_btn.setStyleSheet(primary)
        self.launch_btn.clicked.connect(self.launch_clicked)
        lo.addWidget(self.launch_btn)

        self.edit_mods_btn = QPushButton("📦  Edit Mods")
        self.edit_mods_btn.setStyleSheet(default)
        self.edit_mods_btn.clicked.connect(self.edit_mods_clicked)
        lo.addWidget(self.edit_mods_btn)

        self.duplicate_btn = QPushButton("📋  Duplicate")
        self.duplicate_btn.setStyleSheet(default)
        self.duplicate_btn.clicked.connect(self.duplicate_clicked)
        lo.addWidget(self.duplicate_btn)

        self.folder_btn = QPushButton("📁  Folder")
        self.folder_btn.setStyleSheet(default)
        self.folder_btn.clicked.connect(self.folder_clicked)
        lo.addWidget(self.folder_btn)

        self.export_pack_btn = QPushButton("◆")
        self.export_pack_btn.setFixedWidth(42)
        self.export_pack_btn.setToolTip("Export as .onyx pack")
        self.export_pack_btn.setStyleSheet(default)
        self.export_pack_btn.clicked.connect(self.export_pack_clicked)
        lo.addWidget(self.export_pack_btn)

        self.delete_btn = QPushButton("🗑")
        self.delete_btn.setFixedWidth(42)
        self.delete_btn.setToolTip("Delete this instance")
        self.delete_btn.setStyleSheet(danger)
        self.delete_btn.clicked.connect(self.delete_clicked)
        lo.addWidget(self.delete_btn)

        self.set_enabled(False)

    def set_enabled(self, on: bool):
        # Refresh styles in case theme changed since init
        primary, danger, default = _get_styles()
        self.launch_btn.setStyleSheet(primary)
        self.edit_mods_btn.setStyleSheet(default)
        self.duplicate_btn.setStyleSheet(default)
        self.folder_btn.setStyleSheet(default)
        self.export_pack_btn.setStyleSheet(default)
        self.delete_btn.setStyleSheet(danger)

        for btn in (self.launch_btn, self.edit_mods_btn, self.duplicate_btn,
                    self.folder_btn, self.export_pack_btn, self.delete_btn):
            btn.setEnabled(on)