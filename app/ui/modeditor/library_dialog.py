"""Library browser — add mods from global pool to an instance."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QAbstractItemView,
)
from PyQt6.QtCore import Qt

from app.core.rimworld import ModInfo
from app.core.modlist import VANILLA_AND_DLCS


class LibraryDialog(QDialog):
    """Browse all installed mods and pick ones to add to an instance."""

    def __init__(self, parent, all_mods: dict[str, ModInfo],
                 instance_mod_ids: set[str], game_version: str = ''):
        super().__init__(parent)
        self.all_mods         = all_mods
        self.instance_mod_ids = instance_mod_ids
        self.game_version     = game_version
        self.selected_ids: list[str] = []

        self.setWindowTitle("Mod Library — Add to Instance")
        self.setMinimumSize(520, 480)
        self._build()
        self._load()

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setSpacing(6)

        lo.addWidget(QLabel(
            "<b>Mod Library</b> — Select mods to add to this instance"))

        hint = QLabel(
            "These mods are installed on your system but not yet part of "
            "this instance. Select mods and click 'Add to Instance'.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#888;font-size:11px;")
        lo.addWidget(hint)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Search mods…")
        self.search.textChanged.connect(self._filter)
        lo.addWidget(self.search)

        self.mod_list = QListWidget()
        self.mod_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        lo.addWidget(self.mod_list, 1)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color:#888;font-size:10px;")
        lo.addWidget(self.count_label)

        btns = QHBoxLayout()
        self.sel_label = QLabel("0 selected")
        self.sel_label.setStyleSheet(
            "color:#74d4cc;font-size:11px;font-weight:bold;")
        btns.addWidget(self.sel_label)
        btns.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        add_btn = QPushButton("Add to Instance")
        add_btn.setObjectName("primaryButton")
        add_btn.clicked.connect(self._add)
        btns.addWidget(add_btn)
        lo.addLayout(btns)

        self.mod_list.itemSelectionChanged.connect(self._on_sel_changed)

    def _load(self):
        self.mod_list.clear()
        count = 0

        for mid, info in sorted(self.all_mods.items(),
                                 key=lambda x: x[1].name.lower()):
            if mid in self.instance_mod_ids:
                continue
            if mid in VANILLA_AND_DLCS:
                continue

            src = {'dlc': '👑', 'workshop': '🏪', 'local': '📁'}.get(
                info.source, '📁')
            it = QListWidgetItem(f"{src}  {info.name}  [{mid}]")
            it.setData(Qt.ItemDataRole.UserRole, mid)
            it.setToolTip(
                f"{info.name}\nBy: {info.author}\n"
                + (f"Workshop: {info.workshop_id}"
                   if info.workshop_id else f"Source: {info.source}")
            )
            self.mod_list.addItem(it)
            count += 1

        self.count_label.setText(f"{count} mods available in library")

    def _filter(self):
        q = self.search.text().lower()
        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            item.setHidden(q not in item.text().lower())

    def _on_sel_changed(self):
        n = len(self.mod_list.selectedItems())
        self.sel_label.setText(f"{n} selected")

    def _add(self):
        self.selected_ids = [
            it.data(Qt.ItemDataRole.UserRole)
            for it in self.mod_list.selectedItems()
        ]
        if self.selected_ids:
            self.accept()