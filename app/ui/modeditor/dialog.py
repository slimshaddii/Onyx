"""Mod editor dialog — per-instance mod isolation."""

from pathlib import Path

from PyQt6.QtCore import Qt  # pylint: disable=no-name-in-module
from PyQt6.QtGui import (  # pylint: disable=no-name-in-module
    QShortcut, QKeySequence,
)
from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QSplitter, QWidget,
    QMessageBox,
)

from app.core.app_settings import AppSettings
from app.core.instance import Instance
from app.core.modlist import (
    read_mods_config, VANILLA_AND_DLCS,
)
from app.core.paths import mods_dir
from app.core.rimworld import RimWorldDetector
from app.ui.modeditor.drag_list import DragDropList
from app.ui.modeditor.issue_checker import (
    get_badges, count_issues, get_issue_mod_ids,
    format_issue_color,
)
from app.ui.modeditor.item_builder import ItemBuilder
from app.ui.modeditor.mod_actions import ModActions
from app.ui.modeditor.mod_context import ModContext
from app.ui.modeditor.mod_fixes import ModFixes
from app.ui.modeditor.mod_io import ModIO
from app.ui.modeditor.preview_panel import PreviewPanel
from app.ui.styles import get_colors


# ── ModEditorDialog ──────────────────────────────────────────────────────────

class ModEditorDialog(
        ItemBuilder, ModActions, ModFixes, ModIO,
        ModContext, QDialog):
    """
    Three-panel mod editor.
    Left   — inactive mods for this instance
    Centre — active mods (drag to reorder)
    Right  — preview panel
    """

    def __init__(self, parent, instance: Instance,
                 rw: RimWorldDetector):
        QDialog.__init__(self, parent)
        self.inst = instance
        self.rw   = rw

        _s    = AppSettings.instance()
        paths = []
        if _s.data_root:
            paths.append(
                str(mods_dir(Path(_s.data_root))))
        if _s.steam_workshop_path:
            paths.append(_s.steam_workshop_path)

        self.all_mods = rw.get_installed_mods(
            extra_mod_paths=paths,
            force_rescan=True,
            max_age_seconds=30.0)
        self.names = {
            pid: info.name
            for pid, info in self.all_mods.items()
        }

        self._filter_on     = False
        self._filter_cats   = {
            'error', 'dep', 'warning', 'order',
        }
        self._defer_updates = False
        self._chip_btns: dict[str, QPushButton] = {}
        self._known_mod_ids = (
            self._load_known_mod_ids())
        self._original_mods: set[str] = set(
            instance.mods)

        # Widget attrs — assigned in _build_ui()
        self.cnt:        QLabel       | None = None
        self.preview:    PreviewPanel | None = None
        self.filter_btn: QPushButton  | None = None
        self.a_search:   QLineEdit    | None = None
        self.avail:      DragDropList | None = None
        self.empty_hint: QLabel       | None = None
        self.ac_search:  QLineEdit    | None = None
        self.active:     DragDropList | None = None

        self.setWindowTitle(
            f"Mods — {instance.name}")
        self.setMinimumSize(960, 520)
        self.resize(1040, 590)
        self._build_ui()
        self._load()

    def _load_known_mod_ids(self) -> set[str]:
        data_root = AppSettings.instance().data_root
        if not data_root:
            return set()
        try:
            from app.core.mod_cache import ModCache  # pylint: disable=import-outside-toplevel
            from app.core.paths import instances_dir  # pylint: disable=import-outside-toplevel
            from app.core.instance_manager import InstanceManager  # pylint: disable=import-outside-toplevel
            cache = ModCache(Path(data_root))
            cache.update_from_scan(self.all_mods)
            im = InstanceManager(
                instances_dir(Path(data_root)))
            cache.update_instance_mods(
                im.scan_instances())
            return cache.get_instance_mod_ids()
        except Exception:  # pylint: disable=broad-exception-caught
            # ModCache/InstanceManager failures during
            # init are non-fatal; editor can still open
            return set()

    def _ignored_deps_set(self) -> set[str]:
        return set(self.inst.ignored_deps)

    def _ignored_errors_set(self) -> set[str]:
        return set(self.inst.ignored_errors)

    # ── UI Construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        lo = QVBoxLayout(self)
        lo.setContentsMargins(6, 4, 6, 6)
        lo.setSpacing(4)

        hdr = QHBoxLayout()
        hdr.addWidget(
            QLabel(f"<b>{self.inst.name}</b>"))
        self.cnt = QLabel(
            "0 active · 0 inactive")
        self.cnt.setObjectName("subheading")
        self.cnt.setStyleSheet(
            "font-weight:bold; font-size:11px;")
        hdr.addWidget(self.cnt)
        hdr.addStretch()
        lo.addLayout(hdr)

        lo.addLayout(self._build_filter_row())

        sp = QSplitter(
            Qt.Orientation.Horizontal)
        sp.addWidget(self._build_avail_panel())
        sp.addWidget(self._build_active_panel())
        self.preview = PreviewPanel(self)
        sp.addWidget(self.preview)
        sp.setSizes([240, 320, 260])
        lo.addWidget(sp, 1)

        lo.addLayout(self._build_bottom_bar())
        self._install_shortcuts()

    def _install_shortcuts(self) -> None:
        QShortcut(
            QKeySequence("Ctrl+S"), self
        ).activated.connect(self._save)
        QShortcut(
            QKeySequence("Ctrl+Z"), self
        ).activated.connect(self._open_history)
        QShortcut(
            QKeySequence(Qt.Key.Key_Delete), self
        ).activated.connect(
            self._deactivate_selected_if_active_focused)

    def _deactivate_selected_if_active_focused(
            self) -> None:
        if self.active.hasFocus():
            self._rem_sel()

    # ── Filter Row ────────────────────────────────────────────────────────

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)

        self.filter_btn = QPushButton("Filter ▼")
        self.filter_btn.setCheckable(True)
        self.filter_btn.setChecked(False)
        self.filter_btn.setFixedHeight(22)
        self.filter_btn.setStyleSheet(
            "font-size:10px; padding:1px 8px; "
            "border-radius:3px;")
        self.filter_btn.setToolTip(
            "Toggle filter — show only mods matching "
            "active categories")
        self.filter_btn.clicked.connect(
            self._on_filter_toggle)
        row.addWidget(self.filter_btn)

        for cat, label, color in [
            ('error',       'ERR',   '#ff4444'),
            ('dep',         'DEP',   '#ff8800'),
            ('warning',     'WARN',  '#ff8800'),
            ('order',       'ORDER', '#ffaa00'),
            ('performance', 'PERF',  '#ffaa00'),
            ('info',        'INFO',  '#888888'),
        ]:
            btn = QPushButton(f"{label}  0")
            btn.setCheckable(True)
            btn.setChecked(
                cat in self._filter_cats)
            btn.setFixedHeight(22)
            btn.setProperty('cat',   cat)
            btn.setProperty('label', label)
            btn.setProperty('color', color)
            btn.setToolTip(
                self._chip_tooltip(cat))
            btn.clicked.connect(
                lambda checked, c=cat:
                    self._on_chip_toggle(
                        c, checked))
            self._chip_btns[cat] = btn
            row.addWidget(btn)
            self._style_chip(
                btn, cat in self._filter_cats, 0)

        row.addStretch()
        return row

    def _chip_tooltip(self, cat: str) -> str:
        tips = {
            'error': (
                'Critical errors — not on disk, '
                'missing deps, incompatible mods'),
            'dep': (
                'Dependencies — dep exists '
                'but not active'),
            'warning': (
                'Compatibility — version mismatch, '
                'unstable, better alternative'),
            'order': (
                'Load order — '
                'loadAfter/loadBefore violations'),
            'performance': (
                'Performance — JuMLi community '
                'performance notices'),
            'info': (
                'Info — settings advice '
                'from JuMLi'),
        }
        return tips.get(cat, cat)

    def _style_filter_btn(
            self,
            counts: dict | None = None,
    ) -> None:
        c = get_colors(
            AppSettings.instance().theme)

        if counts is None:
            counts = count_issues(
                self.active.get_ids(),
                self.all_mods,
                self.inst.rimworld_version or '',
                ignored_deps=(
                    self._ignored_deps_set()),
                ignored_errors=(
                    self._ignored_errors_set()),
            )

        worst_color = format_issue_color(counts)

        if self._filter_on:
            self.filter_btn.setText("Filter ▲")
            self.filter_btn.setStyleSheet(
                f"font-size:10px; padding:1px 8px;"
                f" border-radius:3px;"
                f" background:{worst_color};"
                f" color:{c['bg']};"
                f" font-weight:bold;"
                f" border:1px solid "
                f"{worst_color};")
        else:
            self.filter_btn.setText("Filter ▼")
            self.filter_btn.setStyleSheet(
                f"font-size:10px; padding:1px 8px;"
                f" border-radius:3px;"
                f" background:{c['bg_mid']};"
                f" color:{worst_color};"
                f" border:1px solid "
                f"{c['border']};")

    def _style_chip(self, btn: QPushButton,
                    active: bool,
                    count: int) -> None:
        c     = get_colors(
            AppSettings.instance().theme)
        label = btn.property('label')
        color = btn.property('color')

        btn.setText(f"{label} {count}")

        if count == 0:
            btn.setStyleSheet(
                f"font-size:10px; padding:1px 6px;"
                f" border-radius:3px;"
                f" background:{c['bg_mid']};"
                f" color:{c['text_dim']};"
                f" border:1px solid "
                f"{c['border']};")
            btn.setEnabled(False)
            return

        btn.setEnabled(True)

        if active:
            btn.setStyleSheet(
                f"font-size:10px; padding:1px 6px;"
                f" border-radius:3px;"
                f" background:{color};"
                f" color:{c['bg']};"
                f" font-weight:bold;"
                f" border:1px solid {color};")
        else:
            btn.setStyleSheet(
                f"font-size:10px; padding:1px 6px;"
                f" border-radius:3px;"
                f" background:{c['bg_mid']};"
                f" color:{color};"
                f" border:1px solid {color};")

    def _on_filter_toggle(
            self, checked: bool) -> None:
        self._filter_on = checked
        self._apply_filter()
        self._style_filter_btn()

    def _on_chip_toggle(self, cat: str,
                        checked: bool) -> None:
        if checked:
            self._filter_cats.add(cat)
        else:
            self._filter_cats.discard(cat)

        btn = self._chip_btns.get(cat)
        if btn:
            try:
                count = int(
                    btn.text().split()[-1])
            except (ValueError, IndexError):
                count = 0
            self._style_chip(btn, checked, count)

        if self._filter_on:
            self._apply_filter()

    def _apply_filter(self) -> None:
        if not self._filter_on:
            self.active.filter_by_ids(None)
            return
        if not self._filter_cats:
            self.active.filter_by_ids(set())
            return
        ids = get_issue_mod_ids(
            self.active.get_ids(), self.all_mods,
            self.inst.rimworld_version or '',
            ignored_deps=(
                self._ignored_deps_set()),
            active_cats=self._filter_cats,
            ignored_errors=(
                self._ignored_errors_set()))
        self.active.filter_by_ids(ids)

    # ── Avail Panel ───────────────────────────────────────────────────────

    def _build_avail_panel(self) -> QWidget:
        w  = QWidget()
        lo = QVBoxLayout(w)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(2)

        hdr = QHBoxLayout()
        hdr.addWidget(
            QLabel("Instance Mods (inactive)"))
        hdr.addStretch()
        lib_btn = QPushButton("📚 Library")
        lib_btn.setToolTip(
            "Add mods from your full library "
            "to this instance")
        lib_btn.setFixedHeight(22)
        lib_btn.setStyleSheet(
            "font-size:10px; padding:1px 8px;")
        lib_btn.clicked.connect(
            self._open_library)
        hdr.addWidget(lib_btn)
        lo.addLayout(hdr)

        self.a_search = QLineEdit()
        self.a_search.setPlaceholderText(
            "🔍 Search…")
        lo.addWidget(self.a_search)

        self.avail = DragDropList(self)
        self.avail.itemDoubleClicked.connect(
            self._add_sel)
        self.avail.currentItemChanged.connect(
            lambda c, _: self._show_preview(c))
        self.avail.items_changed.connect(
            self._on_items_changed)
        self.avail.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.avail.customContextMenuRequested.connect(
            self._ctx_avail)
        lo.addWidget(self.avail)

        self.a_search.textChanged.connect(
            self.avail.filter_text)

        self.empty_hint = QLabel(
            "<i style='font-size:10px;'>"
            "No inactive mods. "
            "Click Library to add mods.</i>")
        self.empty_hint.setObjectName("statLabel")
        self.empty_hint.setWordWrap(True)
        self.empty_hint.hide()
        lo.addWidget(self.empty_hint)

        row = QHBoxLayout()
        row.addWidget(
            self._btn("Activate →", self._add_sel))
        row.addWidget(
            self._btn("All ⇒", self._add_all))
        lo.addLayout(row)
        return w

    # ── Active Panel ──────────────────────────────────────────────────────

    def _build_active_panel(self) -> QWidget:
        w  = QWidget()
        lo = QVBoxLayout(w)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(2)
        lo.addWidget(
            QLabel("Active — drag to reorder ↕"))

        self.ac_search = QLineEdit()
        self.ac_search.setPlaceholderText(
            "🔍 Search…")
        lo.addWidget(self.ac_search)

        self.active = DragDropList(self)
        self.active.setDragDropMode(
            DragDropList.DragDropMode.DragDrop)
        self.active.itemDoubleClicked.connect(
            self._on_active_double_click)
        self.active.currentItemChanged.connect(
            lambda c, _: self._show_preview(c))
        self.active.items_changed.connect(
            self._update)
        self.active.needs_badge_refresh.connect(
            self._on_items_changed)
        self.active.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.active.customContextMenuRequested \
            .connect(self._ctx_active)
        lo.addWidget(self.active)

        self.ac_search.textChanged.connect(
            self.active.filter_text)

        row = QHBoxLayout()
        row.addWidget(
            self._btn("← Deactivate",
                       self._rem_sel))
        row.addWidget(
            self._btn("⇐ All", self._rem_all))
        row.addStretch()
        lo.addLayout(row)

        self.avail.set_partner(self.active)
        self.active.set_partner(self.avail)
        return w

    # ── Bottom Bar ────────────────────────────────────────────────────────

    def _build_bottom_bar(self) -> QHBoxLayout:
        b = QHBoxLayout()
        b.setSpacing(4)
        b.addWidget(self._btn(
            "Auto-Sort", self._sort,
            "primaryButton"))
        b.addWidget(self._btn(
            "Fix Issues", self._fix,
            "primaryButton"))
        b.addWidget(self._btn(
            "History", self._open_history))
        b.addWidget(self._btn(
            "Conflicts", self._open_conflicts))
        b.addWidget(self._btn(
            "Scan Defs", self._open_def_scan))
        b.addWidget(self._btn(
            "Vanilla", self._vanilla,
            "dangerButton"))
        b.addWidget(self._btn(
            "Import", self._import_file))
        b.addWidget(self._btn(
            "Export", self._export))
        b.addStretch()
        b.addWidget(self._btn(
            "Cancel", self.reject))
        b.addWidget(self._btn(
            "Save", self._save,
            "successButton"))
        return b

    def _btn(self, text: str, slot,
             obj: str = None) -> QPushButton:
        b = QPushButton(text)
        b.setFixedHeight(26)
        b.setStyleSheet(
            "font-size:11px; padding:2px 10px;")
        if obj:
            b.setObjectName(obj)
        b.clicked.connect(slot)
        return b

    # ── Load / Refresh ────────────────────────────────────────────────────

    def _load(self) -> None:
        mods, _, _ = read_mods_config(
            self.inst.config_dir)
        if not mods:
            mods = list(self.inst.mods)

        mods = [m.lower().strip() for m in mods]

        self._original_mods = set(mods)
        active_set          = set(mods)

        self.active.clear()
        self._batch_load_active(mods)

        self.avail.clear()
        self.avail.setUpdatesEnabled(False)
        shown: set[str] = set()

        for mid in self.inst.inactive_mods:
            if (mid not in active_set
                    and mid not in shown):
                info = self.all_mods.get(mid)
                if info:
                    self._mk_avail(mid, info)
                else:
                    self._mk_avail_missing(mid)
                shown.add(mid)

        for mid in VANILLA_AND_DLCS:
            if (mid not in active_set
                    and mid not in shown
                    and mid in self.all_mods):
                self._mk_avail(
                    mid, self.all_mods[mid])
                shown.add(mid)

        if not self.inst.mods_configured:
            for mid, info in self.all_mods.items():
                if (mid not in active_set
                        and mid not in shown):
                    self._mk_avail(mid, info)
                    shown.add(mid)

        self.avail.setUpdatesEnabled(True)
        self.avail.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _on_items_changed(self) -> None:
        self._refresh_badges()
        self.active.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _show_preview(self, item) -> None:
        if not item:
            return
        mid    = item.mid
        info   = self.all_mods.get(mid)
        order  = self.active.get_ids()
        badges = get_badges(
            mid, self.all_mods, set(order),
            self.inst.rimworld_version or '',
            order,
            ignored_deps=(
                self._ignored_deps_set()),
            ignored_errors=(
                self._ignored_errors_set()))
        self.preview.show_mod(info, mid, badges)

    # ── Dialog Launchers ──────────────────────────────────────────────────

    def _open_library(self) -> None:
        from app.ui.modeditor.library_dialog import LibraryDialog  # pylint: disable=import-outside-toplevel
        instance_ids = (
            set(self.active.get_ids())
            | set(self._avail_ids()))
        dlg = LibraryDialog(
            self, self.all_mods, instance_ids,
            self.inst.rimworld_version or '',
            rw=self.rw)
        if dlg.exec() and dlg.selected_ids:
            for mid in dlg.selected_ids:
                if (mid in self.all_mods
                        and mid not in instance_ids):
                    self._mk_avail(
                        mid, self.all_mods[mid])
            self.avail.apply_item_widgets()
            self._update_empty_hint()
            self._update()

    def _open_history(self) -> None:
        from app.core.mod_history import ModHistory  # pylint: disable=import-outside-toplevel
        from app.ui.modeditor.history_panel import HistoryDialog  # pylint: disable=import-outside-toplevel

        history = ModHistory(self.inst.path)
        if not history.snapshots:
            QMessageBox.information(
                self, "No History",
                "No snapshots recorded yet.\n\n"
                "Snapshots are saved automatically "
                "each time you save from the mod "
                "editor.")
            return

        dlg = HistoryDialog(
            self, history=history,
            current_mods=self.active.get_ids(),
            mod_names=self.names)
        if (dlg.exec()
                and dlg.rolled_back_mods is not None):
            self._apply_rollback(
                dlg.rolled_back_mods)

    def _apply_rollback(
            self, mods: list[str]) -> None:
        current_active = set(
            self.active.get_ids())
        current_avail = set(self._avail_ids())
        instance_mods = (
            current_active | current_avail)

        to_avail = [
            mid for mid in instance_mods
            if mid not in set(mods)
            and mid not in current_avail
            and mid not in VANILLA_AND_DLCS
        ]

        self.active.clear()
        self._batch_load_active(mods)

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
            f"Loaded {len(mods)} mods from "
            f"snapshot.\n\nClick Save to apply, "
            f"or Cancel to discard.")

    def _open_conflicts(self) -> None:
        from app.ui.modeditor.conflict_dialog import ConflictReportDialog  # pylint: disable=import-outside-toplevel
        ConflictReportDialog(
            self,
            active_ids=self.active.get_ids(),
            all_mods=self.all_mods,
            mod_names=self.names).exec()

    def _open_def_scan(self) -> None:
        from app.ui.modeditor.def_scan_dialog import DefScanDialog  # pylint: disable=import-outside-toplevel

        active_ids = self.active.get_ids()
        if not active_ids:
            QMessageBox.information(
                self, "Scan Defs",
                "No active mods to scan.")
            return

        active_mods = {
            mid: self.all_mods[mid]
            for mid in active_ids
            if mid in self.all_mods
        }
        game_version = (
            self.inst.rimworld_version or '1.6')
        parts = game_version.split('.')
        if len(parts) >= 2:
            game_version = (
                f"{parts[0]}.{parts[1]}")

        DefScanDialog(
            self, active_mods,
            game_version).exec()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _avail_ids(self) -> list[str]:
        return [
            self.avail.item(i).mid
            for i in range(self.avail.count())
            if (self.avail.item(i)
                and self.avail.item(i).mid)
        ]

    def _get_avail_ids(self) -> list[str]:
        return self._avail_ids()

    def _update(self) -> None:
        if self._defer_updates:
            return

        self.cnt.setText(
            f"{self.active.count()} active · "
            f"{self.avail.count()} inactive")

        counts = count_issues(
            self.active.get_ids(), self.all_mods,
            self.inst.rimworld_version or '',
            ignored_deps=(
                self._ignored_deps_set()),
            ignored_errors=(
                self._ignored_errors_set()))

        for cat, btn in self._chip_btns.items():
            self._style_chip(
                btn, cat in self._filter_cats,
                counts.get(cat, 0))

        self._style_filter_btn(counts)

        if self._filter_on:
            self._apply_filter()

    def _update_empty_hint(self) -> None:
        has_non_dlc = any(
            self.avail.item(i).mid
            not in VANILLA_AND_DLCS
            for i in range(self.avail.count())
            if self.avail.item(i))
        self.empty_hint.setVisible(
            self.avail.count() == 0
            or not has_non_dlc)
