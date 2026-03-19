"""Library browser — add, delete, or redownload mods from the global pool."""

import shutil
from pathlib import Path

from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QAbstractItemView,
    QMenu, QMessageBox,
)
from PyQt6.QtCore import Qt  # pylint: disable=no-name-in-module

from app.core.app_settings import AppSettings
from app.core.mod_linker import delete_mod_permanently
from app.core.modlist import VANILLA_AND_DLCS
from app.core.rimworld import RimWorldDetector, ModInfo
from app.core.steam_integration import open_workshop_page
from app.core.steamcmd import DownloadQueue


class LibraryDialog(QDialog):
    """Browse all installed mods and pick ones to add to an instance."""

    def __init__(self, parent, all_mods: dict[str, ModInfo],
                 instance_mod_ids: set[str], game_version: str = '',
                 rw: RimWorldDetector | None = None):
        super().__init__(parent)
        self.all_mods         = all_mods
        self.instance_mod_ids = instance_mod_ids
        self.game_version     = game_version
        self.rw               = rw
        self.selected_ids: list[str] = []

        self.search:      QLineEdit   | None = None
        self.mod_list:    QListWidget | None = None
        self.count_label: QLabel      | None = None
        self.sel_label:   QLabel      | None = None

        self.setWindowTitle("Mod Library — Add to Instance")
        self.setMinimumSize(560, 520)
        self._build()
        self._load()

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setSpacing(6)

        lo.addWidget(QLabel(
            "<b>Mod Library</b> — Select mods to add to this instance"))

        hint = QLabel(
            "These mods are installed on your system but not yet part of "
            "this instance. Select mods and click 'Add to Instance'.\n"
            "Right-click a mod to delete or redownload it.")
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
        self.mod_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.mod_list.customContextMenuRequested.connect(self._ctx_menu)
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

    def _ctx_menu(self, pos):
        it = self.mod_list.itemAt(pos)
        if not it:
            return
        mid  = it.data(Qt.ItemDataRole.UserRole)
        info = self.all_mods.get(mid)
        if not info:
            return

        m = QMenu(self)
        m.addAction("Add to Instance", self._add)

        if info.path and info.path.exists():
            m.addSeparator()
            m.addAction("🗑 Delete mod files…",
                        lambda: self._delete_mod(mid))

        if info.workshop_id:
            m.addAction("⟳ Redownload from Workshop",
                        lambda: self._redownload_mod(mid))
            m.addSeparator()
            m.addAction("Workshop page",
                        lambda: open_workshop_page(info.workshop_id))

        m.exec(self.mod_list.mapToGlobal(pos))

    def _delete_mod(self, mid: str):
        info = self.all_mods.get(mid)
        if not info or not info.path or not info.path.exists():
            QMessageBox.warning(self, "Delete", "Mod folder not found.")
            return

        reply = QMessageBox.question(
            self, "Delete Mod Files",
            f"Permanently delete '{info.name}'?\n\n"
            f"  {info.path}\n\n"
            f"This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)

        if reply != QMessageBox.StandardButton.Yes:
            return

        _s = AppSettings.instance()

        workshop_id   = info.workshop_id or info.path.name
        onyx_mods_dir = Path(_s.data_root) / 'mods' if _s.data_root else None
        game_mods_dir = (Path(_s.rimworld_exe).parent / 'Mods'
                         if _s.rimworld_exe else None)

        if onyx_mods_dir:
            result = delete_mod_permanently(
                workshop_id=workshop_id,
                onyx_mods_dir=onyx_mods_dir,
                game_mods_dir=game_mods_dir or Path(),
                steamcmd_path=_s.steamcmd_path)
            if result['errors']:
                QMessageBox.warning(
                    self, "Delete",
                    "Deleted with warnings:\n" +
                    "\n".join(result['errors']))
        else:
            try:
                shutil.rmtree(str(info.path))
            except OSError as e:  # pylint: disable=broad-exception-caught
                QMessageBox.critical(self, "Delete Failed", str(e))
                return

        for i in range(self.mod_list.count()):
            if (self.mod_list.item(i) and
                    self.mod_list.item(i).data(
                        Qt.ItemDataRole.UserRole) == mid):
                self.mod_list.takeItem(i)
                break

        self.all_mods.pop(mid, None)
        if self.rw:
            self.all_mods = self.rw.get_installed_mods(force_rescan=True,
                                                        max_age_seconds=0)

        visible = sum(
            1 for i in range(self.mod_list.count())
            if not self.mod_list.item(i).isHidden())
        self.count_label.setText(f"{visible} mods available in library")

        QMessageBox.information(
            self, "Deleted", f"'{info.name}' was deleted.")

    def _redownload_mod(self, mid: str):
        info = self.all_mods.get(mid)
        if not info or not info.workshop_id:
            QMessageBox.warning(
                self, "Redownload",
                "This mod has no Workshop ID — cannot redownload.")
            return

        _s            = AppSettings.instance()
        steamcmd_path = _s.steamcmd_path
        data_root     = _s.data_root

        if not steamcmd_path or not Path(steamcmd_path).exists():
            QMessageBox.warning(
                self, "SteamCMD Not Configured",
                "Set the SteamCMD path in Settings to redownload mods.")
            return
        if not data_root:
            QMessageBox.warning(self, "Error", "Data root not configured.")
            return

        from app.ui.modeditor.download_dialog import DownloadProgressDialog  # pylint: disable=import-outside-toplevel

        queue = DownloadQueue(
            steamcmd_path=steamcmd_path,
            destination=str(Path(data_root) / 'mods'),
            max_concurrent=1,
            username=_s.steamcmd_username)

        dlg = DownloadProgressDialog(
            self, queue, [(info.workshop_id, info.name)])
        dlg.setWindowTitle(f"Redownloading — {info.name}")
        dlg.downloads_complete.connect(
            lambda results: self._on_redownload_done(results, info.name))
        dlg.exec()

    def _on_redownload_done(self, results: list, mod_name: str):
        ok = sum(1 for _, s, _ in results if s)
        if ok:
            QMessageBox.information(
                self, "Redownload Complete",
                f"'{mod_name}' was redownloaded successfully.")
            if self.rw:
                self.all_mods = self.rw.get_installed_mods(force_rescan=True,
                                                            max_age_seconds=0)
                self._load()
        else:
            msg = results[0][2] if results else "Unknown error"
            QMessageBox.warning(
                self, "Redownload Failed",
                f"Failed to redownload '{mod_name}':\n{msg}")
