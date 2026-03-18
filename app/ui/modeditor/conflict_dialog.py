"""
Conflict and performance report dialog.

Shows all JuMLi notices and incompatibleWith conflicts
for the current active mod list.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from app.core.rimworld import ModInfo
from app.core.conflict_db import ConflictDB
from app.ui.modeditor.issue_checker import COLOR_ERROR, COLOR_DEPENDENCY, COLOR_ORDER, COLOR_INFO


# ── Notice type display config ────────────────────────────────────────────────
_TYPE_CONFIG = {
    'incompatible': ('🚫', COLOR_ERROR,      'Incompatible'),
    'unstable':     ('⚠',  COLOR_DEPENDENCY, 'Unstable'),
    'alternative':  ('💡', COLOR_DEPENDENCY, 'Better Alternative'),
    'performance':  ('🐢', COLOR_ORDER,      'Performance'),
    'info':         ('ℹ',  COLOR_INFO,       'Info / Settings'),
}


class ConflictReportDialog(QDialog):
    """
    Shows all detected conflicts and performance notices
    for the currently active mod list.
    """

    def __init__(self, parent, active_ids: list[str],
                 all_mods: dict[str, ModInfo],
                 mod_names: dict[str, str]):
        super().__init__(parent)
        self.active_ids = active_ids
        self.all_mods   = all_mods
        self.mod_names  = mod_names

        self.setWindowTitle("Conflict & Performance Report")
        self.setMinimumSize(760, 500)
        self._build()
        self._populate()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setSpacing(6)

        self.summary = QLabel("")
        self.summary.setStyleSheet("font-size:11px; color:#888;")
        lo.addWidget(self.summary)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Mod", "Type", "Notice"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tree.setWordWrap(True)
        lo.addWidget(self.tree, 1)

        btns = QHBoxLayout()
        btns.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        lo.addLayout(btns)

    # ── Population ────────────────────────────────────────────────────────────

    def _populate(self):
        self.tree.clear()
        db          = ConflictDB.instance()
        active_set  = set(self.active_ids)
        total       = 0
        errors      = 0
        warnings    = 0

        for mid in self.active_ids:
            info = self.all_mods.get(mid)
            name = self.mod_names.get(mid, mid)
            row_notices: list[tuple[str, str, str]] = []
            # (notice_type, message, color)

            # ── incompatibleWith from About.xml ───────────────────────────────
            if info:
                for incompat in info.incompatible_with:
                    incompat_l = incompat.lower()
                    if incompat_l in active_set:
                        incompat_name = (self.all_mods[incompat_l].name
                                         if incompat_l in self.all_mods
                                         else incompat_l)
                        row_notices.append((
                            'incompatible',
                            f"Incompatible with '{incompat_name}' "
                            f"(declared in {name}'s About.xml)",
                            COLOR_ERROR,
                        ))
                        errors += 1

            # ── JuMLi notices ─────────────────────────────────────────────────
            wid = info.workshop_id if info else ''
            for notice in db.get_notices(mid, wid):
                row_notices.append((
                    notice.notice_type,
                    notice.message,
                    _TYPE_CONFIG.get(notice.notice_type,
                                     ('ℹ', COLOR_INFO, 'Info'))[1],
                ))
                if notice.notice_type == 'unstable':
                    warnings += 1
                elif notice.notice_type == 'performance':
                    warnings += 1
                elif notice.notice_type == 'alternative':
                    warnings += 1

            if not row_notices:
                continue

            total += 1

            # ── Parent row — mod name ─────────────────────────────────────────
            parent = QTreeWidgetItem(self.tree)
            parent.setText(0, name)
            parent.setText(1, '')
            parent.setText(2, f"[{mid}]")
            parent.setForeground(0, QColor('#ffffff'))
            parent.setExpanded(True)

            # ── Child rows — individual notices ───────────────────────────────
            for notice_type, message, color in row_notices:
                icon, _, label = _TYPE_CONFIG.get(
                    notice_type, ('ℹ', COLOR_INFO, 'Info'))
                child = QTreeWidgetItem(parent)
                child.setText(0, '')
                child.setText(1, f"{icon} {label}")
                child.setText(2, message)
                child.setForeground(1, QColor(color))
                child.setForeground(2, QColor('#cccccc'))
                # Allow text to wrap by setting a reasonable row height hint
                child.setToolTip(2, message)

        if total == 0:
            empty = QTreeWidgetItem(self.tree)
            empty.setText(0, "✅ No conflicts or notices found")
            empty.setForeground(0, QColor('#4CAF50'))

        incompats = errors
        perf      = total - incompats if total > incompats else 0
        parts     = []
        if incompats:
            parts.append(f"❌ {incompats} incompatible mod(s)")
        if warnings:
            parts.append(f"⚠ {warnings} performance/stability notice(s)")
        if not parts:
            parts.append("✅ No issues found")
        self.summary.setText("  ·  ".join(parts) +
                             f"  ({len(self.active_ids)} mods checked)")