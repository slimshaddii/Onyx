"""
Search for a mod across all instances.
Shows which instances have the mod active, inactive, or not at all.
"""

from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTreeWidget, QTreeWidgetItem, QHeaderView,
)
from PyQt6.QtCore import QTimer  # pylint: disable=no-name-in-module
from PyQt6.QtGui import QColor  # pylint: disable=no-name-in-module

from app.core.instance import Instance
from app.core.rimworld import ModInfo


class ModSearchDialog(QDialog):
    """Search for any mod by name or package ID across all instances."""

    def __init__(self, parent, instances: list[Instance],
                 all_mods: dict[str, ModInfo]):
        super().__init__(parent)
        self.instances = instances
        self.all_mods  = all_mods

        self.setWindowTitle("Search Mods Across Instances")
        self.setMinimumSize(640, 480)
        self._build()

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setSpacing(8)

        lo.addWidget(QLabel(
            "Search for a mod by name or package ID across all instances."))

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Type mod name or package ID…")
        self.search.setObjectName("searchBar")
        search_row.addWidget(self.search)
        lo.addLayout(search_row)

        self.result_label = QLabel("")
        self.result_label.setStyleSheet("color:#888;font-size:10px;")
        lo.addWidget(self.result_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Mod / Instance", "Status", "Package ID"])
        self.tree.setRootIsDecorated(True)
        self.tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        lo.addWidget(self.tree, 1)

        btns = QHBoxLayout()
        btns.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        lo.addLayout(btns)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._run_search)
        self.search.textChanged.connect(self._search_timer.start)

    def _run_search(self):
        query = self.search.text().strip().lower()
        self.tree.clear()

        if len(query) < 2:
            self.result_label.setText(
                "Type at least 2 characters to search.")
            return

        matches: dict[str, ModInfo | None] = {}
        for mid, info in self.all_mods.items():
            if (query in mid.lower() or
                    (info and query in info.name.lower())):
                matches[mid] = info

        for inst in self.instances:
            for mid in inst.all_mods:
                if mid not in matches and query in mid.lower():
                    matches[mid] = None

        if not matches:
            self.result_label.setText("No mods found.")
            return

        self.result_label.setText(
            f"{len(matches)} mod(s) found across "
            f"{len(self.instances)} instance(s).")

        for mid, info in sorted(matches.items(),
                                 key=lambda x: (
                                     x[1].name.lower() if x[1] else x[0])):
            mod_name = info.name if info else mid

            active_in   = [i for i in self.instances if mid in i.mods]
            inactive_in = [i for i in self.instances if mid in i.inactive_mods]
            unused_in   = [i for i in self.instances
                           if mid not in i.mods
                           and mid not in i.inactive_mods]

            mod_item = QTreeWidgetItem(self.tree)
            mod_item.setText(0, mod_name)
            mod_item.setText(1,
                f"Active: {len(active_in)}  "
                f"Inactive: {len(inactive_in)}  "
                f"Unused: {len(unused_in)}")
            mod_item.setText(2, mid)
            mod_item.setForeground(0, QColor('#74d4cc'))
            mod_item.setExpanded(True)

            for inst in active_in:
                child = QTreeWidgetItem(mod_item)
                child.setText(0, f"  {inst.name}")
                child.setText(1, "✅ Active")
                child.setForeground(1, QColor('#4CAF50'))

            for inst in inactive_in:
                child = QTreeWidgetItem(mod_item)
                child.setText(0, f"  {inst.name}")
                child.setText(1, "⏸ Inactive")
                child.setForeground(1, QColor('#888888'))

            if not active_in and not inactive_in:
                child = QTreeWidgetItem(mod_item)
                child.setText(0, "  (not used in any instance)")
                child.setForeground(0, QColor('#555555'))
