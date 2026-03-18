"""Mod preview panel."""

from pathlib import Path
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from app.core.rimworld import ModInfo


class PreviewPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(4, 0, 0, 0)
        lo.setSpacing(3)

        self.img = QLabel()
        self.img.setFixedHeight(100)
        self.img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img.setStyleSheet("background:#1a1a1a;border-radius:6px;")
        self.img.setText("Select a mod")
        lo.addWidget(self.img)

        # Name uses teal accent (#74d4cc) — consistent with Prism palette
        self.name = QLabel("")
        self.name.setStyleSheet(
            "font-weight:bold;font-size:12px;color:#74d4cc;")
        self.name.setWordWrap(True)
        lo.addWidget(self.name)

        self.meta = QLabel("")
        self.meta.setStyleSheet("font-size:10px;color:#888;")
        self.meta.setWordWrap(True)
        lo.addWidget(self.meta)

        self.issues = QLabel("")
        self.issues.setTextFormat(Qt.TextFormat.RichText)
        self.issues.setStyleSheet("font-size:10px;")
        self.issues.setWordWrap(True)
        lo.addWidget(self.issues)

        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        self.desc.setStyleSheet("font-size:11px;color:#aaa;")
        self.desc.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.desc)
        scroll.setStyleSheet("border:none;")
        lo.addWidget(scroll, 1)

    def show_mod(self, info: ModInfo | None, mid: str,
                 badges: list[tuple[str, str, str, str]]):
        if not info:
            self.name.setText(mid)
            self.meta.setText("❌ Not found on disk")
            self.desc.setText("")
            self.issues.setText("")
            self.img.setText("N/A")
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
                "<span style='color:#4CAF50'>✔ No issues</span>")

        self.desc.setText(
            info.description[:2000] if info.description else "No description.")

        if info.preview_image and Path(info.preview_image).exists():
            pm = QPixmap(info.preview_image)
            if not pm.isNull():
                w = self.img.width()
                target_w = w - 4 if w > 60 else 220
                self.img.setPixmap(pm.scaled(
                    target_w, 94,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
                return
        self.img.setText("No preview")