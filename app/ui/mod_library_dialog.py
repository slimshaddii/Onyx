"""
Mod Library dialog — browse, manage, and delete downloaded mods.
Full detail panel: preview image, description, mod info.
Filters: Latest, Has Update, Last Updated, Name.
"""

import os
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QSplitter, QWidget, QGroupBox, QGridLayout, QComboBox,
    QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer  # pylint: disable=no-name-in-module
from PyQt6.QtGui import QPixmap, QColor  # pylint: disable=no-name-in-module

from app.core.app_settings import AppSettings
from app.core.mod_update_checker import ModTimestampStore, check_updates
from app.core.rimworld import ModInfo
from app.core.steam_integration import open_workshop_page
from app.ui.styles import get_colors
from app.utils.file_utils import get_folder_size, human_size


class ModLibraryDialog(QDialog):
    """Browse, manage, and delete mods in the Onyx mods directory."""

    mod_deleted    = pyqtSignal(str)
    mod_redownload = pyqtSignal(str, str)

    def __init__(self, parent, onyx_mods_dir: Path,
                 download_manager=None):
        super().__init__(parent)
        self.mods_dir         = onyx_mods_dir
        self.download_manager = download_manager

        self._mods: list[
            tuple[str, str, Path, ModInfo | None, float]
        ] = []
        self._has_updates: set[str] = set()

        self._search:      QLineEdit | None  = None
        self._sort_cb:     QComboBox | None   = None
        self._filter_cb:   QComboBox | None   = None
        self._count_lbl:   QLabel | None      = None
        self._list:        QListWidget | None = None
        self._preview_lbl: QLabel | None      = None
        self._detail:      dict[str, QLabel]  = {}
        self._desc_lbl:    QLabel | None      = None
        self._update_lbl:  QLabel | None      = None
        self._folder_btn:  QPushButton | None = None
        self._ws_btn:      QPushButton | None = None
        self._redl_btn:    QPushButton | None = None
        self._del_btn:     QPushButton | None = None

        self.setWindowTitle("Mod Library")
        self.setMinimumSize(900, 580)
        self.resize(1060, 640)
        self._build()
        self._load()
        self._check_updates_async()

    # ── UI construction ───────────────────────────────────────────────

    def _build(self):
        """Build the library dialog layout."""
        c  = get_colors(AppSettings.instance().theme)
        lo = QVBoxLayout(self)
        lo.setSpacing(6)

        top = self._build_toolbar()
        lo.addLayout(top)

        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(self._build_left_panel())
        sp.addWidget(self._build_right_panel(c))
        sp.setSizes([380, 580])
        lo.addWidget(sp, 1)

        btns = QHBoxLayout()
        btns.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        lo.addLayout(btns)

    def _build_toolbar(self) -> QHBoxLayout:
        """Build the search/sort/filter toolbar."""
        top = QHBoxLayout()
        top.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search mods…")
        self._search.setObjectName("searchBar")
        self._search.textChanged.connect(self._apply_filter)
        top.addWidget(self._search, 1)

        top.addWidget(QLabel("Sort:"))
        self._sort_cb = QComboBox()
        self._sort_cb.addItem("Name A-Z",     "name_asc")
        self._sort_cb.addItem("Name Z-A",     "name_desc")
        self._sort_cb.addItem("Last Updated", "mtime_desc")
        self._sort_cb.addItem("Oldest First", "mtime_asc")
        self._sort_cb.currentIndexChanged.connect(
            self._apply_filter)
        top.addWidget(self._sort_cb)

        top.addWidget(QLabel("Filter:"))
        self._filter_cb = QComboBox()
        self._filter_cb.addItem("All Mods",      "all")
        self._filter_cb.addItem("Has Update",    "update")
        self._filter_cb.addItem("Workshop Mods", "workshop")
        self._filter_cb.addItem("Local Mods",    "local")
        self._filter_cb.currentIndexChanged.connect(
            self._apply_filter)
        top.addWidget(self._filter_cb)

        self._count_lbl = QLabel("")
        self._count_lbl.setObjectName("subheading")
        top.addWidget(self._count_lbl)

        return top

    def _build_left_panel(self) -> QWidget:
        """Build the mod list panel."""
        left = QWidget()
        ll   = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        self._list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection)
        self._list.currentRowChanged.connect(self._on_select)
        self._list.itemSelectionChanged.connect(
            self._on_selection_changed)
        ll.addWidget(self._list, 1)
        return left

    def _build_right_panel(self, c: dict) -> QWidget:
        """Build the detail/preview panel."""
        right = QWidget()
        rl    = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)

        self._preview_lbl = QLabel()
        self._preview_lbl.setAlignment(
            Qt.AlignmentFlag.AlignCenter)
        self._preview_lbl.setMinimumHeight(120)
        self._preview_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding)
        self._preview_lbl.setStyleSheet(
            f"background:{c['bg_mid']}; border-radius:6px;")
        self._preview_lbl.setText("No preview")
        rl.addWidget(self._preview_lbl, 2)

        rl.addWidget(self._build_info_group(), 0)
        rl.addWidget(self._build_desc_group(), 1)

        self._update_lbl = QLabel("")
        self._update_lbl.setStyleSheet(
            f"color:{c['warning']}; font-weight:bold; "
            f"font-size:10px;")
        self._update_lbl.hide()
        rl.addWidget(self._update_lbl, 0)

        rl.addLayout(self._build_action_buttons(), 0)
        return right

    def _build_info_group(self) -> QGroupBox:
        """Build the Mod Info grid."""
        info_group = QGroupBox("Mod Info")
        ig = QGridLayout()
        ig.setVerticalSpacing(3)
        ig.setContentsMargins(6, 6, 6, 6)
        for row, key in enumerate(
                ('Name', 'Author', 'Version', 'Workshop ID',
                 'Source', 'Size', 'Last Updated', 'Path')):
            lbl = QLabel(f"{key}:")
            lbl.setStyleSheet(
                "font-weight:bold; font-size:10px;")
            lbl.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Preferred)
            val = QLabel("—")
            val.setWordWrap(True)
            val.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            val.setStyleSheet("font-size:10px;")
            ig.addWidget(lbl, row, 0)
            ig.addWidget(val, row, 1)
            self._detail[key] = val
        info_group.setLayout(ig)
        return info_group

    def _build_desc_group(self) -> QGroupBox:
        """Build the Description group with scroll area."""
        desc_group = QGroupBox("Description")
        desc_lo    = QVBoxLayout()
        desc_lo.setContentsMargins(6, 6, 6, 6)
        self._desc_lbl = QLabel("")
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._desc_lbl.setStyleSheet("font-size:10px;")
        self._desc_lbl.setAlignment(
            Qt.AlignmentFlag.AlignTop)
        self._desc_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding)
        desc_scroll = QScrollArea()
        desc_scroll.setWidgetResizable(True)
        desc_scroll.setWidget(self._desc_lbl)
        desc_scroll.setStyleSheet(
            "QScrollArea { border:none; }")
        desc_lo.addWidget(desc_scroll)
        desc_group.setLayout(desc_lo)
        return desc_group

    def _build_action_buttons(self) -> QHBoxLayout:
        """Build the action button row."""
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._folder_btn = QPushButton("Open Folder")
        self._folder_btn.clicked.connect(self._open_folder)
        self._folder_btn.setEnabled(False)
        btn_row.addWidget(self._folder_btn)

        self._ws_btn = QPushButton("Workshop Page")
        self._ws_btn.clicked.connect(self._open_ws)
        self._ws_btn.setEnabled(False)
        btn_row.addWidget(self._ws_btn)

        self._redl_btn = QPushButton("Redownload")
        self._redl_btn.clicked.connect(self._redownload)
        self._redl_btn.setEnabled(False)
        btn_row.addWidget(self._redl_btn)

        self._del_btn = QPushButton("Delete")
        self._del_btn.setObjectName("dangerButton")
        self._del_btn.clicked.connect(self._delete)
        self._del_btn.setEnabled(False)
        btn_row.addWidget(self._del_btn)

        return btn_row

    # ── Data loading ──────────────────────────────────────────────────

    def _load(self):
        """Scan the mods directory and populate the list."""
        self._mods.clear()
        self._list.clear()

        if not self.mods_dir.exists():
            self._count_lbl.setText("0 mods")
            return

        for d in sorted(self.mods_dir.iterdir()):
            if not d.is_dir():
                continue
            self._load_single_mod_dir(d)

        self._count_lbl.setText(
            f"{len(self._mods)} "
            f"mod{'s' if len(self._mods) != 1 else ''}")
        self._apply_filter()

    def _load_single_mod_dir(self, d: Path) -> None:
        """Process a single mod directory during load."""
        try:
            contents = list(d.iterdir())
        except OSError:
            return

        if not contents:
            try:
                d.rmdir()
            except OSError:
                pass
            return

        info = ModInfo.from_path(d, 'workshop')

        if info is None:
            has_meaningful = any(
                f.suffix.lower()
                in ('.xml', '.dll', '.png', '.jpg', '.txt')
                for f in d.rglob('*') if f.is_file())
            if not has_meaningful:
                try:
                    shutil.rmtree(str(d))
                except OSError:
                    pass
                return
            name = d.name
            wid  = d.name
        else:
            name = info.name
            wid  = info.workshop_id or d.name

        try:
            mtime = d.stat().st_mtime
        except OSError:
            mtime = 0.0

        self._mods.append((wid, name, d, info, mtime))
        it = QListWidgetItem(f"📦  {name}")
        it.setData(Qt.ItemDataRole.UserRole,
                   len(self._mods) - 1)
        self._list.addItem(it)

    # ── Update checking ───────────────────────────────────────────────

    def _check_updates_async(self):
        """Check for mod updates on a background thread."""
        dr = AppSettings.instance().data_root
        if not dr:
            return

        def _run():
            try:
                store = ModTimestampStore(Path(dr))
                ws_ids = [m[0] for m in self._mods
                          if m[0].isdigit()]
                names = {m[0]: m[1] for m in self._mods
                         if m[0].isdigit()}
                mod_paths = {m[0]: str(m[2])
                             for m in self._mods
                             if m[0].isdigit()}
                results = check_updates(
                    ws_ids, store, names, mod_paths)
                update_ids = {
                    r.workshop_id
                    for r in results if r.has_update}
                QTimer.singleShot(
                    0,
                    lambda ids=update_ids:
                        self._mark_updates(ids))
            except Exception:  # pylint: disable=broad-exception-caught
                # Background update check must not propagate.
                pass

        threading.Thread(target=_run, daemon=True).start()

    def _mark_updates(self, update_ids: set[str]):
        """Highlight mods that have updates available."""
        self._has_updates = update_ids
        c = get_colors(AppSettings.instance().theme)
        for i in range(self._list.count()):
            it  = self._list.item(i)
            idx = it.data(Qt.ItemDataRole.UserRole)
            if (idx is not None
                    and idx < len(self._mods)):
                wid = self._mods[idx][0]
                if wid in self._has_updates:
                    it.setForeground(QColor(c['warning']))
        self._apply_filter()

    # ── Filtering ─────────────────────────────────────────────────────

    def _apply_filter(self):
        """Rebuild the visible list based on search/sort/filter."""
        q          = self._search.text().lower()
        sort_key   = self._sort_cb.currentData()
        filter_key = self._filter_cb.currentData()

        visible = self._collect_visible(q, filter_key)
        self._sort_visible(visible, sort_key)

        c = get_colors(AppSettings.instance().theme)
        warning_color = QColor(c['warning'])

        self._list.setUpdatesEnabled(False)
        self._list.clear()
        for idx, wid, name, _path, _info, _mtime in visible:
            it = QListWidgetItem(f"📦  {name}")
            it.setData(Qt.ItemDataRole.UserRole, idx)
            if wid in self._has_updates:
                it.setForeground(warning_color)
            self._list.addItem(it)
        self._list.setUpdatesEnabled(True)

        update_count = sum(
            1 for e in visible if e[1] in self._has_updates)
        suffix = (
            f"  •  {update_count} "
            f"update{'s' if update_count != 1 else ''}"
            if update_count else '')
        self._count_lbl.setText(
            f"{len(visible)}/{len(self._mods)} mods{suffix}")

    def _collect_visible(self, query: str,
                         filter_key: str) -> list[tuple]:
        """Collect mods matching the current query and filter."""
        visible: list[tuple] = []
        for idx, (wid, name, path, info, mtime) in enumerate(
                self._mods):
            if query and query not in name.lower():
                continue
            if (filter_key == 'update'
                    and wid not in self._has_updates):
                continue
            if (filter_key == 'workshop'
                    and not (wid and wid.isdigit())):
                continue
            if (filter_key == 'local'
                    and (wid and wid.isdigit())):
                continue
            visible.append(
                (idx, wid, name, path, info, mtime))
        return visible

    @staticmethod
    def _sort_visible(visible: list[tuple],
                      sort_key: str) -> None:
        """Sort the visible list in place by the chosen key."""
        if sort_key == 'name_asc':
            visible.sort(key=lambda x: x[2].lower())
        elif sort_key == 'name_desc':
            visible.sort(
                key=lambda x: x[2].lower(), reverse=True)
        elif sort_key == 'mtime_desc':
            visible.sort(key=lambda x: x[5], reverse=True)
        elif sort_key == 'mtime_asc':
            visible.sort(key=lambda x: x[5])

    # ── Selection ─────────────────────────────────────────────────────

    def _on_select(self, row: int):
        """Show detail for the selected mod."""
        if row < 0 or row >= self._list.count():
            self._disable_action_buttons()
            self._update_lbl.hide()
            return

        it = self._list.item(row)
        if it is None:
            return
        idx = it.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._mods):
            return

        wid, name, path, info, mtime = self._mods[idx]

        self._show_preview(info)
        self._show_detail(wid, name, path, info, mtime)
        self._show_update_status(wid)
        self._enable_action_buttons(wid)

    def _disable_action_buttons(self):
        """Disable all action buttons."""
        for btn in (self._folder_btn, self._ws_btn,
                    self._redl_btn, self._del_btn):
            btn.setEnabled(False)

    def _show_preview(self, info: ModInfo | None):
        """Display the mod preview image or placeholder."""
        preview_path = (
            Path(info.preview_image)
            if info and info.preview_image else None)
        if preview_path and preview_path.exists():
            pm = QPixmap(str(preview_path))
            if not pm.isNull():
                w = max(
                    self._preview_lbl.width() - 4, 60)
                h = max(
                    self._preview_lbl.height() - 4, 80)
                self._preview_lbl.setPixmap(pm.scaled(
                    w, h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode
                    .SmoothTransformation))
            else:
                self._preview_lbl.clear()
                self._preview_lbl.setText("No preview")
        else:
            self._preview_lbl.clear()
            self._preview_lbl.setText("No preview")

    def _show_detail(self, wid: str, name: str,
                     path: Path, info: ModInfo | None,
                     mtime: float):
        """Populate the detail labels for a selected mod."""
        self._detail['Name'].setText(name)
        self._detail['Author'].setText(
            info.author if info and info.author else '—')
        self._detail['Version'].setText(
            ', '.join(info.supported_versions)
            if info and info.supported_versions else '—')
        self._detail['Workshop ID'].setText(wid or '—')
        self._detail['Source'].setText(
            info.source if info else '—')

        try:
            dt = datetime.fromtimestamp(mtime).strftime(
                "%b %d, %Y  %H:%M")
        except (ValueError, OSError):
            dt = '—'
        self._detail['Last Updated'].setText(dt)
        self._detail['Path'].setText(str(path))

        self._detail['Size'].setText('…')
        self._calc_size_async(path, self._detail['Size'])

        desc = (info.description[:500]
                if info and info.description else '')
        self._desc_lbl.setText(desc or 'No description.')

    def _calc_size_async(self, path: Path,
                         label: QLabel) -> None:
        """Calculate folder size on a background thread."""
        def _calc():
            try:
                text = human_size(get_folder_size(path))
            except Exception:  # pylint: disable=broad-exception-caught
                # Size calculation is best-effort.
                text = '—'
            QTimer.singleShot(
                0, lambda: label.setText(text))

        threading.Thread(
            target=_calc, daemon=True).start()

    def _show_update_status(self, wid: str):
        """Show or hide the update-available label."""
        if wid in self._has_updates:
            self._update_lbl.setText(
                "Update available on Workshop")
            self._update_lbl.show()
        else:
            self._update_lbl.hide()

    def _enable_action_buttons(self, wid: str):
        """Enable action buttons based on mod type."""
        self._folder_btn.setEnabled(True)
        self._ws_btn.setEnabled(
            bool(wid and wid.isdigit()))
        self._redl_btn.setEnabled(
            bool(wid and wid.isdigit()
                 and self.download_manager))
        self._del_btn.setEnabled(True)

    def _on_selection_changed(self):
        """Update button states based on selection count."""
        selected = self._list.selectedItems()
        count    = len(selected)

        if count == 0:
            self._disable_action_buttons()
            return

        if count == 1:
            return

        self._folder_btn.setEnabled(False)
        self._ws_btn.setEnabled(False)

        all_have_ws = all(
            self._mods[
                it.data(Qt.ItemDataRole.UserRole)][0]
            .isdigit()
            for it in selected
            if it.data(Qt.ItemDataRole.UserRole) is not None
            and it.data(Qt.ItemDataRole.UserRole)
            < len(self._mods))
        self._redl_btn.setEnabled(
            all_have_ws and self.download_manager is not None)
        self._del_btn.setEnabled(True)

        self._preview_lbl.clear()
        self._preview_lbl.setText(
            f"{count} mods selected")
        for _, val in self._detail.items():
            val.setText('—')
        self._desc_lbl.setText('')
        self._update_lbl.hide()

    # ── Actions ───────────────────────────────────────────────────────

    def _selected(self) -> tuple | None:
        """Return the currently selected mod tuple or None."""
        row = self._list.currentRow()
        if row < 0:
            return None
        it = self._list.item(row)
        if not it:
            return None
        idx = it.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._mods):
            return None
        return self._mods[idx]

    def _open_folder(self):
        """Open the selected mod's folder."""
        sel = self._selected()
        if not sel:
            return
        path = sel[2]
        if os.name == 'nt':
            subprocess.Popen(['explorer', str(path)])
        else:
            subprocess.Popen(['xdg-open', str(path)])

    def _open_ws(self):
        """Open the Workshop page for the selected mod."""
        sel = self._selected()
        if not sel:
            return
        open_workshop_page(sel[0])

    def _redownload(self):
        """Queue selected mods for redownload."""
        if not self.download_manager:
            return
        selected = self._list.selectedItems()
        if not selected:
            return

        pairs: list[tuple[str, str]] = []
        for it in selected:
            idx = it.data(Qt.ItemDataRole.UserRole)
            if idx is None or idx >= len(self._mods):
                continue
            wid, name, _, _, _ = self._mods[idx]
            if wid and wid.isdigit():
                pairs.append((wid, name))

        if pairs:
            self.download_manager.queue_and_show(pairs)

    def _delete(self):
        """Delete selected mods after confirmation."""
        selected = self._list.selectedItems()
        if not selected:
            return

        to_delete = self._collect_delete_targets(selected)
        if not to_delete:
            return

        if not self._confirm_delete(to_delete):
            return

        errors = self._execute_delete(to_delete)
        if errors:
            QMessageBox.warning(
                self, "Delete — Partial Failure",
                f"Failed to delete {len(errors)} mod(s):\n"
                + '\n'.join(errors[:5]))

        self._load()

    def _collect_delete_targets(
            self, selected: list) -> list[tuple]:
        """Build list of (wid, name, path) for deletion."""
        to_delete: list[tuple[str, str, Path]] = []
        for it in selected:
            idx = it.data(Qt.ItemDataRole.UserRole)
            if idx is None or idx >= len(self._mods):
                continue
            wid, name, path, _, _ = self._mods[idx]
            to_delete.append((wid, name, path))
        return to_delete

    def _confirm_delete(self,
                        to_delete: list[tuple]) -> bool:
        """Show confirmation dialog. Return True if confirmed."""
        if len(to_delete) == 1:
            msg = (f"Permanently delete "
                   f"'{to_delete[0][1]}'?\n\n"
                   f"{to_delete[0][2]}\n\nCannot undo.")
        else:
            names = '\n'.join(
                f"  • {n}" for _, n, _ in to_delete[:5])
            extra = (
                f"\n  ... and {len(to_delete) - 5} more"
                if len(to_delete) > 5 else '')
            msg = (f"Permanently delete "
                   f"{len(to_delete)} mods?\n\n"
                   f"{names}{extra}\n\nCannot undo.")

        return QMessageBox.question(
            self, "Delete Mods", msg,
            (QMessageBox.StandardButton.Yes
             | QMessageBox.StandardButton.No),
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def _execute_delete(self,
                        to_delete: list[tuple]) -> list[str]:
        """Delete mods and return list of error messages."""
        errors: list[str] = []
        dr = AppSettings.instance().data_root

        for wid, name, path in to_delete:
            try:
                shutil.rmtree(str(path))
                self.mod_deleted.emit(wid)
                try:
                    if dr:
                        ModTimestampStore(
                            Path(dr)).remove(wid)
                except Exception:  # pylint: disable=broad-exception-caught
                    # Timestamp cleanup is best-effort.
                    pass
            except OSError as e:
                errors.append(f"{name}: {e}")

        return errors

    def resizeEvent(self, e):  # pylint: disable=invalid-name
        """Reload preview at correct size on resize."""
        super().resizeEvent(e)
        row = self._list.currentRow()
        if row >= 0:
            QTimer.singleShot(
                0, lambda: self._on_select(row))
