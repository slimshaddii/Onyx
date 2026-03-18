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
    format_issue_color,
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
        self.all_mods = rw.get_installed_mods(force_rescan=True, max_age_seconds=30.0)
        self.names    = {pid: info.name
                         for pid, info in self.all_mods.items()}

        self._filter_on   = False
        self._filter_cats: set[str] = {'error', 'dep', 'warning', 'order'}
        self._defer_updates = False
        self._chip_btns: dict[str, QPushButton] = {}
        self._known_mod_ids = self._load_known_mod_ids()
        self._original_mods: set[str] = set(instance.mods)

        self.setWindowTitle(f"Mods — {instance.name}")
        self.setMinimumSize(960, 520)
        self.resize(1040, 590)
        self._build_ui()
        self._load()

    # ── Init helpers ──────────────────────────────────────────────────────────

    def _load_known_mod_ids(self) -> set[str]:
        from app.core.app_settings import AppSettings
        data_root = AppSettings.instance().data_root
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

        # ── Header row ────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel(f"<b>{self.inst.name}</b>"))
        self.cnt = QLabel("0 active · 0 inactive")
        self.cnt.setStyleSheet(
            "color:#74d4cc;font-weight:bold;font-size:11px;")
        hdr.addWidget(self.cnt)
        hdr.addStretch()
        lo.addLayout(hdr)

        # ── Filter chips row ──────────────────────────────────────────────────
        lo.addLayout(self._build_filter_row())

        # ── Three-panel splitter ──────────────────────────────────────────────
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(self._build_avail_panel())
        sp.addWidget(self._build_active_panel())
        self.preview = PreviewPanel(self)
        sp.addWidget(self.preview)
        sp.setSizes([240, 320, 260])
        lo.addWidget(sp, 1)

        lo.addLayout(self._build_bottom_bar())

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)

        self.filter_btn = QPushButton("Filter ▼")
        self.filter_btn.setCheckable(True)
        self.filter_btn.setChecked(False)
        self.filter_btn.setFixedHeight(22)
        self.filter_btn.setStyleSheet(
            "font-size:10px; padding:1px 8px; border-radius:3px;")
        self.filter_btn.setToolTip(
            "Toggle filter — show only mods matching active categories")
        self.filter_btn.clicked.connect(self._on_filter_toggle)
        row.addWidget(self.filter_btn)

        _chip_order = [
            ('error',       'ERR',   '#ff4444'),
            ('dep',         'DEP',   '#ff8800'),
            ('warning',     'WARN',  '#ff8800'),
            ('order',       'ORDER', '#ffaa00'),
            ('performance', 'PERF',  '#ffaa00'),
            ('info',        'INFO',  '#888888'),
        ]

        self._chip_btns: dict[str, QPushButton] = {}

        for cat, label, color in _chip_order:
            btn = QPushButton(f"{label}  0")
            btn.setCheckable(True)
            btn.setChecked(cat in self._filter_cats)
            btn.setFixedHeight(22)
            btn.setProperty('cat',   cat)
            btn.setProperty('label', label)
            btn.setProperty('color', color)
            btn.setToolTip(self._chip_tooltip(cat))
            btn.clicked.connect(
                lambda checked, c=cat: self._on_chip_toggle(c, checked))
            self._chip_btns[cat] = btn
            row.addWidget(btn)
            self._style_chip(btn, cat in self._filter_cats, 0)

        row.addStretch()
        return row

    def _chip_tooltip(self, cat: str) -> str:
        return {
            'error':       'Critical errors — not on disk, missing deps, incompatible mods',
            'dep':         'Dependencies — dep exists but not active',
            'warning':     'Compatibility — version mismatch, unstable, better alternative exists',
            'order':       'Load order — loadAfter/loadBefore violations',
            'performance': 'Performance — JuMLi community performance notices',
            'info':        'Info — settings advice from JuMLi',
        }.get(cat, cat)

    def _style_chip(self, btn: QPushButton, active: bool, count: int):
        """Apply visual style to a chip button based on active state and count."""
        label = btn.property('label')
        color = btn.property('color')

        btn.setText(f"{label} {count}")

        if count == 0:
            # No issues of this type — always dim regardless of active state
            btn.setStyleSheet(
                "font-size:10px; padding:1px 6px; border-radius:3px; "
                "background:#2a2a2a; color:#444444; border:1px solid #333;")
            btn.setEnabled(False)
            return

        btn.setEnabled(True)

        if active:
            # Active chip — colored background
            btn.setStyleSheet(
                f"font-size:10px; padding:1px 6px; border-radius:3px; "
                f"background:{color}; color:#1a1a1a; "
                f"font-weight:bold; border:1px solid {color};")
        else:
            # Inactive chip — dark background, colored border
            btn.setStyleSheet(
                f"font-size:10px; padding:1px 6px; border-radius:3px; "
                f"background:#2a2a2a; color:{color}; "
                f"border:1px solid {color};")
            
    def _on_filter_toggle(self, checked: bool):
        """Master filter on/off."""
        self._filter_on = checked
        self.filter_btn.setText("Filter ▲" if checked else "Filter ▼")
        self._apply_filter()

    def _on_chip_toggle(self, cat: str, checked: bool):
        if checked:
            self._filter_cats.add(cat)
        else:
            self._filter_cats.discard(cat)

        btn = self._chip_btns.get(cat)
        if btn:
            try:
                count = int(btn.text().split()[-1])
            except (ValueError, IndexError):
                count = 0
            self._style_chip(btn, checked, count)

        if self._filter_on:
            self._apply_filter()

    def _apply_filter(self):
        """Show/hide items based on current filter state."""
        if not self._filter_on:
            self.active.filter_by_ids(None)
            return

        if not self._filter_cats:
            # No categories active — show nothing (all filtered out)
            self.active.filter_by_ids(set())
            return

        ids = get_issue_mod_ids(
            self.active.get_ids(), self.all_mods,
            self.inst.rimworld_version or '',
            ignored_deps=self._ignored_deps_set(),
            active_cats=self._filter_cats)
        self.active.filter_by_ids(ids)

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
        b.addWidget(self._btn("Scan Defs",  self._open_def_scan))
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

    # ── Def Scanner ────────────────────────────────────────────────────────────

    def _open_def_scan(self):
        from app.ui.modeditor.def_scan_dialog import DefScanDialog
        from PyQt6.QtWidgets import QMessageBox

        active_ids = self.active.get_ids()
        if not active_ids:
            QMessageBox.information(
                self, "Scan Defs", "No active mods to scan.")
            return

        # Build active-only subset of all_mods for the scanner
        active_mods = {
            mid: self.all_mods[mid]
            for mid in active_ids
            if mid in self.all_mods
        }

        game_version = self.inst.rimworld_version or '1.6'
        # Extract major.minor (e.g. '1.6' from '1.6.4630 rev467')
        parts = game_version.split('.')
        if len(parts) >= 2:
            game_version = f"{parts[0]}.{parts[1]}"

        dlg = DefScanDialog(self, active_mods, game_version)
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
        counts  = count_issues(
            ids, self.all_mods,
            self.inst.rimworld_version or '',
            ignored_deps=ignored)

        # Update chip labels and styles
        for cat, btn in self._chip_btns.items():
            chip_n = counts.get(cat, 0)
            self._style_chip(btn, cat in self._filter_cats, chip_n)

        # Update master filter button color
        worst_color = format_issue_color(counts)
        if self._filter_on:
            self.filter_btn.setStyleSheet(
                f"font-size:10px; padding:1px 8px; border-radius:3px; "
                f"background:{worst_color}; color:#1a1a1a; font-weight:bold;")
        else:
            self.filter_btn.setStyleSheet(
                f"font-size:10px; padding:1px 8px; border-radius:3px; "
                f"color:{worst_color};")

        # Re-apply filter if on (counts may have changed)
        if self._filter_on:
            self._apply_filter()

    def _update_empty_hint(self):
        has_non_dlc = any(
            self.avail.item(i).data(Qt.ItemDataRole.UserRole)
            not in VANILLA_AND_DLCS
            for i in range(self.avail.count()))
        self.empty_hint.setVisible(
            self.avail.count() == 0 or not has_non_dlc)