"""Mod editor with per-instance mod isolation."""

from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QMessageBox, QFileDialog, QSplitter, QWidget, QMenu,
    QListWidgetItem
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from app.core.instance import Instance
from app.core.rimworld import RimWorldDetector
from app.core.modlist import (
    write_mods_config, read_mods_config, parse_rimsort_modlist,
    export_rimsort_modlist, get_vanilla_modlist, VANILLA_AND_DLCS
)
from app.core.mod_sort import auto_sort_mods
from app.core.mod_linker import delete_downloaded_mod, sync_instance_mods
from app.core.dep_resolver import analyze_modlist, get_downloadable_deps, get_activatable_deps
from app.core.paths import settings_path
from app.utils.file_utils import load_json

from app.ui.modeditor.drag_list import DragDropList
from app.ui.modeditor.preview_panel import PreviewPanel
from app.ui.modeditor.issue_checker import (
    get_badges, check_version, count_issues,
    get_issue_mod_ids, format_issue_text, format_issue_color
)

PROTECTED_MODS = {'ludeon.rimworld'}


class ModEditorDialog(QDialog):
    def __init__(self, parent, instance: Instance, rw: RimWorldDetector):
        super().__init__(parent)
        self.inst = instance
        self.rw = rw
        self.all_mods = rw.get_installed_mods(force_rescan=True)
        self.names = {pid: info.name for pid, info in self.all_mods.items()}
        self._filter_issues = False

        self.setWindowTitle(f"Mods — {instance.name}")
        self.setMinimumSize(960, 520)
        self.resize(1040, 590)
        self._build()
        self._load()

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(6, 4, 6, 6)
        lo.setSpacing(4)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel(f"<b>{self.inst.name}</b>"))
        self.cnt = QLabel("0")
        self.cnt.setStyleSheet("color:#7c8aff;font-weight:bold;font-size:11px;")
        hdr.addWidget(self.cnt)

        self.issue_btn = QPushButton("✔ OK")
        self.issue_btn.setFlat(True)
        self.issue_btn.setStyleSheet("font-size:11px;padding:0 6px;border:none;color:#4CAF50;")
        self.issue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.issue_btn.setToolTip("Click to show only mods with issues")
        self.issue_btn.clicked.connect(self._toggle_filter)
        hdr.addWidget(self.issue_btn)
        hdr.addStretch()
        lo.addLayout(hdr)

        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(self._build_avail())
        sp.addWidget(self._build_active())
        self.preview = PreviewPanel(self)
        sp.addWidget(self.preview)
        sp.setSizes([240, 320, 260])
        lo.addWidget(sp, 1)
        lo.addLayout(self._build_bottom())

    def _build_avail(self) -> QWidget:
        w = QWidget()
        lo = QVBoxLayout(w)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(2)

        # Header with Library button
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("Instance Mods (inactive)"))
        hdr.addStretch()
        lib_btn = QPushButton("📚 Library")
        lib_btn.setToolTip("Add mods from your library to this instance")
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
        self.avail.currentItemChanged.connect(lambda c, _: self._show_preview(c))
        self.avail.items_changed.connect(self._update)
        self.avail.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.avail.customContextMenuRequested.connect(self._ctx_avail)
        lo.addWidget(self.avail)

        # Hint when empty
        self.empty_hint = QLabel(
            "<i style='color:#555;font-size:10px;'>"
            "No inactive mods. Click 📚 Library to add mods to this instance.</i>")
        self.empty_hint.setWordWrap(True)
        self.empty_hint.hide()
        lo.addWidget(self.empty_hint)

        ab = QHBoxLayout()
        ab.addWidget(self._btn("Activate →", self._add_sel))
        ab.addWidget(self._btn("All ⇒", self._add_all))
        lo.addLayout(ab)
        return w

    def _build_active(self) -> QWidget:
        w = QWidget()
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
        self.active.itemDoubleClicked.connect(self._rem_sel)
        self.active.currentItemChanged.connect(lambda c, _: self._show_preview(c))
        self.active.items_changed.connect(self._update)
        self.active.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.active.customContextMenuRequested.connect(self._ctx_active)
        lo.addWidget(self.active)
        rb = QHBoxLayout()
        rb.addWidget(self._btn("← Deactivate", self._rem_sel))
        rb.addWidget(self._btn("⇐ All", self._rem_all))
        rb.addStretch()
        lo.addLayout(rb)
        self.avail.set_partner(self.active)
        self.active.set_partner(self.avail)
        return w

    def _build_bottom(self) -> QHBoxLayout:
        b = QHBoxLayout()
        b.setSpacing(4)
        b.addWidget(self._btn("Auto-Sort", self._sort, "primaryButton"))
        b.addWidget(self._btn("Fix Issues", self._fix, "primaryButton"))
        b.addWidget(self._btn("Vanilla", self._vanilla, "dangerButton"))
        b.addWidget(self._btn("Import", self._import_file))
        b.addWidget(self._btn("Export", self._export))
        b.addStretch()
        b.addWidget(self._btn("Cancel", self.reject))
        b.addWidget(self._btn("Save", self._save, "successButton"))
        return b

    def _btn(self, text, slot, obj=None):
        b = QPushButton(text)
        b.setFixedHeight(26)
        b.setStyleSheet("font-size:11px;padding:2px 10px;")
        if obj:
            b.setObjectName(obj)
        b.clicked.connect(slot)
        return b

    # ── Load (per-instance isolation) ────────────────────────────

    def _load(self):
        # Active mods from config or instance
        mods, _, _ = read_mods_config(self.inst.config_dir)
        if not mods:
            mods = list(self.inst.mods)

        active_set = set(mods)

        # Active panel: mods in load order
        self.active.clear()
        for mid in mods:
            self._mk_active(mid)

        # Available panel: only instance's inactive mods + DLCs not active
        self.avail.clear()
        shown = set()

        # 1. Instance's inactive mods
        for mid in self.inst.inactive_mods:
            if mid not in active_set and mid not in shown:
                info = self.all_mods.get(mid)
                if info:
                    self._mk_avail(mid, info)
                    shown.add(mid)
                else:
                    # Mod in inactive list but not on disk — show as missing
                    self._mk_avail_missing(mid)
                    shown.add(mid)

        # 2. DLCs/Core not active (auto-available, no install needed)
        for mid in VANILLA_AND_DLCS:
            if mid not in active_set and mid not in shown and mid in self.all_mods:
                self._mk_avail(mid, self.all_mods[mid])
                shown.add(mid)

        self._update_empty_hint()
        self._update()

    def _mk_active(self, mid):
        name = self.names.get(mid, mid)
        order = self.active.get_ids() + [mid]
        active_ids = set(order)
        badges = get_badges(mid, self.all_mods, active_ids,
                            self.inst.rimworld_version or '', order)

        prefix = ''.join(b[0] for b in badges)
        label = f"{prefix} {name}  [{mid}]" if prefix else f"{name}  [{mid}]"
        if mid in PROTECTED_MODS:
            label = f"🔒 {label}"

        it = QListWidgetItem(label)
        it.setData(Qt.ItemDataRole.UserRole, mid)

        if not self.all_mods.get(mid):
            it.setForeground(QColor('#ff6b6b'))
            it.setToolTip("❌ Not on disk")
        elif badges:
            worst = min(badges, key=lambda b: {'error': 0, 'warning': 1, 'info': 2}.get(b[2], 3))
            it.setForeground(QColor(worst[1]))
            it.setToolTip('\n'.join(b[3] for b in badges))

        self.active.addItem(it)

    def _mk_avail(self, mid, info):
        src = {'dlc': '👑', 'workshop': '🏪', 'local': '📁'}.get(info.source, '')
        ver_ok = check_version(info, self.inst.rimworld_version or '')
        prefix = '🔶 ' if not ver_ok else ''
        it = QListWidgetItem(f"{prefix}{src} {info.name}  [{mid}]")
        it.setData(Qt.ItemDataRole.UserRole, mid)
        if not ver_ok:
            it.setForeground(QColor('#ffd54f'))
            it.setToolTip(f"Supports: {', '.join(info.supported_versions)}")
        self.avail.addItem(it)

    def _mk_avail_missing(self, mid):
        it = QListWidgetItem(f"❌ {mid}  [not on disk]")
        it.setData(Qt.ItemDataRole.UserRole, mid)
        it.setForeground(QColor('#ff6b6b'))
        it.setToolTip("This mod is in the instance but not found on disk")
        self.avail.addItem(it)

    def _update_empty_hint(self):
        has_non_dlc = False
        for i in range(self.avail.count()):
            mid = self.avail.item(i).data(Qt.ItemDataRole.UserRole)
            if mid not in VANILLA_AND_DLCS:
                has_non_dlc = True
                break
        self.empty_hint.setVisible(self.avail.count() == 0 or not has_non_dlc)

    # ── Library ──────────────────────────────────────────────────

    def _open_library(self):
        from app.ui.modeditor.library_dialog import LibraryDialog

        # Instance mod IDs = active + inactive (already in this instance)
        instance_ids = set(self.active.get_ids()) | set(self._get_avail_ids())

        dlg = LibraryDialog(self, self.all_mods, instance_ids,
                            self.inst.rimworld_version or '')
        if dlg.exec() and dlg.selected_ids:
            for mid in dlg.selected_ids:
                if mid in self.all_mods and mid not in instance_ids:
                    self._mk_avail(mid, self.all_mods[mid])
            self._update_empty_hint()
            self._update()

    def _get_avail_ids(self) -> list[str]:
        return [self.avail.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.avail.count())
                if self.avail.item(i).data(Qt.ItemDataRole.UserRole)]

    # ── Preview ──────────────────────────────────────────────────

    def _show_preview(self, item):
        if not item:
            return
        mid = item.data(Qt.ItemDataRole.UserRole)
        info = self.all_mods.get(mid)
        order = self.active.get_ids()
        active_ids = set(order)
        badges = get_badges(mid, self.all_mods, active_ids,
                            self.inst.rimworld_version or '', order)
        self.preview.show_mod(info, mid, badges)

    # ── Issue filter ─────────────────────────────────────────────

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

    # ── Fix ──────────────────────────────────────────────────────

    def _fix(self):
        ids = self.active.get_ids()
        issues = analyze_modlist(ids, self.rw, self.inst.rimworld_version or '')
        if not issues:
            QMessageBox.information(self, "Issues", "✔ No issues!")
            return

        activatable = get_activatable_deps(issues)
        activated = 0
        avail_ids = set(self._get_avail_ids())
        for dep in activatable:
            if dep in self.all_mods and dep not in set(self.active.get_ids()):
                # If dep is in Available, move it to Active
                if dep in avail_ids:
                    for i in range(self.avail.count()):
                        if self.avail.item(i).data(Qt.ItemDataRole.UserRole) == dep:
                            self.avail.takeItem(i)
                            break
                # If dep is not in instance at all, add it
                self._mk_active(dep)
                activated += 1

        downloadable = get_downloadable_deps(issues)
        report = []
        if activated:
            report.append(f"✔ Activated {activated} dep(s)")
        if downloadable:
            report.append(f"{len(downloadable)} need downloading:")
            for ws_id, name in downloadable:
                report.append(f"  - {name} ({ws_id})")

        order = self.active.get_ids()
        order_count = 0
        for mid in order:
            info = self.all_mods.get(mid)
            if info:
                from app.ui.modeditor.issue_checker import check_load_order
                lo_issues = check_load_order(mid, info, order, self.all_mods)
                order_count += len(lo_issues)
        if order_count:
            report.append(f"\n🔃 {order_count} load order issue(s) — use Auto-Sort to fix")

        QMessageBox.information(self, "Fix Issues", '\n'.join(report) or "Done.")
        self._update()
        self._refresh()

    def _refresh(self):
        mods = self.active.get_ids()
        self.active.clear()
        for mid in mods:
            self._mk_active(mid)
        if self._filter_issues:
            ids = get_issue_mod_ids(self.active.get_ids(), self.all_mods,
                                    self.inst.rimworld_version or '')
            self.active.filter_by_ids(ids)

    # ── Context menus ────────────────────────────────────────────

    def _ctx_active(self, pos):
        it = self.active.itemAt(pos)
        if not it:
            return
        mid = it.data(Qt.ItemDataRole.UserRole)
        info = self.all_mods.get(mid)
        m = QMenu(self)

        rem = m.addAction("Deactivate")
        if mid in PROTECTED_MODS:
            rem.setEnabled(False)
            rem.setText("Deactivate (Core — required)")
        else:
            rem.triggered.connect(self._rem_sel)

        if info and info.source == 'workshop':
            m.addSeparator()
            m.addAction("Delete files", lambda: self._del(mid))
        if info and info.workshop_id:
            from app.core.steam_integration import open_workshop_page
            m.addAction("Workshop page", lambda: open_workshop_page(info.workshop_id))
        m.exec(self.active.mapToGlobal(pos))

    def _ctx_avail(self, pos):
        it = self.avail.itemAt(pos)
        if not it:
            return
        mid = it.data(Qt.ItemDataRole.UserRole)
        info = self.all_mods.get(mid)
        m = QMenu(self)
        m.addAction("Activate →", self._add_sel)

        # Only allow removal from instance for non-DLC mods
        if mid not in VANILLA_AND_DLCS:
            m.addSeparator()
            m.addAction("Remove from Instance", lambda: self._remove_from_instance(mid))

        if info and info.workshop_id:
            from app.core.steam_integration import open_workshop_page
            m.addAction("Workshop page", lambda: open_workshop_page(info.workshop_id))
        m.exec(self.avail.mapToGlobal(pos))

    def _remove_from_instance(self, mid):
        """Remove a mod entirely from this instance (not just deactivate)."""
        info = self.all_mods.get(mid)
        name = info.name if info else mid
        if QMessageBox.question(self, "Remove from Instance",
                                f"Remove '{name}' from this instance?\n"
                                "It will still be available in the Library."
                                ) != QMessageBox.StandardButton.Yes:
            return
        for i in range(self.avail.count()):
            if self.avail.item(i).data(Qt.ItemDataRole.UserRole) == mid:
                self.avail.takeItem(i)
                break
        self._update_empty_hint()
        self._update()

    def _del(self, mid):
        info = self.all_mods.get(mid)
        name = info.name if info else mid
        if QMessageBox.question(self, "Delete", f"Delete '{name}'?"
                                ) != QMessageBox.StandardButton.Yes:
            return
        s = load_json(settings_path(), {})
        dr, exe = s.get('data_root', ''), s.get('rimworld_exe', '')
        if dr:
            wid = info.workshop_id if info else mid
            delete_downloaded_mod(Path(dr) / 'mods' / wid,
                                  Path(exe).parent / 'Mods' if exe else Path())
        self._rem_sel()
        self.all_mods = self.rw.get_installed_mods(force_rescan=True)
        self.names = {pid: i.name for pid, i in self.all_mods.items()}

    # ── Add/Remove ───────────────────────────────────────────────

    def _add_sel(self):
        for it in self.avail.selectedItems():
            self._mk_active(it.data(Qt.ItemDataRole.UserRole))
            self.avail.takeItem(self.avail.row(it))
        self._update_empty_hint()
        self._update()

    def _rem_sel(self):
        for it in self.active.selectedItems():
            mid = it.data(Qt.ItemDataRole.UserRole)
            if mid in PROTECTED_MODS:
                continue
            self.active.takeItem(self.active.row(it))
            # Deactivated mod stays in instance (goes to Available)
            if mid in self.all_mods:
                self._mk_avail(mid, self.all_mods[mid])
        self._update_empty_hint()
        self._update()

    def _add_all(self):
        while self.avail.count():
            it = self.avail.takeItem(0)
            self._mk_active(it.data(Qt.ItemDataRole.UserRole))
        self._update_empty_hint()
        self._update()

    def _rem_all(self):
        to_remove = []
        for i in range(self.active.count()):
            mid = self.active.item(i).data(Qt.ItemDataRole.UserRole)
            if mid not in PROTECTED_MODS:
                to_remove.append(i)
        for i in reversed(to_remove):
            it = self.active.takeItem(i)
            mid = it.data(Qt.ItemDataRole.UserRole)
            if mid in self.all_mods:
                self._mk_avail(mid, self.all_mods[mid])
        self._update_empty_hint()
        self._update()

    def _sort(self):
        ids = self.active.get_ids()
        if not ids:
            return
        sorted_ids = auto_sort_mods(ids, self.rw)
        self.active.clear()
        for mid in sorted_ids:
            self._mk_active(mid)
        self._update()

    def _vanilla(self):
        if QMessageBox.question(self, "Vanilla", "Reset to Core + DLCs?"
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
        self._update_empty_hint()
        self._update()

    def _import_file(self):
        p, _ = QFileDialog.getOpenFileName(self, "Import", "", "Text (*.txt);;XML (*.xml)")
        if not p:
            return
        if p.endswith('.xml'):
            mods, _, _ = read_mods_config(Path(p).parent)
        else:
            mods = parse_rimsort_modlist(p)
        if mods:
            # Importing adds all mods to this instance
            self._rem_all()
            for mid in mods:
                if mid in set(self.active.get_ids()):
                    continue
                self._mk_active(mid)
                for i in range(self.avail.count()):
                    if self.avail.item(i).data(Qt.ItemDataRole.UserRole) == mid:
                        self.avail.takeItem(i)
                        break
            self._update_empty_hint()
            self._update()

    def _export(self):
        p, _ = QFileDialog.getSaveFileName(self, "Export", "modlist.txt", "Text (*.txt)")
        if p:
            export_rimsort_modlist(p, self.active.get_ids(), self.names)

    # ── Update ───────────────────────────────────────────────────

    def _update(self):
        n = self.active.count()
        n_avail = self.avail.count()
        self.cnt.setText(f"{n} active · {n_avail} inactive")

        ids = self.active.get_ids()
        errors, warnings, order = count_issues(ids, self.all_mods,
                                                self.inst.rimworld_version or '')
        text = format_issue_text(errors, warnings, order, self._filter_issues)
        color = format_issue_color(errors, warnings, order)
        self.issue_btn.setText(text)
        self.issue_btn.setStyleSheet(f"font-size:11px;padding:0 6px;border:none;color:{color};")

    # ── Save (writes both active + inactive for isolation) ───────

    def _save(self):
        active_ids = self.active.get_ids()
        if 'ludeon.rimworld' not in active_ids:
            active_ids.insert(0, 'ludeon.rimworld')

        # Inactive = mods in Available panel that aren't DLCs (DLCs are auto-available)
        inactive_ids = [
            mid for mid in self._get_avail_ids()
            if mid not in VANILLA_AND_DLCS
        ]

        exp = [m for m in active_ids if m in VANILLA_AND_DLCS and m != 'ludeon.rimworld']
        write_mods_config(self.inst.config_dir, active_ids,
                          self.inst.rimworld_version or '1.6.4630 rev467',
                          exp or None)

        self.inst.mods = active_ids
        self.inst.inactive_mods = inactive_ids
        self.inst.save()

        verify, _, _ = read_mods_config(self.inst.config_dir)
        print(f"[Save] Wrote {len(active_ids)} active, {len(inactive_ids)} inactive")
        print(f"[Save] Verified {len(verify)} in XML")

        s = load_json(settings_path(), {})
        dr, exe = s.get('data_root', ''), s.get('rimworld_exe', '')
        if dr and exe:
            onyx_mods = Path(dr) / 'mods'
            game_mods = Path(exe).parent / 'Mods'
            r = sync_instance_mods(active_ids, self.all_mods, game_mods, onyx_mods)
            if r['failed']:
                QMessageBox.warning(self, "Sync", f"Failed: {', '.join(r['errors'][:3])}")

        self.accept()