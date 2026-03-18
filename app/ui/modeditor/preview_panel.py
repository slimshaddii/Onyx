"""Mod preview panel."""

from pathlib import Path
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from app.core.rimworld import ModInfo
from app.core.app_settings import AppSettings
from app.ui.styles import get_colors


class PreviewPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_image_path: str = ''
        c = get_colors(AppSettings.instance().theme)

        lo = QVBoxLayout(self)
        lo.setContentsMargins(4, 0, 0, 0)
        lo.setSpacing(3)

        self.img = QLabel()
        self.img.setMinimumHeight(100)
        self.img.setMaximumHeight(140)
        self.img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img.setStyleSheet(
            f"background:{c['bg_panel']};border-radius:6px;")
        self.img.setText("Select a mod")
        lo.addWidget(self.img)

        self.name = QLabel("")
        self.name.setStyleSheet(
            f"font-weight:bold;font-size:12px;color:{c['accent']};")
        self.name.setWordWrap(True)
        lo.addWidget(self.name)

        self.meta = QLabel("")
        self.meta.setStyleSheet(
            f"font-size:10px;color:{c['text_dim']};")
        self.meta.setWordWrap(True)
        lo.addWidget(self.meta)

        self.issues = QLabel("")
        self.issues.setTextFormat(Qt.TextFormat.RichText)
        self.issues.setStyleSheet("font-size:10px;")
        self.issues.setWordWrap(True)
        lo.addWidget(self.issues)

        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        self.desc.setStyleSheet(
            f"font-size:11px;color:{c['text_faint']};")
        self.desc.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.desc)
        scroll.setStyleSheet("border:none;")
        lo.addWidget(scroll, 1)

    def show_mod(self, info: ModInfo | None, mid: str,
                 badges: list[tuple[str, str, str, str]]):
        c = get_colors(AppSettings.instance().theme)

        if not info:
            self.name.setText(mid)
            self.meta.setText("❌ Not found on disk")
            self.desc.setText("")
            self.issues.setText("")
            self.img.setText("N/A")
            self._current_image_path = ''
            return

        self.name.setText(info.name)

        parts = [f"ID: {info.package_id}", f"By: {info.author}"]
        if info.supported_versions:
            parts.append(f"v{', '.join(info.supported_versions)}")
        if info.workshop_id:
            parts.append(f"WS: {info.workshop_id}")
        parts.append(f"Src: {info.source}")
        self.meta.setText(" • ".join(parts))

        if badges:
            html = '<br>'.join(
                f"<span style='color:{b[1]}'>{b[0]} {b[3]}</span>"
                for b in badges)
            self.issues.setText(html)
        else:
            self.issues.setText(
                f"<span style='color:{c['success']}'>✔ No issues</span>")

        self.desc.setText(
            info.description[:2000] if info.description else "No description.")

        self._current_image_path = info.preview_image or ''
        self._load_preview_image()

    def _load_preview_image(self):
        path = self._current_image_path
        if path and Path(path).exists():
            pm = QPixmap(path)
            if not pm.isNull():
                w = max(self.img.width() - 4, 60)
                h = self.img.maximumHeight() - 4
                self.img.setPixmap(pm.scaled(
                    w, h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
                return
        self.img.clear()
        self.img.setText("No preview")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._current_image_path:
            self._load_preview_image()