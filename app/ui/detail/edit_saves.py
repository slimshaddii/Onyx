"""
Saves tab widget for the Edit Instance dialog.

Shows save files with mod inspection, compatibility
badges, download-missing, load-modlist-from-save,
and added-mod detection.
"""

from datetime import datetime
from pathlib import Path

from PyQt6.QtGui import QColor  # pylint: disable=no-name-in-module
from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QSplitter, QMessageBox, QInputDialog,
    QLineEdit,
)
from PyQt6.QtCore import (  # pylint: disable=no-name-in-module
    Qt, pyqtSignal,
)

from app.core.app_settings import AppSettings
from app.core.instance import Instance
from app.core.modlist import write_mods_config
from app.core.paths import mods_dir
from app.core.rimworld import RimWorldDetector
from app.core.save_parser import (
    parse_save_header, compare_save_mods,
    SaveHeader,
)
from app.core.steamcmd import DownloadQueue
from app.ui.detail.save_compat import (
    COMPAT_ICON, COMPAT_LABEL, compat_style,
)
from app.ui.styles import get_colors
from app.utils.file_utils import human_size


# ── Status Constants ─────────────────────────────

_STATUS_ACTIVE = 'active'
_STATUS_INACTIVE = 'inactive'
_STATUS_MISSING = 'missing'
_STATUS_ADDED = 'added'

_STATUS_PREFIX = {
    _STATUS_ACTIVE:   '✅',
    _STATUS_INACTIVE: '📦',
    _STATUS_MISSING:  '❌',
    _STATUS_ADDED:    '➕',
}

_FILTER_ALL = 'all'


# ── EditSavesTab ─────────────────────────────────

class EditSavesTab(QWidget):
    """Saves tab for InstanceEditDialog."""

    instance_changed = pyqtSignal()

    def __init__(self, parent, inst: Instance,
                 rw: RimWorldDetector | None):
        super().__init__(parent)
        self.inst = inst
        self.rw = rw

        self.saves_list: (
            QListWidget | None) = None
        self._save_files: list | None = None
        self._save_mods_list: (
            QListWidget | None) = None
        self._save_compat_lbl: (
            QLabel | None) = None
        self._save_info_lbl: (
            QLabel | None) = None
        self._download_missing_btn: (
            QPushButton | None) = None
        self._deactivate_added_btn: (
            QPushButton | None) = None
        self._load_modlist_btn: (
            QPushButton | None) = None
        self._mod_search: (
            QLineEdit | None) = None
        self._filter_btns: (
            dict[str, QPushButton]) = {}
        self._active_filter: str = _FILTER_ALL
        self._current_header: (
            SaveHeader | None) = None
        self._mod_items: (
            list[tuple[
                QListWidgetItem, str]] | None
            ) = None

        self._save_files = inst.get_save_files()
        self._build()

    def refresh(self):
        """Re-evaluate the currently selected save
        after external changes."""
        row = self.saves_list.currentRow()
        if row >= 0:
            self._on_save_selected(row)

    # ── Build ────────────────────────────────────

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(4)

        sp = QSplitter(
            Qt.Orientation.Vertical)
        sp.addWidget(self._build_list_panel())
        sp.addWidget(self._build_detail_panel())
        sp.setSizes([240, 320])
        lo.addWidget(sp)

        self.saves_list.currentRowChanged \
            .connect(self._on_save_selected)

    def _build_list_panel(self) -> QWidget:
        w = QWidget()
        lo = QVBoxLayout(w)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(4)

        self.saves_list = QListWidget()
        self._populate_saves_list()

        if not self.saves_list.count():
            lo.addWidget(
                QLabel("No saves yet."))
        lo.addWidget(self.saves_list)

        btns = QHBoxLayout()
        open_btn = QPushButton(
            "Open Saves Folder")
        open_btn.clicked.connect(
            self._open_saves_folder)
        btns.addWidget(open_btn)
        ren_btn = QPushButton("Rename")
        ren_btn.clicked.connect(
            self._rename_selected_save)
        btns.addWidget(ren_btn)
        del_btn = QPushButton("Delete")
        del_btn.setObjectName("dangerButton")
        del_btn.clicked.connect(
            self._delete_selected_save)
        btns.addWidget(del_btn)
        btns.addStretch()
        lo.addLayout(btns)
        return w

    def _build_detail_panel(self) -> QWidget:
        c = get_colors(
            AppSettings.instance().theme)
        w = QWidget()
        lo = QVBoxLayout(w)
        lo.setContentsMargins(4, 4, 4, 4)
        lo.setSpacing(4)

        # -- Header row
        hdr = QHBoxLayout()
        self._save_compat_lbl = QLabel("")
        self._save_compat_lbl.setStyleSheet(
            f"color:{c['text_dim']};"
            f"font-size:11px;")
        hdr.addWidget(self._save_compat_lbl)
        hdr.addStretch()
        self._save_info_lbl = QLabel(
            "Select a save to view its mods")
        self._save_info_lbl.setStyleSheet(
            f"color:{c['text_dim']};"
            f"font-size:10px;")
        hdr.addWidget(self._save_info_lbl)
        lo.addLayout(hdr)

        # -- Search + filters
        sf_row = QHBoxLayout()
        sf_row.setSpacing(4)
        self._mod_search = QLineEdit()
        self._mod_search.setPlaceholderText(
            "🔍 Search mods…")
        self._mod_search.setFixedHeight(24)
        self._mod_search.textChanged.connect(
            self._apply_filters)
        sf_row.addWidget(self._mod_search, 1)

        for key, label in [
            (_FILTER_ALL, "All"),
            (_STATUS_ACTIVE, "✅ Active"),
            (_STATUS_INACTIVE, "📦 Inactive"),
            (_STATUS_MISSING, "❌ Missing"),
            (_STATUS_ADDED, "➕ Added"),
        ]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == _FILTER_ALL)
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                "font-size:10px;"
                "padding:1px 6px;")
            btn.clicked.connect(
                lambda _, k=key:
                    self._set_filter(k))
            self._filter_btns[key] = btn
            sf_row.addWidget(btn)
        lo.addLayout(sf_row)

        # -- Mod list
        self._save_mods_list = QListWidget()
        self._save_mods_list.setStyleSheet(
            "font-size:11px;")
        lo.addWidget(self._save_mods_list, 1)

        # -- Action buttons
        btn_row = QHBoxLayout()
        self._download_missing_btn = QPushButton(
            "⬇ Download Missing")
        self._download_missing_btn.setEnabled(
            False)
        self._download_missing_btn.setToolTip(
            "Download mods from this save "
            "that are not installed")
        self._download_missing_btn.clicked \
            .connect(self._download_missing_mods)
        btn_row.addWidget(
            self._download_missing_btn)

        self._deactivate_added_btn = QPushButton(
            "🚫 Deactivate Added")
        self._deactivate_added_btn.setEnabled(
            False)
        self._deactivate_added_btn.setToolTip(
            "Deactivate mods active in this "
            "instance but not in this save")
        self._deactivate_added_btn.clicked \
            .connect(self._deactivate_added_mods)
        btn_row.addWidget(
            self._deactivate_added_btn)

        self._load_modlist_btn = QPushButton(
            "📋 Load Modlist from Save")
        self._load_modlist_btn.setEnabled(False)
        self._load_modlist_btn.setToolTip(
            "Replace this instance's active "
            "modlist with the save's mod order")
        self._load_modlist_btn.clicked.connect(
            self._load_modlist_from_save)
        btn_row.addWidget(
            self._load_modlist_btn)
        btn_row.addStretch()
        lo.addLayout(btn_row)
        return w

    # ── Save List ────────────────────────────────

    def _populate_saves_list(self):
        self.saves_list.clear()
        for s in self._save_files:
            try:
                dt = datetime.fromisoformat(
                    s['modified']).strftime(
                        "%b %d %H:%M")
            except ValueError:
                dt = s['modified'][:16]
            self.saves_list.addItem(
                f"📄 {s['name']}  —  "
                f"{human_size(s['size'])}"
                f"  —  {dt}")

    # ── Save Selection ───────────────────────────

    def _on_save_selected(self, row: int):
        """Parse and display the mod list for the
        selected save, including added mods."""
        c = get_colors(
            AppSettings.instance().theme)

        self._save_mods_list.clear()
        self._current_header = None
        self._mod_items = None
        self._download_missing_btn.setEnabled(
            False)
        self._deactivate_added_btn.setEnabled(
            False)
        self._deactivate_added_btn.setText(
            "🚫 Deactivate Added")
        self._load_modlist_btn.setEnabled(False)
        self._mod_search.clear()
        self._set_filter(_FILTER_ALL)

        if (row < 0
                or row >= len(self._save_files)):
            self._save_compat_lbl.setText("")
            self._save_info_lbl.setText(
                "Select a save to view its mods")
            return

        s = self._save_files[row]
        header = parse_save_header(
            Path(s['path']))

        if header is None:
            self._save_compat_lbl.setText(
                "❓ Could not read save")
            self._save_info_lbl.setText("")
            return

        self._current_header = header

        installed = (
            self.rw.get_installed_mods()
            if self.rw else {})
        installed_ids = set(installed.keys())
        active_set = {
            m.lower() for m in self.inst.mods}
        save_set = {
            m.lower() for m in header.mod_ids}

        compat = compare_save_mods(
            header, list(self.inst.mods),
            installed_ids)
        self._save_compat_lbl.setText(
            f"{COMPAT_ICON[compat]}"
            f" {COMPAT_LABEL[compat]}")
        self._save_compat_lbl.setStyleSheet(
            compat_style(compat))

        missing_count = 0
        inactive_count = 0
        self._mod_items = []

        for i, mid in enumerate(header.mod_ids):
            mid_lower = mid.lower()
            name = (
                header.mod_names[i]
                if i < len(header.mod_names)
                else mid)
            on_disk = mid_lower in installed_ids
            active = mid_lower in active_set

            if on_disk and active:
                status = _STATUS_ACTIVE
            elif on_disk:
                status = _STATUS_INACTIVE
                inactive_count += 1
            else:
                status = _STATUS_MISSING
                missing_count += 1

            prefix = _STATUS_PREFIX[status]
            text = (
                f"{prefix}  {name}  [{mid}]")
            item = QListWidgetItem(text)

            if status == _STATUS_MISSING:
                item.setForeground(
                    QColor(c['error']))
            elif status == _STATUS_INACTIVE:
                item.setForeground(
                    QColor(c['warning']))

            item.setData(
                Qt.ItemDataRole.UserRole,
                mid_lower)
            self._save_mods_list.addItem(item)
            self._mod_items.append(
                (item, status))

        # -- Added mods (active but not in save)
        added_count = 0
        for mid in self.inst.mods:
            mid_lower = mid.lower()
            if mid_lower in save_set:
                continue
            info = installed.get(mid_lower)
            name = info.name if info else mid
            prefix = _STATUS_PREFIX[_STATUS_ADDED]
            text = (
                f"{prefix}  {name}  [{mid}]")
            item = QListWidgetItem(text)
            item.setForeground(
                QColor(c['accent']))
            item.setData(
                Qt.ItemDataRole.UserRole,
                mid_lower)
            self._save_mods_list.addItem(item)
            self._mod_items.append(
                (item, _STATUS_ADDED))
            added_count += 1

        mod_count = len(header.mod_ids)
        active_count = (
            mod_count - missing_count
            - inactive_count)

        parts = [
            f"{mod_count} save mods",
            f"{active_count} active",
            f"{inactive_count} inactive",
            f"{missing_count} missing",
            f"{added_count} added",
        ]
        self._save_info_lbl.setText(
            "  •  ".join(parts))

        self._download_missing_btn.setEnabled(
            missing_count > 0)
        self._load_modlist_btn.setEnabled(
            mod_count > 0)

        if added_count:
            self._deactivate_added_btn.setText(
                f"🚫 Deactivate"
                f" {added_count} Added")
            self._deactivate_added_btn.setEnabled(
                True)

        self._update_filter_labels(
            mod_count, active_count,
            inactive_count, missing_count,
            added_count)

    # ── Search / Filter ──────────────────────────

    def _set_filter(self, key: str):
        self._active_filter = key
        c = get_colors(
            AppSettings.instance().theme)
        for k, btn in self._filter_btns.items():
            if k == key:
                btn.setChecked(True)
                btn.setStyleSheet(
                    f"font-size:10px;"
                    f"padding:1px 6px;"
                    f"background:{c['accent']};"
                    f"color:{c['bg']};"
                    f"font-weight:bold;")
            else:
                btn.setChecked(False)
                btn.setStyleSheet(
                    "font-size:10px;"
                    "padding:1px 6px;")
        self._apply_filters()

    def _update_filter_labels(
            self, total: int, active: int,
            inactive: int, missing: int,
            added: int):
        labels = {
            _FILTER_ALL: (
                f"All ({total + added})"),
            _STATUS_ACTIVE: (
                f"✅ Active ({active})"),
            _STATUS_INACTIVE: (
                f"📦 Inactive ({inactive})"),
            _STATUS_MISSING: (
                f"❌ Missing ({missing})"),
            _STATUS_ADDED: (
                f"➕ Added ({added})"),
        }
        for key, btn in self._filter_btns.items():
            btn.setText(labels.get(key, key))

    def _apply_filters(self, _text=None):
        if self._mod_items is None:
            return
        query = self._mod_search.text().lower()
        filt = self._active_filter

        for item, status in self._mod_items:
            text_match = (
                not query
                or query in item.text().lower())
            status_match = (
                filt == _FILTER_ALL
                or filt == status)
            item.setHidden(
                not (text_match
                     and status_match))

    # ── Deactivate Added ─────────────────────────

    def _deactivate_added_mods(self):
        """Deactivate mods active in the instance
        but not present in the selected save."""
        if self._current_header is None:
            return

        save_set = {
            m.lower()
            for m in self._current_header.mod_ids}
        added = [
            mid for mid in self.inst.mods
            if mid.lower() not in save_set]

        if not added:
            QMessageBox.information(
                self, "No Added Mods",
                "No mods to deactivate.")
            return

        installed = (
            self.rw.get_installed_mods()
            if self.rw else {})
        names = []
        for mid in added[:10]:
            info = installed.get(mid.lower())
            names.append(
                info.name if info else mid)

        msg = (
            f"Deactivate {len(added)} mod(s) "
            f"not in this save?\n\n"
            + "\n".join(
                f"  • {n}" for n in names)
            + ("\n  …"
               if len(added) > 10 else "")
            + "\n\nThey will be moved to "
              "inactive.")

        if QMessageBox.question(
            self, "Deactivate Added Mods", msg,
            (QMessageBox.StandardButton.Yes
             | QMessageBox.StandardButton.No),
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        added_set = set(added)
        new_mods = [
            m for m in self.inst.mods
            if m not in added_set]
        new_inactive = list(
            self.inst.inactive_mods)
        for mid in added:
            if mid not in new_inactive:
                new_inactive.append(mid)

        self.inst.mods = new_mods
        self.inst.inactive_mods = new_inactive
        self.inst.save()
        self._write_mods_config()
        self.instance_changed.emit()
        self.refresh()

    # ── Download Missing ─────────────────────────

    def _extra_mod_paths(self) -> list[str]:
        _s = AppSettings.instance()
        paths: list[str] = []
        if _s.data_root:
            paths.append(
                str(mods_dir(
                    Path(_s.data_root))))
        if _s.steam_workshop_path:
            paths.append(
                _s.steam_workshop_path)
        return paths

    def _download_missing_mods(self):
        """Download mods from this save that are
        not installed on disk."""
        if self._current_header is None:
            return

        installed = (
            self.rw.get_installed_mods()
            if self.rw else {})
        installed_ids = set(installed.keys())

        missing = [
            mid for mid
            in self._current_header.mod_ids
            if mid.lower() not in installed_ids]

        if not missing:
            QMessageBox.information(
                self, "No Missing Mods",
                "All mods from this save are "
                "already installed.")
            return

        ws_map = self.inst.mod_workshop_ids
        name_map = self._build_name_map()

        downloadable: list[tuple[str, str]] = []
        no_wid: list[str] = []

        for mid in missing:
            mid_lower = mid.lower()
            wid = (ws_map.get(mid_lower, '')
                   or ws_map.get(mid, ''))
            name = name_map.get(mid_lower, mid)
            if wid:
                downloadable.append((wid, name))
            else:
                no_wid.append(name)

        if not downloadable and no_wid:
            QMessageBox.warning(
                self, "Cannot Download",
                self._fmt_no_wid_msg(no_wid))
            return

        msg = (
            f"{len(downloadable)} mod(s) can "
            f"be downloaded.")
        if no_wid:
            msg += (
                f"\n\n{len(no_wid)} mod(s) "
                f"have no Workshop ID:\n"
                + "\n".join(
                    f"  • {n}"
                    for n in no_wid[:10])
                + ("\n  …"
                   if len(no_wid) > 10
                   else ""))
        msg += (
            f"\n\nDownload {len(downloadable)}"
            f" mod(s) now?")

        if QMessageBox.question(
            self, "Download Missing Mods", msg,
            (QMessageBox.StandardButton.Yes
             | QMessageBox.StandardButton.No),
            QMessageBox.StandardButton.Yes,
        ) != QMessageBox.StandardButton.Yes:
            return

        _s = AppSettings.instance()
        if (not _s.steamcmd_path
                or not Path(
                    _s.steamcmd_path).exists()):
            QMessageBox.warning(
                self, "SteamCMD Not Configured",
                "Set the SteamCMD path in "
                "Settings to download mods.")
            return
        if not _s.data_root:
            QMessageBox.warning(
                self, "Error",
                "Data root not configured.")
            return

        from app.ui.modeditor.download_manager import DownloadManagerWindow  # pylint: disable=import-outside-toplevel

        _queue = DownloadQueue(
            steamcmd_path=_s.steamcmd_path,
            destination=str(
                Path(_s.data_root) / 'mods'),
            max_concurrent=2,
            username=_s.steamcmd_username)
        _mgr = DownloadManagerWindow(
            _queue, self)
        _mgr.queue_and_show(downloadable)
        _queue.queue_empty.connect(
            self._on_missing_download_done)

    def _on_missing_download_done(self):
        if self.rw:
            self.rw.get_installed_mods(
                extra_mod_paths=(
                    self._extra_mod_paths()),
                force_rescan=True,
                max_age_seconds=0)
        self.refresh()
        QMessageBox.information(
            self, "Downloads Complete",
            "Missing mods downloaded. "
            "View refreshed.")

    # ── Load Modlist from Save ───────────────────

    def _load_modlist_from_save(self):
        """Replace this instance's active modlist
        with the save's mod order."""
        if self._current_header is None:
            return

        save_mods = [
            m.lower().strip()
            for m in self._current_header.mod_ids
            if m.strip()]

        if not save_mods:
            QMessageBox.information(
                self, "Empty Modlist",
                "This save has no mods.")
            return

        installed = (
            self.rw.get_installed_mods()
            if self.rw else {})
        installed_ids = set(installed.keys())
        name_map = self._build_name_map()
        save_name = (
            self._current_header.save_name)

        present = [
            m for m in save_mods
            if m in installed_ids]
        missing = [
            m for m in save_mods
            if m not in installed_ids]

        if missing:
            names = [
                name_map.get(m, m)
                for m in missing[:20]]
            msg = (
                f"{len(missing)} mod(s) from "
                f"'{save_name}' are not "
                f"installed:\n\n"
                + "\n".join(
                    f"  • {n}" for n in names)
                + ("\n  …"
                   if len(missing) > 20
                   else "")
                + f"\n\nLoad the {len(present)}"
                  f" installed mods anyway?")
            if QMessageBox.question(
                self, "Missing Mods", msg,
                (QMessageBox.StandardButton.Yes
                 | QMessageBox
                 .StandardButton.No),
                QMessageBox.StandardButton.No,
            ) != (
                    QMessageBox
                    .StandardButton.Yes):
                return
        else:
            if QMessageBox.question(
                self, "Load Modlist",
                f"Replace active modlist with "
                f"{len(present)} mods from "
                f"'{save_name}'?",
                (QMessageBox.StandardButton.Yes
                 | QMessageBox
                 .StandardButton.No),
                QMessageBox.StandardButton.No,
            ) != (
                    QMessageBox
                    .StandardButton.Yes):
                return

        new_active_set = set(present)
        to_deactivate = (
            set(self.inst.mods)
            - new_active_set)

        new_inactive = [
            m for m in self.inst.inactive_mods
            if m not in new_active_set]
        for mid in to_deactivate:
            if mid not in new_inactive:
                new_inactive.append(mid)

        self.inst.mods = present
        self.inst.inactive_mods = new_inactive
        self.inst.save()
        self._write_mods_config()
        self.instance_changed.emit()
        self.refresh()

        QMessageBox.information(
            self, "Modlist Loaded",
            f"Loaded {len(present)} mods from "
            f"'{save_name}'."
            + (f"\n{len(missing)} unavailable"
               f" mod(s) skipped."
               if missing else "")
            + "\n\nOpen the Mod Editor to "
              "sort and review.")

    # ── Rename / Delete ──────────────────────────

    def _rename_selected_save(self):
        """Rename the currently selected save."""
        row = self.saves_list.currentRow()
        if (row < 0
                or row >= len(self._save_files)):
            QMessageBox.information(
                self, "Rename Save",
                "Select a save to rename.")
            return
        s = self._save_files[row]
        old_path = Path(s['path'])
        new_name, ok = QInputDialog.getText(
            self, "Rename Save",
            "New name:", text=s['name'])
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        if new_name == s['name']:
            return
        new_path = (
            old_path.parent
            / f"{new_name}.rws")
        if new_path.exists():
            QMessageBox.warning(
                self, "Rename Save",
                f"'{new_name}' already exists.")
            return
        try:
            old_path.rename(new_path)
            self._save_files[row][
                'name'] = new_name
            self._save_files[row][
                'path'] = str(new_path)
            self._populate_saves_list()
            self.saves_list.setCurrentRow(row)
        except OSError as e:
            QMessageBox.critical(
                self, "Rename Failed", str(e))

    def _delete_selected_save(self):
        """Delete the currently selected save."""
        row = self.saves_list.currentRow()
        if (row < 0
                or row >= len(self._save_files)):
            QMessageBox.information(
                self, "Delete Save",
                "Select a save to delete.")
            return
        s = self._save_files[row]
        if QMessageBox.question(
            self, "Delete Save",
            f"Delete '{s['name']}'?\n\n"
            f"This cannot be undone.",
            (QMessageBox.StandardButton.Yes
             | QMessageBox.StandardButton.No),
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            Path(s['path']).unlink()
            self.saves_list.takeItem(row)
            self._save_files.pop(row)
        except OSError as e:
            QMessageBox.critical(
                self, "Delete Failed", str(e))

    def _open_saves_folder(self):
        """Open the saves directory."""
        import os  # pylint: disable=import-outside-toplevel
        import subprocess  # pylint: disable=import-outside-toplevel
        path = self.inst.saves_dir
        path.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            subprocess.Popen(
                ['explorer', str(path)])
        else:
            subprocess.Popen(
                ['xdg-open', str(path)])

    # ── Helpers ──────────────────────────────────

    def _write_mods_config(self):
        """Sync ModsConfig.xml with inst.mods."""
        write_mods_config(
            self.inst.config_dir,
            self.inst.mods,
            version=(
                self.inst.rimworld_version
                or '1.6.4630 rev467'))

    def _build_name_map(self) -> dict[str, str]:
        if self._current_header is None:
            return {}
        nm: dict[str, str] = {}
        for i, mid in enumerate(
                self._current_header.mod_ids):
            if i < len(
                    self._current_header
                    .mod_names):
                nm[mid.lower()] = (
                    self._current_header
                    .mod_names[i])
        return nm

    @staticmethod
    def _fmt_no_wid_msg(
            no_wid: list[str]) -> str:
        """Format message for mods without
        Workshop IDs."""
        return (
            f"{len(no_wid)} missing mod(s) "
            f"have no Workshop ID:\n\n"
            + "\n".join(
                f"  • {n}"
                for n in no_wid[:20])
            + ("\n  …"
               if len(no_wid) > 20 else "")
            + "\n\nDownload manually from "
              "the Workshop browser.")
