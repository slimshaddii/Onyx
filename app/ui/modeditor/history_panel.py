"""
Modlist history dialog — browse, diff, and roll back mod list snapshots.

Opened from the mod editor's bottom bar via the History button.
"""

from PyQt6.QtCore import Qt  # pylint: disable=no-name-in-module
from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QWidget,
    QTextEdit, QInputDialog, QMessageBox,
)

from app.core.mod_history import ModHistory, Snapshot


class HistoryDialog(QDialog):
    """
    Shows the snapshot list on the left.
    Selecting a snapshot shows its mod list on the right.
    Selecting two snapshots shows a diff.
    """

    def __init__(self, parent, history: ModHistory,
             current_mods: list[str],
             mod_names: dict[str, str]):
        super().__init__(parent)
        self.history       = history
        self.current_mods  = current_mods
        self.mod_names     = mod_names
        self.rolled_back_mods: list[str] | None = None

        # Widget attributes — assigned in _build_left_panel / _build_right_panel
        self.snap_list:    QListWidget  | None = None
        self.save_snap_btn: QPushButton | None = None
        self.del_btn:      QPushButton  | None = None
        self.detail_label: QLabel       | None = None
        self.detail_view:  QTextEdit    | None = None
        self.rollback_btn: QPushButton  | None = None

        self.setWindowTitle("Modlist History")
        self.setMinimumSize(720, 480)
        self._build()
        self._load_snapshots()

    def _build(self) -> None:
        lo = QVBoxLayout(self)
        lo.setSpacing(6)

        hint = QLabel(
            "Select one snapshot to view its mod list.  "
            "Select two to compare them.")
        hint.setStyleSheet("color:#888; font-size:11px;")
        lo.addWidget(hint)

        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(self._build_left_panel())
        sp.addWidget(self._build_right_panel())
        sp.setSizes([260, 440])
        lo.addWidget(sp, 1)

        btns      = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(close_btn)
        lo.addLayout(btns)

    def _build_left_panel(self) -> QWidget:
        left = QWidget()
        ll   = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)

        ll.addWidget(QLabel("Snapshots:"))
        self.snap_list = QListWidget()
        self.snap_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection)
        self.snap_list.itemSelectionChanged.connect(self._on_selection)
        ll.addWidget(self.snap_list, 1)

        btn_row = QHBoxLayout()
        self.save_snap_btn = QPushButton("💾 Save Snapshot")
        self.save_snap_btn.setToolTip(
            "Save a named snapshot of the current mod list")
        self.save_snap_btn.clicked.connect(self._save_snapshot)
        btn_row.addWidget(self.save_snap_btn)

        self.del_btn = QPushButton("🗑 Delete")
        self.del_btn.setEnabled(False)
        self.del_btn.clicked.connect(self._delete_snapshot)
        btn_row.addWidget(self.del_btn)
        ll.addLayout(btn_row)

        return left

    def _build_right_panel(self) -> QWidget:
        right = QWidget()
        rl    = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)

        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("font-weight:bold;")
        rl.addWidget(self.detail_label)

        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setStyleSheet("font-size:11px;")
        rl.addWidget(self.detail_view, 1)

        self.rollback_btn = QPushButton("↩ Roll Back to This Snapshot")
        self.rollback_btn.setObjectName("primaryButton")
        self.rollback_btn.setEnabled(False)
        self.rollback_btn.clicked.connect(self._rollback)
        rl.addWidget(self.rollback_btn)

        return right

    def _load_snapshots(self) -> None:
        self.snap_list.clear()
        for i, snap in enumerate(self.history.snapshots):
            text = (f"{snap.fmt_date()}  —  {snap.label}"
                    f"  ({snap.mod_count} mods)")
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, i)
            self.snap_list.addItem(it)

        if not self.history.snapshots:
            self.detail_label.setText("No history yet.")
            self.detail_view.setPlainText(
                "Snapshots are recorded automatically each time you save "
                "from the mod editor.")

    def _on_selection(self) -> None:
        selected = self.snap_list.selectedItems()
        self.del_btn.setEnabled(bool(selected))

        if len(selected) == 1:
            idx  = selected[0].data(Qt.ItemDataRole.UserRole)
            snap = self.history.snapshots[idx]
            self._show_snapshot(snap)
            self.rollback_btn.setEnabled(True)

        elif len(selected) == 2:
            idx_a  = selected[0].data(Qt.ItemDataRole.UserRole)
            idx_b  = selected[1].data(Qt.ItemDataRole.UserRole)
            snap_a = self.history.snapshots[idx_a]
            snap_b = self.history.snapshots[idx_b]
            self._show_diff(snap_a, snap_b)
            self.rollback_btn.setEnabled(False)

        else:
            self.detail_label.setText("")
            self.detail_view.setPlainText("")
            self.rollback_btn.setEnabled(False)

    def _show_snapshot(self, snap: Snapshot) -> None:
        self.detail_label.setText(
            f"{snap.fmt_date()}  —  {snap.label}  ({snap.mod_count} mods)")
        lines = [
            f"{i:3}.  {self.mod_names.get(mid, mid)}  [{mid}]"
            for i, mid in enumerate(snap.mods, 1)
        ]
        self.detail_view.setPlainText('\n'.join(lines))

    def _show_diff(self, snap_a: Snapshot, snap_b: Snapshot) -> None:
        newer = snap_a if snap_a.timestamp > snap_b.timestamp else snap_b
        older = snap_b if snap_a.timestamp > snap_b.timestamp else snap_a
        diff  = self.history.diff(newer, older)

        self.detail_label.setText(
            f"Diff:  {older.fmt_date()}  →  {newer.fmt_date()}")

        lines: list[str] = []

        if diff['added']:
            lines.append(f"── Added ({len(diff['added'])}) ──────────────")
            for mid in diff['added']:
                lines.append(f"  + {self.mod_names.get(mid, mid)}  [{mid}]")

        if diff['removed']:
            if lines:
                lines.append('')
            lines.append(f"── Removed ({len(diff['removed'])}) ──────────")
            for mid in diff['removed']:
                lines.append(f"  - {self.mod_names.get(mid, mid)}  [{mid}]")

        if not diff['added'] and not diff['removed']:
            lines.append("These two snapshots are identical.")

        self.detail_view.setPlainText('\n'.join(lines))

    def _save_snapshot(self) -> None:
        label, ok = QInputDialog.getText(
            self, "Save Snapshot", "Snapshot label:",
            text="Manual snapshot")
        if not ok or not label.strip():
            return
        self.history.record(self.current_mods, label.strip())
        self._load_snapshots()

    def _delete_snapshot(self) -> None:
        selected = self.snap_list.selectedItems()
        if not selected:
            return

        if QMessageBox.question(
                self, "Delete",
                f"Delete {len(selected)} snapshot(s)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        indices = sorted(
            [it.data(Qt.ItemDataRole.UserRole) for it in selected],
            reverse=True)
        for idx in indices:
            self.history.delete(idx)

        self._load_snapshots()
        self.detail_label.setText("")
        self.detail_view.setPlainText("")
        self.rollback_btn.setEnabled(False)
        self.del_btn.setEnabled(False)

    def _rollback(self) -> None:
        selected = self.snap_list.selectedItems()
        if len(selected) != 1:
            return

        idx  = selected[0].data(Qt.ItemDataRole.UserRole)
        snap = self.history.snapshots[idx]

        reply = QMessageBox.question(
            self, "Roll Back",
            f"Restore mod list from:\n\n"
            f"  {snap.fmt_date()} — {snap.label}\n"
            f"  {snap.mod_count} mods\n\n"
            f"This will replace your current active mod list in the editor. "
            f"You still need to click Save to apply it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.rolled_back_mods = list(snap.mods)
        self.accept()
