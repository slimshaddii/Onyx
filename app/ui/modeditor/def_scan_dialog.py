"""
Def collision scan dialog — 8.3 + 8.4 + 8.5 combined UI.

Shows a progress bar while the threaded scanner runs,
then displays results in a tree grouped by def type.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QStackedWidget, QWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from app.core.def_scanner import DefScannerThread, DefCollision
from app.core.rimworld import ModInfo


class DefScanDialog(QDialog):
    """
    Two-phase dialog:
      Phase 1 — progress bar while DefScannerThread runs
      Phase 2 — results tree after scan completes
    """

    def __init__(self, parent, active_mods: dict[str, ModInfo],
                 game_version: str):
        super().__init__(parent)
        self.active_mods   = active_mods
        self.game_version  = game_version
        self._collisions:  list[DefCollision] = []

        self.setWindowTitle("Def Collision Scanner")
        self.setMinimumSize(700, 480)
        self._build()
        self._start_scan()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setSpacing(8)

        self.stack = QStackedWidget()
        lo.addWidget(self.stack, 1)

        # ── Page 0: scanning progress ─────────────────────────────────────────
        scan_page = QWidget()
        sl        = QVBoxLayout(scan_page)
        sl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.scan_label = QLabel("Preparing scan…")
        self.scan_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scan_label.setStyleSheet("font-size:12px;")
        sl.addWidget(self.scan_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        sl.addWidget(self.progress_bar)

        self.mod_label = QLabel("")
        self.mod_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mod_label.setStyleSheet("color:#888;font-size:10px;")
        sl.addWidget(self.mod_label)

        self.stack.addWidget(scan_page)

        # ── Page 1: results ───────────────────────────────────────────────────
        results_page = QWidget()
        rl           = QVBoxLayout(results_page)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-size:11px;color:#888;")
        rl.addWidget(self.summary_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Def Type / Def Name", "Mod", "File"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        rl.addWidget(self.tree, 1)

        self.stack.addWidget(results_page)

        # ── Bottom buttons ────────────────────────────────────────────────────
        btns = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel)
        btns.addWidget(self.cancel_btn)
        btns.addStretch()
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setVisible(False)
        btns.addWidget(self.close_btn)
        lo.addLayout(btns)

    # ── Scanner ───────────────────────────────────────────────────────────────

    def _start_scan(self):
        n = len(self.active_mods)
        self.progress_bar.setMaximum(n)
        self.scan_label.setText(
            f"Scanning {n} mods for def collisions…")

        self._thread = DefScannerThread(
            self.active_mods, self.game_version, self)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished.connect(self._on_finished)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    def _on_progress(self, current: int, total: int, mod_name: str):
        self.progress_bar.setValue(current)
        self.mod_label.setText(f"Scanning: {mod_name}")

    def _on_finished(self, collisions: list):
        self._collisions = collisions
        self._show_results(collisions)

    def _on_error(self, msg: str):
        self.scan_label.setText(f"Scan failed: {msg}")
        self.cancel_btn.setText("Close")

    def _cancel(self):
        if hasattr(self, '_thread') and self._thread.isRunning():
            self._thread.terminate()
            self._thread.wait()
        self.reject()

    # ── Results ───────────────────────────────────────────────────────────────

    def _show_results(self, collisions: list[DefCollision]):
        self.stack.setCurrentIndex(1)
        self.cancel_btn.setVisible(False)
        self.close_btn.setVisible(True)

        if not collisions:
            self.summary_label.setText(
                f"✅ No def collisions found across "
                f"{len(self.active_mods)} mods.")
            empty = QTreeWidgetItem(self.tree)
            empty.setText(0, "No collisions detected")
            empty.setForeground(0, QColor('#4CAF50'))
            return

        # Group by def_type
        by_type: dict[str, list[DefCollision]] = {}
        for c in collisions:
            by_type.setdefault(c.def_type, []).append(c)

        self.summary_label.setText(
            f"⚠ {len(collisions)} def collision(s) found across "
            f"{len(by_type)} def type(s).  "
            f"({len(self.active_mods)} mods scanned)")

        for def_type in sorted(by_type):
            type_collisions = by_type[def_type]

            # Top-level: def type header
            type_item = QTreeWidgetItem(self.tree)
            type_item.setText(
                0, f"{def_type}  ({len(type_collisions)} collision(s))")
            type_item.setForeground(0, QColor('#ffaa00'))
            type_item.setExpanded(True)

            for collision in sorted(type_collisions,
                                    key=lambda c: c.def_name):
                # Second-level: defName
                def_item = QTreeWidgetItem(type_item)
                def_item.setText(0, collision.def_name)
                def_item.setForeground(0, QColor('#ff8800'))
                def_item.setExpanded(True)

                # Third-level: one row per mod
                for entry in collision.mods:
                    mod_item = QTreeWidgetItem(def_item)
                    mod_item.setText(0, '')
                    mod_item.setText(1, entry.mod_name)
                    mod_item.setText(2, entry.file_path)
                    mod_item.setForeground(1, QColor('#cccccc'))
                    mod_item.setForeground(2, QColor('#888888'))
                    mod_item.setToolTip(
                        1, f"Package ID: {entry.mod_id}")