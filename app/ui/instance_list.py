"""Instance list panel — Prism-style grouped card grid for instance management."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QMimeData  # pylint: disable=no-name-in-module
from PyQt6.QtGui import (  # pylint: disable=no-name-in-module
    QMouseEvent, QDrag, QPainter, QColor,
)
from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QComboBox, QFrame, QScrollArea, QMenu,
    QInputDialog, QFileDialog, QMessageBox, QColorDialog,
    QSizePolicy,
)

from app.core.instance import Instance
from app.core.icons import load_icon, get_color_choices
from app.core.app_settings import AppSettings
from app.ui.styles import get_colors

_UNGROUPED_KEY = '\x00ungrouped'


class InstanceCard(QFrame):
    """Card widget representing a single instance in the grid."""

    clicked           = pyqtSignal(object)
    double_clicked    = pyqtSignal(object)
    context_requested = pyqtSignal(object, object)

    def __init__(self, instance: Instance, parent=None):
        super().__init__(parent)
        self.instance = instance
        self.setObjectName("instanceCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(148, 130)

        lo = QVBoxLayout(self)
        lo.setContentsMargins(8, 8, 8, 6)
        lo.setSpacing(2)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setFixedHeight(48)
        pm = load_icon(instance.path, instance.name, instance.icon_color)
        self.icon_label.setPixmap(pm)
        lo.addWidget(self.icon_label)

        name = QLabel(instance.name)
        name.setObjectName("cardTitle")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)
        name.setMaximumHeight(28)
        lo.addWidget(name)

        stats = QLabel(f"📦{instance.mod_count}  💾{instance.save_count}")
        stats.setObjectName("cardStat")
        stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(stats)

        lp = "Never"
        if instance.last_played:
            try:
                lp = datetime.fromisoformat(
                    instance.last_played).strftime("%b %d")
            except ValueError:
                lp = instance.last_played[:10]
        lp_l = QLabel(lp)
        lp_l.setObjectName("cardStat")
        lp_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(lp_l)

    def set_selected(self, sel: bool):
        """Apply or remove the selected visual style."""
        self.setObjectName(
            "instanceCardSelected" if sel else "instanceCard")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, e: QMouseEvent):  # pylint: disable=invalid-name
        """Emit clicked or context_requested on left/right press."""
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.instance)
        elif e.button() == Qt.MouseButton.RightButton:
            self.context_requested.emit(
                self.instance, self.mapToGlobal(e.pos()))
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e: QMouseEvent):  # pylint: disable=invalid-name
        """Emit double_clicked on left double-click."""
        if e.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.instance)
        super().mouseDoubleClickEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):  # pylint: disable=invalid-name
        """Start a drag operation when the card is dragged with the left button."""
        if not e.buttons() & Qt.MouseButton.LeftButton:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(
            'application/x-onyx-instance',
            str(self.instance.path).encode())
        drag.setMimeData(mime)

        pixmap = self.grab()
        painter = QPainter(pixmap)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.fillRect(pixmap.rect(), QColor(0, 0, 0, 180))
        painter.end()

        drag.setPixmap(pixmap)
        drag.setHotSpot(e.pos())
        drag.exec(Qt.DropAction.MoveAction)


class GroupHeader(QWidget):
    """Collapsible section header for an instance group."""

    toggle_requested = pyqtSignal(str, bool)
    rename_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, group_name: str, collapsed: bool = False,
                 _count: int = 0, parent=None):
        super().__init__(parent)
        self.group_name = group_name
        self._collapsed = collapsed
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

        lo = QHBoxLayout(self)
        lo.setContentsMargins(4, 0, 8, 0)
        lo.setSpacing(6)

        self._arrow = QLabel()
        self._arrow.setFixedWidth(14)
        lo.addWidget(self._arrow)

        self._name_lbl = QLabel()
        self._name_lbl.setFixedWidth(max(60, len(group_name) * 8))
        lo.addWidget(self._name_lbl)

        self._line = QFrame()
        self._line.setFrameShape(QFrame.Shape.HLine)
        self._line.setFrameShadow(QFrame.Shadow.Plain)
        lo.addWidget(self._line, 1)

        self._refresh_style()

    def _refresh_style(self):
        c = get_colors(AppSettings.instance().theme)
        arrow = "▶" if self._collapsed else "▼"
        self._arrow.setText(arrow)
        self._arrow.setStyleSheet(
            f"color:{c['accent']}; font-size:10px; font-weight:bold;")
        self._name_lbl.setText(self.group_name)
        self._name_lbl.setStyleSheet(
            f"color:{c['accent']}; font-size:11px; font-weight:bold;")
        self._line.setStyleSheet(
            f"color:{c['border']}; background:{c['border']};")
        self.setStyleSheet(f"QWidget {{ background:{c['bg']}; }}")

    def is_collapsed(self) -> bool:
        """Return True if this group is currently collapsed."""
        return self._collapsed

    def set_collapsed(self, val: bool):
        """Set the collapsed state and refresh the visual style."""
        self._collapsed = val
        self._refresh_style()

    def mousePressEvent(self, e: QMouseEvent):  # pylint: disable=invalid-name
        """Toggle collapse on left click; show context menu on right click."""
        if e.button() == Qt.MouseButton.LeftButton:
            self._collapsed = not self._collapsed
            self._refresh_style()
            self.toggle_requested.emit(self.group_name, self._collapsed)
        elif e.button() == Qt.MouseButton.RightButton:
            self._show_context(self.mapToGlobal(e.pos()))
        super().mousePressEvent(e)

    def _show_context(self, global_pos):
        if self.group_name == "Ungrouped":
            return
        m = QMenu(self)
        m.setStyleSheet(_menu_style())
        m.addAction("✏️  Rename…",
                    lambda: self.rename_requested.emit(self.group_name))
        m.addAction("🗑  Delete group",
                    lambda: self.delete_requested.emit(self.group_name))
        m.exec(global_pos)


class GroupCardGrid(QWidget):
    """Card grid for all instances within a single group, with drag-drop support."""

    def __init__(self, group_name: str = '', parent=None):
        super().__init__(parent)
        self.group_name  = group_name
        self._on_drop_cb = None
        self.setAcceptDrops(True)
        self._layout = QGridLayout(self)
        self._layout.setSpacing(6)
        self._layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._layout.setContentsMargins(4, 4, 4, 8)

    def set_drop_callback(self, cb):
        """Register a callback invoked when a card is dropped onto this grid."""
        self._on_drop_cb = cb

    def dragEnterEvent(self, e):  # pylint: disable=invalid-name
        """Accept drag if it carries an onyx instance payload."""
        if e.mimeData().hasFormat('application/x-onyx-instance'):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):  # pylint: disable=invalid-name
        """Keep accepting drag move while the payload is valid."""
        if e.mimeData().hasFormat('application/x-onyx-instance'):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):  # pylint: disable=invalid-name
        """Handle a dropped instance card and invoke the drop callback."""
        if not e.mimeData().hasFormat('application/x-onyx-instance'):
            e.ignore()
            return
        inst_path = e.mimeData().data(
            'application/x-onyx-instance').data().decode()
        if self._on_drop_cb:
            self._on_drop_cb(inst_path, self.group_name)
        e.acceptProposedAction()

    def populate(self, instances: list[Instance], cols: int,
                 selected: Instance | None,
                 on_click, on_double, on_context,
                 drop_callback=None):
        """Clear and rebuild all instance cards in a grid layout."""
        if drop_callback:
            self.set_drop_callback(drop_callback)

        while self._layout.count():
            w = self._layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        for idx, inst in enumerate(instances):
            card = InstanceCard(inst)
            card.clicked.connect(on_click)
            card.double_clicked.connect(on_double)
            card.context_requested.connect(on_context)
            if selected and inst is selected:
                card.set_selected(True)
            self._layout.addWidget(card, idx // cols, idx % cols)

        return self


def _menu_style() -> str:
    c = get_colors(AppSettings.instance().theme)
    return f"""
        QMenu {{
            background: {c['bg_mid']};
            border: 1px solid {c['border']};
            border-radius: 6px;
            padding: 4px 0px;
            color: {c['text']};
            font-size: 11px;
        }}
        QMenu::item {{
            padding: 6px 20px 6px 12px;
            border-radius: 4px;
            margin: 1px 4px;
        }}
        QMenu::item:selected {{
            background: {c['bg_card']};
            color: {c['accent']};
        }}
        QMenu::item:disabled {{ color: {c['text_dim']}; }}
        QMenu::separator {{
            height: 1px;
            background: {c['border']};
            margin: 3px 8px;
        }}
    """


class InstanceGridPanel(QWidget):
    """Main panel showing all instances as a grouped card grid with search and sort."""

    instance_selected       = pyqtSignal(object)
    instance_double_clicked = pyqtSignal(object)
    rename_requested        = pyqtSignal(object)
    change_icon_requested   = pyqtSignal(object)
    edit_requested          = pyqtSignal(object)
    launch_requested        = pyqtSignal(object)
    folder_requested        = pyqtSignal(object)
    export_requested        = pyqtSignal(object)
    export_pack_requested   = pyqtSignal(object)
    copy_requested          = pyqtSignal(object)
    delete_requested        = pyqtSignal(object)

    SORTS = [
        ("Name ↑",      lambda x: x.name.lower(), False),
        ("Name ↓",      lambda x: x.name.lower(), True),
        ("Last Played", lambda x: x.last_played or '', True),
        ("Mods ↓",      lambda x: x.mod_count,    True),
        ("Saves ↓",     lambda x: x.save_count,   True),
        ("Newest",      lambda x: x.created or '', True),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.instances: list[Instance]           = []
        self._cards:    list[InstanceCard]       = []
        self._selected_instance: Instance | None = None
        self._collapsed: dict[str, bool]         = {}
        self._empty_groups: set[str]             = set()
        self._last_cols: int                     = -1

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._rebuild)

        self._build()

    def _groups_path(self) -> Path | None:
        dr = AppSettings.instance().data_root
        return Path(dr) / 'groups.json' if dr else None

    def _load_empty_groups(self):
        p = self._groups_path()
        if p and p.exists():
            try:
                data = json.loads(p.read_text(encoding='utf-8'))
                self._empty_groups = set(data.get('empty_groups', []))
                return
            except (OSError, json.JSONDecodeError):
                pass
        self._empty_groups = set()

    def _save_empty_groups(self):
        p = self._groups_path()
        if not p:
            return
        try:
            p.write_text(
                json.dumps({'empty_groups': sorted(self._empty_groups)},
                           indent=2),
                encoding='utf-8')
        except OSError:
            pass

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(8, 6, 4, 6)
        lo.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(4)
        t = QLabel("Instances")
        t.setObjectName("heading")
        row.addWidget(t)
        row.addStretch()
        self.cnt = QLabel("")
        self.cnt.setObjectName("subheading")
        row.addWidget(self.cnt)
        lo.addLayout(row)

        filt = QHBoxLayout()
        filt.setSpacing(4)
        self.search = QLineEdit()
        self.search.setObjectName("searchBar")
        self.search.setPlaceholderText("🔍 Search…")
        self.search.textChanged.connect(self._rebuild)
        filt.addWidget(self.search, 1)

        self.group_filter = QComboBox()
        self.group_filter.addItem("All Groups")
        self.group_filter.currentIndexChanged.connect(self._rebuild)
        filt.addWidget(self.group_filter)

        self.sort_cb = QComboBox()
        for lbl, _, _ in self.SORTS:
            self.sort_cb.addItem(lbl)
        self.sort_cb.currentIndexChanged.connect(self._rebuild)
        self.sort_cb.setFixedWidth(110)
        filt.addWidget(self.sort_cb)
        lo.addLayout(filt)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.gc = QWidget()
        self.gc.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.gc.customContextMenuRequested.connect(
            self._show_empty_context)

        self._content_lo = QVBoxLayout(self.gc)
        self._content_lo.setContentsMargins(0, 0, 0, 0)
        self._content_lo.setSpacing(0)
        self._content_lo.addStretch()

        self.scroll.setWidget(self.gc)
        lo.addWidget(self.scroll, 1)

        self._load_empty_groups()

    def set_instances(self, insts: list[Instance]):
        """Replace the instance list, refresh the group filter, and rebuild the grid."""
        self.instances = insts
        self._load_empty_groups()

        current_group = self.group_filter.currentText()
        self.group_filter.blockSignals(True)
        self.group_filter.clear()
        self.group_filter.addItem("All Groups")
        groups = sorted(
            {i.group for i in insts if i.group} | self._empty_groups)
        for g in groups:
            self.group_filter.addItem(g)
        idx = self.group_filter.findText(current_group)
        self.group_filter.setCurrentIndex(max(0, idx))
        self.group_filter.blockSignals(False)

        self._rebuild()

    def _rebuild(self):
        self.gc.setVisible(False)

        while self._content_lo.count() > 1:
            item = self._content_lo.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._cards.clear()

        q            = self.search.text().lower()
        group_filter = self.group_filter.currentText()

        filt = [i for i in self.instances if q in i.name.lower()]
        if group_filter != "All Groups":
            filt = [i for i in filt if i.group == group_filter]

        si = self.sort_cb.currentIndex()
        if 0 <= si < len(self.SORTS):
            _, fn, rev = self.SORTS[si]
            filt.sort(key=fn, reverse=rev)

        vw   = self.scroll.viewport().width()
        vw   = vw if vw > 50 else 350
        cols = max(1, (vw - 6) // 158)

        if group_filter == "All Groups":
            self._rebuild_grouped(filt, cols)
        else:
            self._rebuild_flat(filt, cols)

        self.cnt.setText(f"{len(filt)}/{len(self.instances)}")
        self.gc.setVisible(True)

    def _rebuild_flat(self, instances: list[Instance], cols: int):
        """Populate the grid with all instances in a single ungrouped layout."""
        grid = GroupCardGrid('')
        grid.populate(
            instances, cols, self._selected_instance,
            self._on_click,
            self.instance_double_clicked.emit,
            self._show_context,
            drop_callback=self._on_card_dropped)
        # pylint: disable=protected-access
        for i in range(grid._layout.count()):
            w = grid._layout.itemAt(i).widget()
            if isinstance(w, InstanceCard):
                self._cards.append(w)
        # pylint: enable=protected-access
        self._content_lo.insertWidget(
            self._content_lo.count() - 1, grid)

    def _rebuild_grouped(self, instances: list[Instance], cols: int):
        grouped: dict[str, list[Instance]] = {}
        ungrouped: list[Instance] = []

        for inst in instances:
            if inst.group:
                grouped.setdefault(inst.group, []).append(inst)
            else:
                ungrouped.append(inst)

        all_group_names = sorted(
            set(grouped.keys()) | self._empty_groups)

        insert_pos = 0

        for group_name in all_group_names:
            group_instances = grouped.get(group_name, [])
            is_collapsed    = self._collapsed.get(group_name, False)

            hdr = GroupHeader(group_name, is_collapsed,
                              len(group_instances))
            hdr.toggle_requested.connect(self._on_group_toggle)
            hdr.rename_requested.connect(self._on_group_rename)
            hdr.delete_requested.connect(self._on_group_delete)
            self._content_lo.insertWidget(insert_pos, hdr)
            insert_pos += 1

            grid = GroupCardGrid(group_name)
            grid.populate(
                group_instances, cols, self._selected_instance,
                self._on_click,
                self.instance_double_clicked.emit,
                self._show_context,
                drop_callback=self._on_card_dropped)
            grid.setVisible(not is_collapsed)

            # pylint: disable=protected-access
            for i in range(grid._layout.count()):
                w = grid._layout.itemAt(i).widget()
                if isinstance(w, InstanceCard):
                    self._cards.append(w)
            # pylint: enable=protected-access

            self._content_lo.insertWidget(insert_pos, grid)
            insert_pos += 1

        if ungrouped or _UNGROUPED_KEY in self._collapsed:
            is_collapsed = self._collapsed.get(_UNGROUPED_KEY, False)

            hdr = GroupHeader("Ungrouped", is_collapsed, len(ungrouped))
            hdr.toggle_requested.connect(self._on_group_toggle)
            self._content_lo.insertWidget(insert_pos, hdr)
            insert_pos += 1

            grid = GroupCardGrid('')
            grid.populate(
                ungrouped, cols, self._selected_instance,
                self._on_click,
                self.instance_double_clicked.emit,
                self._show_context,
                drop_callback=self._on_card_dropped)
            grid.setVisible(not is_collapsed)
            # pylint: disable=protected-access
            for i in range(grid._layout.count()):
                w = grid._layout.itemAt(i).widget()
                if isinstance(w, InstanceCard):
                    self._cards.append(w)
            # pylint: enable=protected-access
            self._content_lo.insertWidget(insert_pos, grid)

    def _on_group_toggle(self, group_name: str, is_collapsed: bool):
        key = _UNGROUPED_KEY if group_name == "Ungrouped" else group_name
        self._collapsed[key] = is_collapsed
        for i in range(self._content_lo.count() - 1):
            w = self._content_lo.itemAt(i).widget()
            if isinstance(w, GroupHeader) and w.group_name == group_name:
                grid_item = self._content_lo.itemAt(i + 1)
                if grid_item and grid_item.widget():
                    grid_item.widget().setVisible(not is_collapsed)
                break

    def _on_group_rename(self, old_name: str):
        name, ok = QInputDialog.getText(
            self, "Rename Group", "New name:", text=old_name)
        if not ok or not name.strip() or name.strip() == old_name:
            return
        new_name = name.strip()
        for inst in self.instances:
            if inst.group == old_name:
                inst.group = new_name
                inst.save()
        if old_name in self._empty_groups:
            self._empty_groups.discard(old_name)
            self._empty_groups.add(new_name)
        if old_name in self._collapsed:
            self._collapsed[new_name] = self._collapsed.pop(old_name)
        self._save_empty_groups()
        self._rebuild()

    def _on_group_delete(self, group_name: str):
        affected = [i for i in self.instances if i.group == group_name]
        msg = (f"Delete group '{group_name}'?\n"
               f"{len(affected)} instance(s) will be ungrouped.")
        if QMessageBox.question(
                self, "Delete Group", msg,
        ) != QMessageBox.StandardButton.Yes:
            return
        for inst in affected:
            inst.group = ''
            inst.save()
        self._empty_groups.discard(group_name)
        self._collapsed.pop(group_name, None)
        self._save_empty_groups()
        self._rebuild()

    def _on_click(self, inst: Instance):
        self._selected_instance = inst
        for card in self._cards:
            card.set_selected(card.instance is inst)
        self.instance_selected.emit(inst)

    def _on_card_dropped(self, inst_path: str, target_group: str):
        inst = next(
            (i for i in self.instances if str(i.path) == inst_path),
            None)
        if inst is None or inst.group == target_group:
            return
        self._move_inst_to_group(inst, target_group)

    def _show_context(self, inst: Instance, pos):
        m = QMenu(self)
        m.setStyleSheet(_menu_style())

        m.addAction("▶  Launch",
                    lambda: self.instance_double_clicked.emit(inst))
        m.addSeparator()
        m.addAction("✏️  Edit…",   lambda: self.edit_requested.emit(inst))
        m.addAction("🎨  Change Icon", lambda: self._change_icon(inst))
        m.addAction("✏️  Rename",  lambda: self._rename(inst))
        m.addSeparator()

        all_groups = sorted(
            {i.group for i in self.instances if i.group}
            | self._empty_groups)
        move_menu = m.addMenu("📁  Move to Group")
        move_menu.setStyleSheet(_menu_style())
        move_menu.addAction("➕  New Group…",
                            lambda: self._move_to_new_group(inst))
        if all_groups:
            move_menu.addSeparator()
            for g in all_groups:
                label = f"✓  {g}" if inst.group == g else f"    {g}"
                move_menu.addAction(
                    label,
                    lambda checked=False, grp=g:
                        self._move_inst_to_group(inst, grp))
        if inst.group:
            move_menu.addSeparator()
            move_menu.addAction(
                "✕  Remove from group",
                lambda: self._move_inst_to_group(inst, ''))

        m.addSeparator()
        m.addAction("📁  Open Folder",
                    lambda: self.folder_requested.emit(inst))
        m.addAction("📤  Export Modlist",
                    lambda: self.export_requested.emit(inst))
        m.addAction("📦  Export .onyx",
                    lambda: self.export_pack_requested.emit(inst))
        m.addAction("📋  Copy Instance",
                    lambda: self.copy_requested.emit(inst))
        m.addSeparator()
        m.addAction("🗑  Delete",
                    lambda: self.delete_requested.emit(inst))
        m.exec(pos)

    def _show_empty_context(self, pos):
        m = QMenu(self)
        m.setStyleSheet(_menu_style())
        m.addAction("➕  New Group…", self._create_group)

        all_groups = sorted(
            {i.group for i in self.instances if i.group}
            | self._empty_groups)
        if all_groups:
            m.addSeparator()
            ren = m.addMenu("✏️  Rename Group…")
            ren.setStyleSheet(_menu_style())
            dlt = m.addMenu("🗑  Delete Group…")
            dlt.setStyleSheet(_menu_style())
            for g in all_groups:
                ren.addAction(g, lambda checked=False, grp=g:
                              self._on_group_rename(grp))
                dlt.addAction(g, lambda checked=False, grp=g:
                              self._on_group_delete(grp))

        m.exec(self.gc.mapToGlobal(pos))

    def _create_group(self):
        name, ok = QInputDialog.getText(
            self, "New Group", "Group name:")
        if not ok or not name.strip():
            return
        g = name.strip()
        if g in {i.group for i in self.instances} | self._empty_groups:
            QMessageBox.information(
                self, "New Group", f"Group '{g}' already exists.")
            return
        self._empty_groups.add(g)
        self._save_empty_groups()
        self._rebuild()

    def _move_to_new_group(self, inst: Instance):
        name, ok = QInputDialog.getText(
            self, "New Group", "Group name:")
        if ok and name.strip():
            self._move_inst_to_group(inst, name.strip())

    def _move_inst_to_group(self, inst: Instance, group: str):
        old_group = inst.group
        inst.group = group
        inst.save()

        if old_group:
            still_has = any(
                i.group == old_group
                for i in self.instances
                if i is not inst)
            if not still_has:
                self._empty_groups.add(old_group)

        if group:
            self._empty_groups.discard(group)

        self._save_empty_groups()
        self._rebuild()

    def _rename(self, inst: Instance):
        name, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=inst.name)
        if ok and name.strip():
            inst.name = name.strip()
            inst.save()
            self.rename_requested.emit(inst)

    def _change_icon(self, inst: Instance):
        m = QMenu(self)
        m.setStyleSheet(_menu_style())
        m.addAction("🎨  Pick Color…", lambda: self._pick_color(inst))
        m.addAction("🖼  Custom Image…", lambda: self._pick_image(inst))
        m.addSeparator()
        for color in get_color_choices()[:10]:
            act = m.addAction(f"  ██  {color}")
            act.triggered.connect(
                lambda checked=False, c=color: self._set_color(inst, c))
        m.exec(self.cursor().pos())

    def _pick_color(self, inst: Instance):
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self._set_color(inst, color.name())

    def _set_color(self, inst: Instance, color: str):
        inst.icon_color = color
        inst.save()
        self._rebuild()

    def _pick_image(self, inst: Instance):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Icon", "",
            "Images (*.png *.jpg *.jpeg *.ico *.bmp)")
        if path:
            dest = inst.path / 'icon.png'
            shutil.copy2(path, str(dest))
            self._rebuild()

    def resizeEvent(self, e):  # pylint: disable=invalid-name
        """Rebuild the grid only when the column count changes."""
        super().resizeEvent(e)
        vw       = self.scroll.viewport().width()
        vw       = vw if vw > 50 else 350
        new_cols = max(1, (vw - 6) // 158)
        if new_cols != self._last_cols:
            self._last_cols = new_cols
            if self._cards:
                self._resize_timer.start(150)
