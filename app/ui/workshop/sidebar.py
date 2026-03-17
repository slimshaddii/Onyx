"""Download sidebar — shows active downloads and downloaded mods list."""

from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor

from app.core.steam_integration import open_workshop_page


class DownloadSidebar(QWidget):
    delete_mod = pyqtSignal(str, str)  # workshop_id, "delete"|"redownload"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)
        self.setStyleSheet("background:#0d0d18; border-right:1px solid #252540;")

        lo = QVBoxLayout(self)
        lo.setContentsMargins(6, 6, 6, 6)
        lo.setSpacing(4)

        # Downloads
        lo.addWidget(self._header("Downloads"))
        self.dl_list = QListWidget()
        self.dl_list.setObjectName("workshopList")
        self.dl_list.setMaximumHeight(140)
        self.dl_list.setStyleSheet("font-size:10px;")
        lo.addWidget(self.dl_list)

        # Downloaded mods
        lo.addWidget(self._header("Downloaded Mods"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter…")
        self.search.textChanged.connect(self._filter)
        lo.addWidget(self.search)

        self.mod_list = QListWidget()
        self.mod_list.setObjectName("workshopList")
        self.mod_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.mod_list.customContextMenuRequested.connect(self._menu)
        self.mod_list.setStyleSheet("font-size:11px;")
        lo.addWidget(self.mod_list, 1)

        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("font-size:10px;color:#555;")
        lo.addWidget(self.count_lbl)

    @staticmethod
    def _header(text):
        l = QLabel(f"<b style='color:#7c8aff;font-size:11px;'>{text}</b>")
        return l

    # ── Download tracking ────────────────────────────────────────

    def add_download(self, wid: str, title: str):
        it = QListWidgetItem(f"⬇ {title}")
        it.setData(Qt.ItemDataRole.UserRole, wid)
        it.setForeground(QColor('#64b5f6'))
        self.dl_list.addItem(it)

    def update_progress(self, wid: str, pct: int):
        for i in range(self.dl_list.count()):
            it = self.dl_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == wid:
                base = it.text().split('—')[-1].strip() if '—' in it.text() else it.text()[2:]
                it.setText(f"⬇ {pct}% — {base}")
                break

    def finish_download(self, wid: str, ok: bool, title: str = ''):
        for i in range(self.dl_list.count()):
            it = self.dl_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == wid:
                it.setText(f"{'✅' if ok else '❌'} {title or wid}")
                it.setForeground(QColor('#4CAF50' if ok else '#f44336'))
                idx = i
                QTimer.singleShot(5000, lambda: self._remove_dl(idx))
                break

    def _remove_dl(self, idx):
        if idx < self.dl_list.count():
            self.dl_list.takeItem(idx)

    # ── Mod list ─────────────────────────────────────────────────

    def refresh_mods(self, onyx_mods_dir: Path):
        self.mod_list.clear()
        if not onyx_mods_dir.exists():
            self.count_lbl.setText("0 mods")
            return

        from app.core.rimworld import ModInfo
        n = 0
        for d in sorted(onyx_mods_dir.iterdir()):
            if not d.is_dir():
                continue
            info = ModInfo.from_path(d, 'workshop')
            name = info.name if info else d.name
            wid = info.workshop_id if info else d.name

            it = QListWidgetItem(f"📦 {name}")
            it.setData(Qt.ItemDataRole.UserRole, wid)
            it.setData(Qt.ItemDataRole.UserRole + 1, str(d))
            it.setData(Qt.ItemDataRole.UserRole + 2, name)
            it.setToolTip(f"{name}\nID: {wid}\n{d}")
            self.mod_list.addItem(it)
            n += 1
        self.count_lbl.setText(f"{n} mod{'s' if n != 1 else ''}")

    def _filter(self):
        q = self.search.text().lower()
        for i in range(self.mod_list.count()):
            self.mod_list.item(i).setHidden(q not in self.mod_list.item(i).text().lower())

    def _menu(self, pos):
        it = self.mod_list.itemAt(pos)
        if not it:
            return
        wid = it.data(Qt.ItemDataRole.UserRole)
        path = it.data(Qt.ItemDataRole.UserRole + 1)

        m = QMenu(self)
        m.addAction("Open Folder", lambda: self._open(path))
        m.addAction("Workshop Page", lambda: open_workshop_page(wid))
        m.addSeparator()
        m.addAction("Redownload", lambda: self.delete_mod.emit(wid, "redownload"))
        m.addAction("Delete", lambda: self.delete_mod.emit(wid, "delete"))
        m.exec(self.mod_list.mapToGlobal(pos))

    @staticmethod
    def _open(path):
        import os, subprocess
        if os.name == 'nt':
            subprocess.Popen(['explorer', path])
        else:
            subprocess.Popen(['xdg-open', path])