"""
Save compatibility helpers for the UI layer.

Keeps the visual mapping (color, icon, label) in one place so
detail_saves.py and launch_dialog.py stay consistent.
"""

from app.core.save_parser import SaveCompat

# ── Visual mapping ────────────────────────────────────────────────────────────

COMPAT_ICON: dict[SaveCompat, str] = {
    SaveCompat.COMPATIBLE: '✅',
    SaveCompat.CHANGED:    '⚠',
    SaveCompat.MISSING:    '❌',
    SaveCompat.UNKNOWN:    '❓',
}

COMPAT_COLOR: dict[SaveCompat, str] = {
    SaveCompat.COMPATIBLE: '#4CAF50',   # green
    SaveCompat.CHANGED:    '#ffaa00',   # yellow
    SaveCompat.MISSING:    '#ff4444',   # red
    SaveCompat.UNKNOWN:    '#888888',   # grey
}

COMPAT_LABEL: dict[SaveCompat, str] = {
    SaveCompat.COMPATIBLE: 'Compatible',
    SaveCompat.CHANGED:    'Mods changed',
    SaveCompat.MISSING:    'Mods missing',
    SaveCompat.UNKNOWN:    'Unknown',
}


def compat_style(compat: SaveCompat) -> str:
    """Return a QSS color string for a QLabel."""
    color = COMPAT_COLOR[compat]
    return f"color:{color}; background:transparent; padding:1px 4px;"