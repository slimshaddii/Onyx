"""
Instance icon generation — Prism-style letter icons with colors.
"""

import hashlib
import platform
from pathlib import Path

from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont  # pylint: disable=no-name-in-module
from PyQt6.QtCore import Qt, QRect  # pylint: disable=no-name-in-module


PALETTE = [
    '#e53935', '#d81b60', '#8e24aa', '#5e35b1',
    '#3949ab', '#1e88e5', '#039be5', '#00acc1',
    '#00897b', '#43a047', '#7cb342', '#c0ca33',
    '#fdd835', '#ffb300', '#fb8c00', '#f4511e',
    '#6d4c41', '#757575', '#546e7a', '#26a69a',
]

RW_ICONS: dict[str, str] = {
    'rimworld': '🎮', 'modded':  '🔧', 'vanilla': '🌿',
    'combat':   '⚔️', 'build':   '🏗️', 'mech':   '🤖',
    'magic':    '✨', 'horror':  '👁️', 'colony': '🏘️',
    'medieval': '🏰', 'tribal':  '🪶', 'space':  '🚀',
    'hardcore': '💀', 'chill':   '☕', 'test':   '🧪',
}

# Custom image extensions to check before generating a letter icon, in order.
_ICON_EXTENSIONS = ('png', 'jpg', 'jpeg', 'ico', 'bmp')

# Platform UI font — resolved once at import time; Qt handles fallback.
_system = platform.system()
if _system == 'Windows':
    _UI_FONT = 'Segoe UI'
elif _system == 'Darwin':
    _UI_FONT = 'SF Pro Display'
else:
    _UI_FONT = 'Ubuntu'  # Qt falls back to Noto Sans / DejaVu / system default


# ── Public API ────────────────────────────────────────────────────────────────

def color_for_name(name: str) -> str:
    """
    Derive a deterministic palette color from an instance name.

    Uses the first 8 hex digits of the MD5 hash mapped to PALETTE indices.
    The result is stable for the same name across runs.
    """
    digest = hashlib.md5(name.encode(), usedforsecurity=False).hexdigest()[:8]
    return PALETTE[int(digest, 16) % len(PALETTE)]


def generate_icon(name: str, size: int = 48, color: str = '',
                  glyph: str = '') -> QPixmap:
    """
    Render a Prism-style rounded-rectangle icon with a centered letter or glyph.

    Parameters
    ----------
    name  : Instance name — used to derive color if color is empty,
            and provides the fallback letter (first character).
    size  : Pixel dimensions of the square pixmap.
    color : Hex color string for the background. Derived from name if empty.
    glyph : Override character/emoji to draw instead of the first letter of name.
    """
    bg_color = color or color_for_name(name)
    symbol   = glyph or (name[0].upper() if name else '?')

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    _paint_background(painter, size, bg_color)
    _paint_symbol(painter, size, symbol)

    painter.end()
    return pm


def load_icon(instance_path: Path, instance_name: str,
              icon_color: str = '', icon_key: str = '') -> QPixmap:
    """
    Load the best available icon for an instance.

    Priority:
      1. Custom image file (icon.png / .jpg / .jpeg / .ico / .bmp)
         placed in the instance directory.
      2. Emoji glyph from RW_ICONS if icon_key is set and recognised.
      3. Generated letter icon using instance_name and icon_color.
    """
    custom = _find_custom_image(instance_path)
    if custom is not None:
        return custom

    glyph = RW_ICONS.get(icon_key.lower().strip()) if icon_key else ''
    return generate_icon(instance_name, 48, icon_color, glyph)


def get_icon_choices() -> list[tuple[str, str]]:
    """Return all available (key, emoji) icon choices."""
    return list(RW_ICONS.items())


def get_color_choices() -> list[str]:
    """Return the full color palette as a list of hex strings."""
    return list(PALETTE)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _find_custom_image(instance_path: Path) -> QPixmap | None:
    """
    Search the instance directory for a custom icon image.

    Returns a scaled 48×48 QPixmap if found and valid, otherwise None.
    """
    for ext in _ICON_EXTENSIONS:
        candidate = instance_path / f'icon.{ext}'
        if candidate.exists():
            pm = QPixmap(str(candidate))
            if not pm.isNull():
                return pm.scaled(
                    48, 48,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
    return None


def _paint_background(painter: QPainter, size: int, color: str) -> None:
    """Fill the painter canvas with a rounded rectangle in the given color."""
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    radius = size // 5
    painter.drawRoundedRect(0, 0, size, size, radius, radius)


def _paint_symbol(painter: QPainter, size: int, symbol: str) -> None:
    """Draw a centered symbol (letter or emoji) in white over the background."""
    painter.setPen(QColor('#ffffff'))
    font = QFont(_UI_FONT, int(size * 0.45), QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(QRect(0, 0, size, size),
                     Qt.AlignmentFlag.AlignCenter, symbol)
