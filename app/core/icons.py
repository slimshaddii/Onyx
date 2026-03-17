"""
Instance icon generation — Prism-style letter icons with colors.
"""

import hashlib
from pathlib import Path
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QIcon
from PyQt6.QtCore import Qt, QRect


PALETTE = [
    '#e53935', '#d81b60', '#8e24aa', '#5e35b1',
    '#3949ab', '#1e88e5', '#039be5', '#00acc1',
    '#00897b', '#43a047', '#7cb342', '#c0ca33',
    '#fdd835', '#ffb300', '#fb8c00', '#f4511e',
    '#6d4c41', '#757575', '#546e7a', '#26a69a',
]

RW_ICONS = {
    'rimworld':  '🎮', 'modded': '🔧', 'vanilla': '🌿',
    'combat':    '⚔️', 'build':  '🏗️', 'mech':   '🤖',
    'magic':     '✨', 'horror': '👁️', 'colony': '🏘️',
    'medieval':  '🏰', 'tribal': '🪶', 'space':  '🚀',
    'hardcore':  '💀', 'chill':  '☕', 'test':   '🧪',
}


def color_for_name(name: str) -> str:
    h = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
    return PALETTE[h % len(PALETTE)]


def generate_icon(name: str, size: int = 48, color: str = '') -> QPixmap:
    if not color:
        color = color_for_name(name)
    letter = name[0].upper() if name else '?'

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Background rounded rect
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    radius = size // 5
    p.drawRoundedRect(0, 0, size, size, radius, radius)

    # Letter
    p.setPen(QColor('#ffffff'))
    font = QFont('Segoe UI', int(size * 0.45), QFont.Weight.Bold)
    p.setFont(font)
    p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, letter)
    p.end()
    return pm


def load_icon(instance_path: Path, instance_name: str,
              icon_color: str = '', icon_key: str = '') -> QPixmap:
    """Load custom icon or generate one."""
    # Check for custom icon
    for ext in ('png', 'jpg', 'jpeg', 'ico', 'bmp'):
        custom = instance_path / f'icon.{ext}'
        if custom.exists():
            pm = QPixmap(str(custom))
            if not pm.isNull():
                return pm.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)

    return generate_icon(instance_name, 48, icon_color)


def get_icon_choices() -> list[tuple[str, str]]:
    """Return (key, emoji) pairs for the icon picker."""
    return list(RW_ICONS.items())


def get_color_choices() -> list[str]:
    return list(PALETTE)