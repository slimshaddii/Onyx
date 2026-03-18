"""Mod editor dialog — per-instance mod isolation."""

from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QSplitter, QWidget,
)
from PyQt6.QtCore import Qt

from app.core.instance import Instance
from app.core.rimworld import RimWorldDetector
from app.core.modlist import read_mods_config, VANILLA_AND_DLCS
from app.core.paths import settings_path
from app.utils.file_utils import load_json

from app.ui.modeditor.drag_list import DragDropList
from app.ui.modeditor.preview_panel import PreviewPanel
from app.ui.modeditor.item_builder import ItemBuilder
from app.ui.modeditor.issue_checker import (
    get_badges, count_issues, get_issue_mod_ids,
    format_issue_text, format_issue_color,
)
from app.ui.modeditor.mod_actions import ModActions
from app.ui.modeditor.mod_fixes   import ModFixes
from app.ui.modeditor.mod_io      import ModIO
from app.ui.modeditor.mod_context import ModContext


class ModEditorDialog(ItemBuilder, ModActions, ModFixes, ModIO,
                      ModContext, QDialog):
    """
    Three-panel mod editor.
    Left   — inactive mods for this instance
    Centre — active mods (drag to reorder)
    Right  — preview panel
    """

    def __init__(self, parent, instance: Instance, rw: RimWorldDetector):
        QDialog.__init__(self, parent)
        self.inst     = instance
        self.rw       = rw
        self.all_mods = rw.get_installed_mods(force_rescan=True)
        self.names    = {pid: info.name
                         for pid, info in self.all_mods.items()}

        self._filter_issues = False
        self._defer_updates = False
        self._known_mod_ids = self._load_known_mod_ids()
        self._original_mods: set[str] = set(instance.mods)

        self.setWindowTitle(f"Mods — {instance.name}")
        self.setMinimumSize(960, 520)
        self.resize(1040, 590)
        self._build_ui()
        self._load()

    # ── Init helpers ──────────────────────────────────────────────────────────

    def _load_known_mod_ids(self) -> set[str]:
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

    def _ignored_deps_set(self) -> set[str]:
        return set(self.inst.ignored_deps)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(6, 4, 6, 6)
        lo.setSpacing(4)

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
        self.a_search.textChanged.connect(
            lambda t: self.avail.filter_text(t))
        lo.addWidget(self.a_search)

        self.avail = DragDropList(self)
        self.avail.itemDoubleClicked.connect(self._add_sel)
        self.avail.currentItemChanged.connect(
            lambda c, _: self._show_preview(c))
        self.avail.items_changed.connect(self._on_items_changed)
        self.avail.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
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
        self.ac_search.textChanged.connect(
            lambda t: self.active.filter_text(t))
        lo.addWidget(self.ac_search)

        self.active = DragDropList(self)
        self.active.setDragDropMode(DragDropList.DragDropMode.DragDrop)
        self.active.itemDoubleClicked.connect(self._on_active_double_click)
        self.active.currentItemChanged.connect(
            lambda c, _: self._show_preview(c))
        self.active.items_changed.connect(self._update)
        self.active.needs_badge_refresh.connect(self._on_items_changed)
        self.active.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
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
        b.addWidget(self._btn("History",    self._open_history))
        b.addWidget(self._btn("Conflicts",  self._open_conflicts))
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

    # ── Load ──────────────────────────────────────────────────────────────────

    def _load(self):
        mods, _, _ = read_mods_config(self.inst.config_dir)
        if not mods:
            mods = list(self.inst.mods)

        self._original_mods = set(mods)
        active_set          = set(mods)

        self.active.clear()
        self._batch_load_active(mods)

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
            if (mid not in active_set and mid not in shown
                    and mid in self.all_mods):
                self._mk_avail(mid, self.all_mods[mid])
                shown.add(mid)

        if not self.inst.mods_configured:
            for mid, info in self.all_mods.items():
                if mid not in active_set and mid not in shown:
                    self._mk_avail(mid, info)
                    shown.add(mid)

        self.avail.setUpdatesEnabled(True)
        self.avail.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _on_items_changed(self):
        self._refresh_badges()
        self.active.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    # ── Preview ───────────────────────────────────────────────────────────────

    def _show_preview(self, item):
        if not item:
            return
        mid    = item.data(Qt.ItemDataRole.UserRole)
        info   = self.all_mods.get(mid)
        order  = self.active.get_ids()
        badges = get_badges(mid, self.all_mods, set(order),
                            self.inst.rimworld_version or '', order,
                            ignored_deps=self._ignored_deps_set())
        self.preview.show_mod(info, mid, badges)

    # ── Issue filter ──────────────────────────────────────────────────────────

    def _toggle_filter(self):
        self._filter_issues = not self._filter_issues
        if self._filter_issues:
            ids = get_issue_mod_ids(
                self.active.get_ids(), self.all_mods,
                self.inst.rimworld_version or '',
                ignored_deps=self._ignored_deps_set())
            self.active.filter_by_ids(ids)
        else:
            self.active.filter_by_ids(None)
            self.ac_search.clear()
        self._update()

    # ── Library ───────────────────────────────────────────────────────────────

    def _open_library(self):
        from app.ui.modeditor.library_dialog import LibraryDialog
        instance_ids = set(self.active.get_ids()) | set(self._avail_ids())
        dlg = LibraryDialog(self, self.all_mods, instance_ids,
                            self.inst.rimworld_version or '',
                            rw=self.rw)
        if dlg.exec() and dlg.selected_ids:
            for mid in dlg.selected_ids:
                if mid in self.all_mods and mid not in instance_ids:
                    self._mk_avail(mid, self.all_mods[mid])
            self.avail.apply_item_widgets()
            self._update_empty_hint()
            self._update()

    # ── Save History ──────────────────────────────────────────────────────────

    def _open_history(self):
        from app.core.mod_history import ModHistory
        from app.ui.modeditor.history_panel import HistoryDialog

        history = ModHistory(self.inst.path)
        if not history.snapshots:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "No History",
                "No snapshots recorded yet.\n\n"
                "Snapshots are saved automatically each time you save "
                "from the mod editor. You can also save a named snapshot "
                "from the History dialog.")
            return

        dlg = HistoryDialog(
            self,
            history=history,
            current_mods=self.active.get_ids(),
            mod_names=self.names)

        if dlg.exec() and dlg.rolled_back_mods is not None:
            self._apply_rollback(dlg.rolled_back_mods)

    def _apply_rollback(self, mods: list[str]):
        from PyQt6.QtWidgets import QMessageBox
        from app.core.modlist import VANILLA_AND_DLCS

        # Capture everything currently in the editor before we change anything
        # "in the instance" = active + avail (not the whole library)
        current_active = set(self.active.get_ids())
        current_avail  = set(self._avail_ids())
        instance_mods  = current_active | current_avail  # the full instance pool

        rollback_set   = set(mods)

        # Mods that should move to avail after rollback:
        # were in the instance pool AND are not in the rollback active list
        # AND are not already in avail (no duplicates)
        to_avail = [
            mid for mid in instance_mods
            if mid not in rollback_set
            and mid not in current_avail
            and mid not in VANILLA_AND_DLCS
        ]

        # Rebuild active panel with rollback mods
        self.active.clear()
        self._batch_load_active(mods)

        # Move displaced mods to avail
        for mid in to_avail:
            info = self.all_mods.get(mid)
            if info:
                self._mk_avail(mid, info)
            else:
                self._mk_avail_missing(mid)

        self.avail.apply_item_widgets()
        self._update_empty_hint()
        self._update()

        QMessageBox.information(
            self, "Rolled Back",
            f"Loaded {len(mods)} mods from snapshot.\n\n"
            "Click Save to apply, or Cancel to discard.")
        
    # ── Conflicts ─────────────────────────────────────────────────────────────

    def _open_conflicts(self):
        from app.ui.modeditor.conflict_dialog import ConflictReportDialog
        dlg = ConflictReportDialog(
            self,
            active_ids=self.active.get_ids(),
            all_mods=self.all_mods,
            mod_names=self.names)
        dlg.exec()   

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _avail_ids(self) -> list[str]:
        return [
            self.avail.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.avail.count())
            if self.avail.item(i).data(Qt.ItemDataRole.UserRole)
        ]

    def _get_avail_ids(self) -> list[str]:
        return self._avail_ids()

    def _update(self):
        if self._defer_updates:
            return
        n    = self.active.count()
        n_av = self.avail.count()
        self.cnt.setText(f"{n} active · {n_av} inactive")

        ids     = self.active.get_ids()
        ignored = self._ignored_deps_set()
        errors, warns, order = count_issues(
            ids, self.all_mods,
            self.inst.rimworld_version or '',
            ignored_deps=ignored)
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