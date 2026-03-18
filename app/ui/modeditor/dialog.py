"""Mod editor dialog — per-instance mod isolation."""

from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QMessageBox, QFileDialog, QSplitter, QWidget, QMenu,
    QListWidgetItem,
)
from PyQt6.QtCore import Qt

from app.core.instance import Instance
from app.core.rimworld import RimWorldDetector
from app.core.steamcmd import DownloadQueue
from app.core.modlist import (
    write_mods_config, read_mods_config, parse_rimsort_modlist,
    export_rimsort_modlist, get_vanilla_modlist, VANILLA_AND_DLCS,
)
from app.core.mod_sort import auto_sort_mods
from app.core.mod_linker import delete_downloaded_mod, sync_instance_mods
from app.core.dep_resolver import (
    analyze_modlist, get_downloadable_deps, get_activatable_deps,
)
from app.core.paths import settings_path
from app.utils.file_utils import load_json

from app.ui.modeditor.drag_list import DragDropList, COLOR_ROLE
from app.ui.modeditor.preview_panel import PreviewPanel
from app.ui.modeditor.item_builder import ItemBuilder
from app.ui.modeditor.issue_checker import (
    get_badges, count_issues, get_issue_mod_ids,
    format_issue_text, format_issue_color, check_load_order,
)

PROTECTED_MODS = {'ludeon.rimworld'}


class ModEditorDialog(ItemBuilder, QDialog):
    """
    Three-panel mod editor:
      Left   — inactive mods for this instance
      Centre — active mods (drag to reorder)
      Right  — preview (mod metadata + issue badges)
    """

    def __init__(self, parent, instance: Instance, rw: RimWorldDetector):
        QDialog.__init__(self, parent)
        self.inst     = instance
        self.rw       = rw
        self.all_mods = rw.get_installed_mods(force_rescan=True)
        self.names    = {pid: info.name for pid, info in self.all_mods.items()}

        self._filter_issues = False
        self._defer_updates = False

        # Mod IDs used in *any* instance — drives the [NEW] badge in avail panel
        self._known_mod_ids  = self._load_known_mod_ids()
        # Mods already saved to *this* instance — drives [NEW] badge in active panel
        self._original_mods: set[str] = set(instance.mods)

        self.setWindowTitle(f"Mods — {instance.name}")
        self.setMinimumSize(960, 520)
        self.resize(1040, 590)
        self._build_ui()
        self._load()

    # ─────────────────────────────────────────────────────────────────────────
    # Init helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _load_known_mod_ids(self) -> set[str]:
        """Return mod IDs that already exist in at least one instance."""
        s = load_json(settings_path(), {})
        data_root = s.get('data_root', '')
        if not data_root:
            return set()
        try:
            from app.core.mod_cache import ModCache
            from app.core.paths import instances_dir
            from app.core.instance_manager import InstanceManager
            cache = ModCache(Path(data_root))
            cache.update_from_scan(self.all_mods)
            im = InstanceManager(instances_dir(Path(data_root)))
            cache.update_instance_mods(im.scan_instances())
            return cache.get_instance_mod_ids()
        except Exception:
            return set()

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(6, 4, 6, 6)
        lo.setSpacing(4)

        # ── Header ────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel(f"<b>{self.inst.name}</b>"))
        self.cnt = QLabel("0")
        self.cnt.setStyleSheet(
            "color:#7c8aff;font-weight:bold;font-size:11px;")
        hdr.addWidget(self.cnt)
        self.issue_btn = QPushButton("✔ OK")
        self.issue_btn.setFlat(True)
        self.issue_btn.setStyleSheet(
            "font-size:11px;padding:0 6px;border:none;color:#4CAF50;")
        self.issue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.issue_btn.setToolTip("Click to show only mods with issues")
        self.issue_btn.clicked.connect(self._toggle_filter)
        hdr.addWidget(self.issue_btn)
        hdr.addStretch()
        lo.addLayout(hdr)

        # ── Three-panel splitter ───────────────────────────────────
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(self._build_avail_panel())
        sp.addWidget(self._build_active_panel())
        self.preview = PreviewPanel(self)
        sp.addWidget(self.preview)
        sp.setSizes([240, 320, 260])
        lo.addWidget(sp, 1)

        lo.addLayout(self._build_bottom_bar())

    def _build_avail_panel(self) -> QWidget:
        w  = QWidget()
        lo = QVBoxLayout(w)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(2)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("Instance Mods (inactive)"))
        hdr.addStretch()
        lib_btn = QPushButton("📚 Library")
        lib_btn.setToolTip("Add mods from your full library to this instance")
        lib_btn.setFixedHeight(22)
        lib_btn.setStyleSheet("font-size:10px;padding:1px 8px;")
        lib_btn.clicked.connect(self._open_library)
        hdr.addWidget(lib_btn)
        lo.addLayout(hdr)

        self.a_search = QLineEdit()
        self.a_search.setPlaceholderText("🔍 Search…")
        self.a_search.textChanged.connect(lambda t: self.avail.filter_text(t))
        lo.addWidget(self.a_search)

        self.avail = DragDropList(self)
        self.avail.itemDoubleClicked.connect(self._add_sel)
        self.avail.currentItemChanged.connect(
            lambda c, _: self._show_preview(c))
        self.avail.items_changed.connect(self._on_items_changed)
        self.avail.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.avail.customContextMenuRequested.connect(self._ctx_avail)
        lo.addWidget(self.avail)

        self.empty_hint = QLabel(
            "<i style='color:#555;font-size:10px;'>"
            "No inactive mods. Click 📚 Library to add mods.</i>")
        self.empty_hint.setWordWrap(True)
        self.empty_hint.hide()
        lo.addWidget(self.empty_hint)

        row = QHBoxLayout()
        row.addWidget(self._btn("Activate →", self._add_sel))
        row.addWidget(self._btn("All ⇒",      self._add_all))
        lo.addLayout(row)
        return w

    def _build_active_panel(self) -> QWidget:
        w  = QWidget()
        lo = QVBoxLayout(w)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(2)
        lo.addWidget(QLabel("Active — drag to reorder ↕"))

        self.ac_search = QLineEdit()
        self.ac_search.setPlaceholderText("🔍 Search…")
        self.ac_search.textChanged.connect(lambda t: self.active.filter_text(t))
        lo.addWidget(self.ac_search)

        self.active = DragDropList(self)
        self.active.setDragDropMode(DragDropList.DragDropMode.DragDrop)
        self.active.itemDoubleClicked.connect(self._on_active_double_click)
        self.active.currentItemChanged.connect(
            lambda c, _: self._show_preview(c))
        self.active.items_changed.connect(self._update)
        # NEW — recompute badges after drag-drop into active list
        self.active.needs_badge_refresh.connect(self._on_items_changed)
        self.active.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.active.customContextMenuRequested.connect(self._ctx_active)
        lo.addWidget(self.active)

        row = QHBoxLayout()
        row.addWidget(self._btn("← Deactivate", self._rem_sel))
        row.addWidget(self._btn("⇐ All",        self._rem_all))
        row.addStretch()
        lo.addLayout(row)

        self.avail.set_partner(self.active)
        self.active.set_partner(self.avail)
        return w

    def _build_bottom_bar(self) -> QHBoxLayout:
        b = QHBoxLayout()
        b.setSpacing(4)
        b.addWidget(self._btn("Auto-Sort",  self._sort,        "primaryButton"))
        b.addWidget(self._btn("Fix Issues", self._fix,         "primaryButton"))
        b.addWidget(self._btn("Vanilla",    self._vanilla,     "dangerButton"))
        b.addWidget(self._btn("Import",     self._import_file))
        b.addWidget(self._btn("Export",     self._export))
        b.addStretch()
        b.addWidget(self._btn("Cancel", self.reject))
        b.addWidget(self._btn("Save",   self._save, "successButton"))
        return b

    def _btn(self, text: str, slot, obj: str = None) -> QPushButton:
        b = QPushButton(text)
        b.setFixedHeight(26)
        b.setStyleSheet("font-size:11px;padding:2px 10px;")
        if obj:
            b.setObjectName(obj)
        b.clicked.connect(slot)
        return b

    # ─────────────────────────────────────────────────────────────────────────
    # Load / populate lists
    # ─────────────────────────────────────────────────────────────────────────

    def _load(self):
        mods, _, _ = read_mods_config(self.inst.config_dir)
        if not mods:
            mods = list(self.inst.mods)

        # Only mods that were ACTIVE when the editor opened are "not new".
        # Inactive mods are excluded: if a deactivated mod (or a Library mod
        # that was previously inactive) gets moved to active, it IS new.
        # Including inactive_mods here was causing [NEW] to never show for
        # any mod that had ever been in the inactive list.
        self._original_mods = set(mods)
        active_set = set(mods)

        # Active panel
        self.active.clear()
        self._batch_load_active(mods)           # from ItemBuilder

        # Available panel
        self.avail.clear()
        self.avail.setUpdatesEnabled(False)
        shown: set[str] = set()

        for mid in self.inst.inactive_mods:
            if mid not in active_set and mid not in shown:
                info = self.all_mods.get(mid)
                (self._mk_avail(mid, info) if info
                 else self._mk_avail_missing(mid))
                shown.add(mid)

        for mid in VANILLA_AND_DLCS:
            if mid not in active_set and mid not in shown and mid in self.all_mods:
                self._mk_avail(mid, self.all_mods[mid])
                shown.add(mid)

        if not self.inst.inactive_mods:          # first open — show everything
            for mid, info in self.all_mods.items():
                if mid not in active_set and mid not in shown:
                    self._mk_avail(mid, info)
                    shown.add(mid)

        self.avail.setUpdatesEnabled(True)
        self.avail.apply_item_widgets()          # <— colour labels applied here

        self._update_empty_hint()
        self._update()

    def _on_items_changed(self):
        """
        Called after drag-drop moves items into the active list.
        Recomputes badges so colors, [NEW], and error/warn prefixes are correct.
        """
        self._refresh_badges()
        self.active.apply_item_widgets()
        self._update_empty_hint()
        self._update()


    # ─────────────────────────────────────────────────────────────────────────
    # Preview
    # ─────────────────────────────────────────────────────────────────────────

    def _show_preview(self, item):
        if not item:
            return
        mid       = item.data(Qt.ItemDataRole.UserRole)
        info      = self.all_mods.get(mid)
        order     = self.active.get_ids()
        badges    = get_badges(mid, self.all_mods, set(order),
                               self.inst.rimworld_version or '', order)
        self.preview.show_mod(info, mid, badges)

    # ─────────────────────────────────────────────────────────────────────────
    # Issue filter toggle
    # ─────────────────────────────────────────────────────────────────────────

    def _toggle_filter(self):
        self._filter_issues = not self._filter_issues
        if self._filter_issues:
            ids = get_issue_mod_ids(self.active.get_ids(), self.all_mods,
                                    self.inst.rimworld_version or '')
            self.active.filter_by_ids(ids)
        else:
            self.active.filter_by_ids(None)
            self.ac_search.clear()
        self._update()

    # ─────────────────────────────────────────────────────────────────────────
    # Library
    # ─────────────────────────────────────────────────────────────────────────

    def _open_library(self):
        from app.ui.modeditor.library_dialog import LibraryDialog
        instance_ids = set(self.active.get_ids()) | set(self._avail_ids())
        dlg = LibraryDialog(self, self.all_mods, instance_ids,
                            self.inst.rimworld_version or '')
        if dlg.exec() and dlg.selected_ids:
            for mid in dlg.selected_ids:
                if mid in self.all_mods and mid not in instance_ids:
                    self._mk_avail(mid, self.all_mods[mid])
            self.avail.apply_item_widgets()
            self._update_empty_hint()
            self._update()

    def _avail_ids(self) -> list[str]:
        return [self.avail.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.avail.count())
                if self.avail.item(i).data(Qt.ItemDataRole.UserRole)]

    # keep old name as alias so nothing breaks
    def _get_avail_ids(self) -> list[str]:
        return self._avail_ids()

    # ─────────────────────────────────────────────────────────────────────────
    # Add / Remove
    # ─────────────────────────────────────────────────────────────────────────

    def _add_sel(self):
        selected = self.avail.selectedItems()
        if not selected:
            return
        self._defer_updates = True
        self.active.setUpdatesEnabled(False)
        self.avail.setUpdatesEnabled(False)

        rows     = sorted([self.avail.row(it) for it in selected], reverse=True)
        mids     = [it.data(Qt.ItemDataRole.UserRole) for it in selected]
        for row in rows:
            self.avail.takeItem(row)
        for mid in mids:
            self._mk_active(mid, skip_badges=True)

        self.avail.setUpdatesEnabled(True)
        self.active.setUpdatesEnabled(True)
        self._defer_updates = False

        self._refresh_badges()
        self.active.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _rem_sel(self):
        selected = self.active.selectedItems()
        if not selected:
            return

        to_remove, has_core = [], False
        for it in selected:
            if it.data(Qt.ItemDataRole.UserRole).lower() == 'ludeon.rimworld':
                has_core = True
            else:
                to_remove.append(it)

        if has_core and not to_remove:
            QMessageBox.warning(self, "Cannot Remove",
                                "Core (ludeon.rimworld) is required.")
            return

        self._defer_updates = True
        self.active.setUpdatesEnabled(False)
        self.avail.setUpdatesEnabled(False)

        rows = sorted([self.active.row(it) for it in to_remove], reverse=True)
        removed = []
        for row in rows:
            it = self.active.takeItem(row)
            if it:
                removed.append(it.data(Qt.ItemDataRole.UserRole))
        for mid in removed:
            if mid in self.all_mods:
                self._mk_avail(mid, self.all_mods[mid])

        self.avail.setUpdatesEnabled(True)
        self.active.setUpdatesEnabled(True)
        self._defer_updates = False

        if has_core:
            QMessageBox.information(
                self, "Note",
                f"Deactivated {len(removed)} mod(s). Core was kept (required).")

        self.avail.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _add_all(self):
        self._defer_updates = True
        self.active.setUpdatesEnabled(False)
        self.avail.setUpdatesEnabled(False)

        mids = []
        while self.avail.count():
            it = self.avail.takeItem(0)
            if it:
                mids.append(it.data(Qt.ItemDataRole.UserRole))
        for mid in mids:
            self._mk_active(mid, skip_badges=True)

        self.avail.setUpdatesEnabled(True)
        self.active.setUpdatesEnabled(True)
        self._defer_updates = False

        self._refresh_badges()
        self.active.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _rem_all(self):
        self._defer_updates = True
        self.active.setUpdatesEnabled(False)
        self.avail.setUpdatesEnabled(False)

        to_remove = [i for i in range(self.active.count())
                     if self.active.item(i).data(
                         Qt.ItemDataRole.UserRole).lower() != 'ludeon.rimworld']

        removed = []
        for i in reversed(to_remove):
            it = self.active.takeItem(i)
            if it:
                removed.append(it.data(Qt.ItemDataRole.UserRole))
        for mid in removed:
            if mid in self.all_mods:
                self._mk_avail(mid, self.all_mods[mid])

        self.avail.setUpdatesEnabled(True)
        self.active.setUpdatesEnabled(True)
        self._defer_updates = False

        self.avail.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _on_active_double_click(self, item):
        if not item:
            return
        mid = item.data(Qt.ItemDataRole.UserRole)
        if mid.lower() == 'ludeon.rimworld':
            QMessageBox.warning(self, "Cannot Remove",
                                "Core (ludeon.rimworld) is required.")
            return
        self.active.takeItem(self.active.row(item))
        if mid in self.all_mods:
            self._mk_avail(mid, self.all_mods[mid])
        self.avail.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _remove_from_instance_batch(self, items: list):
        if not items:
            return
        names = []
        for it in items:
            mid  = it.data(Qt.ItemDataRole.UserRole)
            info = self.all_mods.get(mid)
            names.append(info.name if info else mid)

        msg  = f"Remove {len(items)} mod(s) from this instance?\n\n"
        msg += "\n".join(f"  - {n}" for n in names[:10])
        if len(names) > 10:
            msg += f"\n  ... and {len(names) - 10} more"
        msg += "\n\nThey will still be available in the Library."

        if QMessageBox.question(self, "Remove from Instance",
                                msg) != QMessageBox.StandardButton.Yes:
            return

        # Freeze UI — without this each takeItem triggers a full repaint,
        # causing a hard lag spike on 300+ item removals.
        self.avail.setUpdatesEnabled(False)
        rows = sorted([self.avail.row(it) for it in items], reverse=True)
        for row in rows:
            self.avail.takeItem(row)
        self.avail.setUpdatesEnabled(True)
        # Re-apply color labels to remaining items after index shift
        self.avail.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    # ─────────────────────────────────────────────────────────────────────────
    # Sort / Vanilla / Import / Export
    # ─────────────────────────────────────────────────────────────────────────

    def _sort(self):
        ids = self.active.get_ids()
        if not ids:
            return
        self.all_mods = self.rw.get_installed_mods(force_rescan=True)
        sorted_ids    = auto_sort_mods(ids, self.rw)
        self.active.clear()
        self._batch_load_active(sorted_ids)
        self._update()

    def _vanilla(self):
        if QMessageBox.question(self, "Vanilla",
                                "Reset to Core + DLCs only?"
                                ) != QMessageBox.StandardButton.Yes:
            return
        self._rem_all()
        for mid in get_vanilla_modlist(self.rw.get_detected_dlcs()):
            if mid in set(self.active.get_ids()):
                continue
            self._mk_active(mid)
            for i in range(self.avail.count()):
                if self.avail.item(i).data(Qt.ItemDataRole.UserRole) == mid:
                    self.avail.takeItem(i)
                    break
        self.active.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _import_file(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Import", "", "Text (*.txt);;XML (*.xml)")
        if not p:
            return
        mods = (read_mods_config(Path(p).parent)[0]
                if p.endswith('.xml')
                else parse_rimsort_modlist(p))
        if not mods:
            return
        self._rem_all()
        active_set = set(self.active.get_ids())
        for mid in mods:
            if mid in active_set:
                continue
            self._mk_active(mid)
            for i in range(self.avail.count()):
                if self.avail.item(i).data(Qt.ItemDataRole.UserRole) == mid:
                    self.avail.takeItem(i)
                    break
        self.active.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _export(self):
        p, _ = QFileDialog.getSaveFileName(
            self, "Export", "modlist.txt", "Text (*.txt)")
        if p:
            export_rimsort_modlist(p, self.active.get_ids(), self.names)

    # ─────────────────────────────────────────────────────────────────────────
    # Fix Issues
    # ─────────────────────────────────────────────────────────────────────────

    def _fix(self):
        ids    = self.active.get_ids()
        issues = analyze_modlist(ids, self.rw, self.inst.rimworld_version or '')
        if not issues:
            QMessageBox.information(self, "Fix Issues", "No issues found.")
            return

        activatable  = get_activatable_deps(issues)
        downloadable = get_downloadable_deps(issues)
        activated    = 0
        avail_set    = set(self._avail_ids())

        for dep in activatable:
            if dep in self.all_mods and dep not in set(self.active.get_ids()):
                for i in range(self.avail.count()):
                    if self.avail.item(i).data(
                            Qt.ItemDataRole.UserRole) == dep:
                        self.avail.takeItem(i)
                        break
                self._mk_active(dep)
                activated += 1

        if downloadable:
            self._offer_download(downloadable, activated)
            return
        self._show_fix_report(issues, activated, [])

    def _offer_download(self, downloadable: list, already_activated: int):
        mod_list = "\n".join(
            f"  - {name} ({wid})" for wid, name in downloadable[:10])
        if len(downloadable) > 10:
            mod_list += f"\n  ... and {len(downloadable) - 10} more"
        msg = f"{len(downloadable)} mod(s) need downloading:\n\n{mod_list}\n\nDownload now?"
        if already_activated:
            msg = f"[FIXED] Activated {already_activated} dep(s).\n\n" + msg

        if QMessageBox.question(
                self, "Download Required", msg,
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self._start_download(downloadable)
        else:
            issues = analyze_modlist(self.active.get_ids(), self.rw,
                                     self.inst.rimworld_version or '')
            self._show_fix_report(issues, already_activated, [])

    def _start_download(self, mods_to_download: list):
        from app.ui.modeditor.download_dialog import DownloadProgressDialog
        s            = load_json(settings_path(), {})
        steamcmd_path = s.get('steamcmd_path', '')
        data_root     = s.get('data_root', '')

        if not steamcmd_path or not Path(steamcmd_path).exists():
            QMessageBox.warning(self, "SteamCMD Not Configured",
                                "Set the SteamCMD path in Settings.")
            return
        if not data_root:
            QMessageBox.warning(self, "Error", "Data root not configured.")
            return

        queue = DownloadQueue(
            steamcmd_path=steamcmd_path,
            destination=str(Path(data_root) / 'mods'),
            max_concurrent=2,
            username=s.get('steamcmd_username', ''))
        dlg = DownloadProgressDialog(self, queue, mods_to_download)
        dlg.downloads_complete.connect(self._on_downloads_complete)
        dlg.exec()

    def _on_downloads_complete(self, results: list):
        ok  = sum(1 for _, s, _ in results if s)
        bad = len(results) - ok

        if ok:
            self.all_mods = self.rw.get_installed_mods(force_rescan=True)
            self.names    = {pid: i.name for pid, i in self.all_mods.items()}
            issues        = analyze_modlist(self.active.get_ids(), self.rw,
                                            self.inst.rimworld_version or '')
            newly = 0
            for dep in get_activatable_deps(issues):
                if dep in self.all_mods and dep not in set(self.active.get_ids()):
                    self._mk_active(dep)
                    newly += 1
            msg = f"Downloaded {ok} mod(s)."
            if newly:
                msg += f"\nActivated {newly} dep(s)."
            if bad:
                msg += f"\n\n{bad} download(s) failed."
            QMessageBox.information(self, "Downloads Complete", msg)
        elif bad:
            QMessageBox.warning(self, "Downloads Failed",
                                f"All {bad} download(s) failed.")

        self.active.apply_item_widgets()
        self._refresh_inner()
        issues = analyze_modlist(self.active.get_ids(), self.rw,
                                 self.inst.rimworld_version or '')
        if issues:
            self._show_fix_report(issues, 0, results)

    def _show_fix_report(self, issues: list, activated: int,
                         dl_results: list):
        order       = self.active.get_ids()
        order_count = sum(
            len(check_load_order(mid, self.all_mods.get(mid), order,
                                 self.all_mods))
            for mid in order if self.all_mods.get(mid))

        unfixable   = [i for i in issues if i.issue_type == 'missing_dep'
                       and i.severity == 'error' and not i.workshop_id]
        not_found   = [i for i in issues if i.issue_type == 'not_found']
        ver_issues  = [i for i in issues if i.issue_type == 'version_mismatch']
        downloadable= [i for i in issues if i.issue_type == 'missing_dep'
                       and i.severity == 'error' and i.workshop_id]

        report, has_errors = [], False

        if activated:
            report.append(f"[FIXED] Activated {activated} dep(s)")
        if dl_results:
            ok  = sum(1 for _, s, _ in dl_results if s)
            bad = len(dl_results) - ok
            if ok:  report.append(f"[DOWNLOADED] {ok} mod(s)")
            if bad: report.append(f"[FAILED] {bad} mod(s)"); has_errors = True
        if downloadable:
            report.append(f"\n[NEED DOWNLOAD] {len(downloadable)} mod(s)")
            has_errors = True
        if unfixable:
            report.append(f"\n[MISSING - NO WS ID] {len(unfixable)} mod(s):")
            for iss in unfixable[:5]:
                report.append(f"   - {iss.mod_name} needs '{iss.dep_name}'")
            report.append("Find and install these manually.")
            has_errors = True
        if not_found:
            report.append(f"\n[NOT INSTALLED] {len(not_found)} mod(s):")
            for iss in not_found[:5]:
                report.append(f"   - {iss.mod_name}")
            has_errors = True
        if ver_issues:
            report.append(
                f"\n[VERSION WARNING] {len(ver_issues)} mod(s) may be incompatible")
        if order_count:
            report.append(
                f"\n[LOAD ORDER] {order_count} issue(s) — click Auto-Sort to fix")

        if not report:
            QMessageBox.information(self, "Fix Issues", "All issues resolved.")
        elif not has_errors and not order_count:
            QMessageBox.information(self, "Fix Issues",
                                    "Fixed:\n\n" + '\n'.join(report))
        else:
            QMessageBox.warning(self, "Fix Issues — Action Required",
                                '\n'.join(report))

        self.active.apply_item_widgets()
        self._refresh_inner()

    def _refresh_inner(self):
        """Rebuild the active list preserving order."""
        mods = self.active.get_ids()
        self.active.clear()
        self._batch_load_active(mods)
        if self._filter_issues:
            ids = get_issue_mod_ids(self.active.get_ids(), self.all_mods,
                                    self.inst.rimworld_version or '')
            self.active.filter_by_ids(ids)

    # ─────────────────────────────────────────────────────────────────────────
    # Context menus
    # ─────────────────────────────────────────────────────────────────────────

    def _ctx_active(self, pos):
        it = self.active.itemAt(pos)
        if not it:
            return
        mid  = it.data(Qt.ItemDataRole.UserRole)
        info = self.all_mods.get(mid)
        m    = QMenu(self)

        rem = m.addAction("Deactivate")
        if mid.lower() == 'ludeon.rimworld':
            rem.setEnabled(False)
            rem.setText("Deactivate (Core — required)")
        else:
            rem.triggered.connect(self._rem_sel)

        if info and info.source == 'workshop':
            m.addSeparator()
            m.addAction("Delete files", lambda: self._del_mod(mid))
        if info and info.workshop_id:
            from app.core.steam_integration import open_workshop_page
            m.addAction("Workshop page",
                        lambda: open_workshop_page(info.workshop_id))
        m.exec(self.active.mapToGlobal(pos))

    def _ctx_avail(self, pos):
        it = self.avail.itemAt(pos)
        if not it:
            return
        mid      = it.data(Qt.ItemDataRole.UserRole)
        info     = self.all_mods.get(mid)
        selected = self.avail.selectedItems()
        m        = QMenu(self)
        m.addAction("Activate →", self._add_sel)

        removable = [i for i in selected
                     if i.data(Qt.ItemDataRole.UserRole) not in VANILLA_AND_DLCS]
        if removable:
            m.addSeparator()
            label = ("Remove from Instance" if len(removable) == 1
                     else f"Remove {len(removable)} from Instance")
            m.addAction(label,
                        lambda: self._remove_from_instance_batch(removable))

        if info and info.workshop_id:
            from app.core.steam_integration import open_workshop_page
            m.addAction("Workshop page",
                        lambda: open_workshop_page(info.workshop_id))
        m.exec(self.avail.mapToGlobal(pos))

    def _del_mod(self, mid: str):
        info = self.all_mods.get(mid)
        name = info.name if info else mid
        if QMessageBox.question(self, "Delete",
                                f"Delete '{name}'?"
                                ) != QMessageBox.StandardButton.Yes:
            return
        s = load_json(settings_path(), {})
        dr, exe = s.get('data_root', ''), s.get('rimworld_exe', '')
        if dr:
            wid = info.workshop_id if info else mid
            delete_downloaded_mod(
                Path(dr) / 'mods' / wid,
                Path(exe).parent / 'Mods' if exe else Path())
        self._rem_sel()
        self.all_mods = self.rw.get_installed_mods(force_rescan=True)
        self.names    = {pid: i.name for pid, i in self.all_mods.items()}

    # ─────────────────────────────────────────────────────────────────────────
    # Update status bar
    # ─────────────────────────────────────────────────────────────────────────

    def _update(self):
        if self._defer_updates:
            return
        n      = self.active.count()
        n_av   = self.avail.count()
        self.cnt.setText(f"{n} active · {n_av} inactive")

        ids            = self.active.get_ids()
        errors, warns, order = count_issues(
            ids, self.all_mods, self.inst.rimworld_version or '')
        text  = format_issue_text(errors, warns, order, self._filter_issues)
        color = format_issue_color(errors, warns, order)
        self.issue_btn.setText(text)
        self.issue_btn.setStyleSheet(
            f"font-size:11px;padding:0 6px;border:none;color:{color};")

    def _update_empty_hint(self):
        has_non_dlc = any(
            self.avail.item(i).data(Qt.ItemDataRole.UserRole)
            not in VANILLA_AND_DLCS
            for i in range(self.avail.count()))
        self.empty_hint.setVisible(
            self.avail.count() == 0 or not has_non_dlc)

    # ─────────────────────────────────────────────────────────────────────────
    # Save
    # ─────────────────────────────────────────────────────────────────────────

    def _save(self):
        active_ids = self.active.get_ids()
        if not any(m.lower() == 'ludeon.rimworld' for m in active_ids):
            active_ids.insert(0, 'ludeon.rimworld')

        issues   = analyze_modlist(active_ids, self.rw,
                                   self.inst.rimworld_version or '')
        critical = [i for i in issues if i.severity == 'error']

        if critical:
            msg = f"Cannot save: {len(critical)} critical issue(s).\n\n"
            missing = [i for i in critical if i.issue_type == 'missing_dep']
            absent  = [i for i in critical if i.issue_type == 'not_found']
            if missing:
                msg += f"Missing deps ({len(missing)}):\n"
                for iss in missing[:5]:
                    msg += f"  - {iss.mod_name} needs '{iss.dep_name}'\n"
            if absent:
                msg += f"\nNot on disk ({len(absent)}):\n"
                for iss in absent[:5]:
                    msg += f"  - {iss.mod_name}\n"
            msg += "\nUse 'Fix Issues' to resolve."
            QMessageBox.critical(self, "Cannot Save", msg)
            return

        inactive_ids = [mid for mid in self._avail_ids()
                        if mid not in VANILLA_AND_DLCS]
        exp          = [m for m in active_ids
                        if m in VANILLA_AND_DLCS and m != 'ludeon.rimworld']

        write_mods_config(
            self.inst.config_dir, active_ids,
            self.inst.rimworld_version or '1.6.4630 rev467',
            exp or None)

        self.inst.mods         = active_ids
        self.inst.inactive_mods = inactive_ids
        self.inst.save()

        verify, _, _ = read_mods_config(self.inst.config_dir)
        print(f"[Save] Wrote {len(active_ids)} active, "
              f"{len(inactive_ids)} inactive | verified {len(verify)}")

        s = load_json(settings_path(), {})
        dr, exe = s.get('data_root', ''), s.get('rimworld_exe', '')
        if dr and exe:
            r = sync_instance_mods(
                active_ids, self.all_mods,
                Path(exe).parent / 'Mods',
                Path(dr) / 'mods')
            if r['failed']:
                QMessageBox.warning(
                    self, "Sync",
                    f"Failed: {', '.join(r['errors'][:3])}")

        self.accept()