"""
Drag-and-drop mod list — QListView + QAbstractListModel + QStyledItemDelegate.

Phase 9.1: Replaces QListWidget for RimSort-level performance.
Phase 9.4: Delegate only paints visible items — lazy badge rendering.

External API is backward-compatible with the old QListWidget-based version:
    addItem(item)          — append a ModItem
    clear()                — remove all items
    count()                — number of items
    item(i)                — ModItem at row i
    takeItem(i)            — remove and return ModItem at row i
    row(item)              — index of ModItem (-1 if not found)
    itemAt(pos)            — ModItem under QPoint pos (or None)
    selectedItems()        — list of selected ModItems
    get_ids()              — ordered list of package_ids
    apply_item_widgets()   — trigger repaint (no-op label approach gone)
    filter_text(q)         — show/hide by text search
    filter_by_ids(ids)     — show/hide by mod id set
    set_partner(other)     — set cross-list drag partner
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    Qt, QAbstractListModel, QModelIndex, QMimeData,
    QSize, QRect, QPoint, pyqtSignal, QTimer,
)
from PyQt6.QtGui import (
    QPainter, QColor, QFontMetrics, QPalette,
)
from PyQt6.QtWidgets import (
    QListView, QStyledItemDelegate, QStyleOptionViewItem,
    QAbstractItemView, QApplication, QStyle,
)

# ── Custom data roles ─────────────────────────────────────────────────────────
COLOR_ROLE = Qt.ItemDataRole.UserRole + 10
TEXT_ROLE  = Qt.ItemDataRole.UserRole + 11
NEW_ROLE   = Qt.ItemDataRole.UserRole + 12
MID_ROLE   = Qt.ItemDataRole.UserRole        # package_id


# ── Data container ────────────────────────────────────────────────────────────

class ModItem:
    """
    Replaces QListWidgetItem. Stores all display data for one mod row.
    Exposed to callers via item(i), selectedItems(), takeItem(i), etc.
    """

    def __init__(self, text: str = '', mid: str = '',
                 color: str = '#e0e0e0', tooltip: str = '',
                 is_new: bool = False):
        self.text    = text
        self.mid     = mid
        self.color   = color
        self.tooltip = tooltip
        self.is_new  = is_new
        self.hidden  = False

    # ── QListWidgetItem-compatible data API ───────────────────────────────────

    def data(self, role: int):
        if role == MID_ROLE:
            return self.mid
        if role == COLOR_ROLE:
            return self.color
        if role == TEXT_ROLE:
            return self.text
        if role == NEW_ROLE:
            return self.is_new
        if role == Qt.ItemDataRole.DisplayRole:
            return self.text
        if role == Qt.ItemDataRole.ToolTipRole:
            return self.tooltip
        return None

    def setData(self, role: int, value):
        if role == MID_ROLE:
            self.mid = value or ''
        elif role == COLOR_ROLE:
            self.color = value or '#e0e0e0'
        elif role == TEXT_ROLE:
            self.text = value or ''
        elif role == NEW_ROLE:
            self.is_new = bool(value)
        elif role == Qt.ItemDataRole.ToolTipRole:
            self.tooltip = value or ''

    def toolTip(self) -> str:
        return self.tooltip

    def setText(self, text: str):
        # QListWidgetItem compat — we store text in TEXT_ROLE
        # Callers do setText('') to clear built-in text; we ignore that.
        if text:
            self.text = text

    def setToolTip(self, tip: str):
        self.tooltip = tip

    def setHidden(self, hidden: bool):
        self.hidden = hidden

    def isHidden(self) -> bool:
        return self.hidden


# ── Model ─────────────────────────────────────────────────────────────────────

class ModListModel(QAbstractListModel):
    """
    Stores ModItems in a list. Supports drag/drop reordering via
    Qt's built-in MIME drag mechanism.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[ModItem] = []

    # ── QAbstractListModel interface ──────────────────────────────────────────

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        item = self._items[index.row()]
        return item.data(role)

    def setData(self, index: QModelIndex, value,
                role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return False
        self._items[index.row()].setData(role, value)
        self.dataChanged.emit(index, index, [role])
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.isValid():
            base |= (Qt.ItemFlag.ItemIsDragEnabled |
                     Qt.ItemFlag.ItemIsDropEnabled)
        return base

    def supportedDropActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction

    def mimeTypes(self) -> list[str]:
        return ['application/x-onyx-mod-row']

    def mimeData(self, indexes: list[QModelIndex]) -> QMimeData:
        mime = QMimeData()
        rows = sorted({i.row() for i in indexes if i.isValid()})
        mime.setData('application/x-onyx-mod-row',
                     ','.join(str(r) for r in rows).encode())
        return mime

    def dropMimeData(self, data: QMimeData, action: Qt.DropAction,
                     row: int, column: int,
                     parent: QModelIndex) -> bool:
        if action == Qt.DropAction.IgnoreAction:
            return True
        if not data.hasFormat('application/x-onyx-mod-row'):
            return False

        raw = data.data('application/x-onyx-mod-row').data().decode()
        src_rows = [int(r) for r in raw.split(',') if r]

        # Determine insertion point
        insert_at = row if row >= 0 else len(self._items)

        # Collect items to move (stable order)
        moving = [self._items[r] for r in sorted(src_rows)
                  if 0 <= r < len(self._items)]

        # Remove from current positions (high→low to preserve indices)
        for r in sorted(src_rows, reverse=True):
            if 0 <= r < len(self._items):
                # Adjust insertion point if we remove rows before it
                if r < insert_at:
                    insert_at -= 1
                self._items.pop(r)

        # Insert at destination
        for i, item in enumerate(moving):
            self._items.insert(insert_at + i, item)

        self.layoutChanged.emit()
        return True

    # ── Public item manipulation API ──────────────────────────────────────────

    def appendItem(self, item: ModItem):
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append(item)
        self.endInsertRows()

    def removeRow(self, row: int,
                  parent: QModelIndex = QModelIndex()) -> bool:
        if not (0 <= row < len(self._items)):
            return False
        self.beginRemoveRows(parent, row, row)
        self._items.pop(row)
        self.endRemoveRows()
        return True

    def clear(self):
        if not self._items:
            return
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def item(self, row: int) -> Optional[ModItem]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def indexOf(self, item: ModItem) -> int:
        try:
            return self._items.index(item)
        except ValueError:
            return -1

    def indexOfMid(self, mid: str) -> int:
        for i, it in enumerate(self._items):
            if it.mid == mid:
                return i
        return -1

    def allItems(self) -> list[ModItem]:
        return list(self._items)

    def popAll(self) -> list['ModItem']:
        if not self._items:
            return []
        self.beginResetModel()
        items = list(self._items)
        self._items.clear()
        self.endResetModel()
        return items

# ── Delegate ──────────────────────────────────────────────────────────────────

class ModDelegate(QStyledItemDelegate):
    """
    Paints each row as:   ● ModName  [package.id]       [NEW]
                           ↑ dot      ↑ name text        ↑ teal pill

    Only called for visible rows — this is the 9.4 lazy rendering benefit.
    """

    _DOT_W      = 18
    _PILL_PAD_H = 4
    _PILL_PAD_V = 2
    _SPACING    = 6
    _ROW_H      = 26

    def sizeHint(self, option: QStyleOptionViewItem,
                 index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), self._ROW_H)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
            index: QModelIndex):
        painter.save()

        from app.core.app_settings import AppSettings
        from app.ui.styles import get_colors
        c = get_colors(AppSettings.instance().theme)

        rect   = option.rect
        color  = index.data(COLOR_ROLE) or c['item_normal']
        text   = index.data(TEXT_ROLE)  or ''
        is_new = bool(index.data(NEW_ROLE))

        # ── Selection / hover / normal background ─────────────────────────
        if option.state & QStyle.StateFlag.State_Selected:
            bg = QColor(c['accent'])
            bg.setAlpha(60)
            painter.fillRect(rect, bg)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            bg = QColor(c['bg_mid'])
            painter.fillRect(rect, bg)
        else:
            painter.fillRect(rect, QColor(c['bg_panel']))

        x  = rect.left() + 4
        cy = rect.center().y()

        # ── Colored dot ───────────────────────────────────────────────────
        painter.setPen(QColor(color))
        dot_font = painter.font()
        dot_font.setPointSize(7)
        painter.setFont(dot_font)
        dot_rect = QRect(x, rect.top(), self._DOT_W, rect.height())
        painter.drawText(dot_rect, Qt.AlignmentFlag.AlignCenter, '●')
        x += self._DOT_W + self._SPACING

        # ── [NEW] pill ────────────────────────────────────────────────────
        pill_w = 0
        if is_new:
            pill_font = painter.font()
            pill_font.setPointSize(7)
            pill_font.setBold(True)
            fm       = QFontMetrics(pill_font)
            pill_w   = fm.horizontalAdvance('NEW') + self._PILL_PAD_H * 2
            pill_h   = fm.height() + self._PILL_PAD_V * 2
            pill_x   = rect.right() - pill_w - 6
            pill_y   = cy - pill_h // 2
            pill_rect = QRect(pill_x, pill_y, pill_w, pill_h)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(c['accent']))
            painter.drawRoundedRect(pill_rect, 3, 3)

            painter.setPen(QColor(c['bg']))
            painter.setFont(pill_font)
            painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, 'NEW')
            pill_w += self._SPACING

        # ── Mod name ──────────────────────────────────────────────────────
        name_font = painter.font()
        name_font.setPointSize(9)
        name_font.setBold(False)
        painter.setFont(name_font)
        painter.setPen(QColor(c['text']))

        available_w = rect.right() - x - pill_w - 4
        name_rect   = QRect(x, rect.top(), available_w, rect.height())
        fm          = QFontMetrics(name_font)
        elided      = fm.elidedText(text, Qt.TextElideMode.ElideRight,
                                    available_w)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter, elided)

        painter.restore()


# ── View (public interface) ───────────────────────────────────────────────────

class DragDropList(QListView):
    """
    Drop-in replacement for the old QListWidget-based DragDropList.

    Signals
    -------
    items_changed       — debounced, emitted after any add/remove/reorder
    needs_badge_refresh — emitted after cross-list drag to trigger badge recompute
    itemDoubleClicked   — emits ModItem (matches old QListWidget signal pattern)
    currentItemChanged  — emits (ModItem | None, ModItem | None)
    """

    items_changed       = pyqtSignal()
    needs_badge_refresh = pyqtSignal()
    itemDoubleClicked   = pyqtSignal(object)          # ModItem
    currentItemChanged  = pyqtSignal(object, object)  # new ModItem, old ModItem

    def __init__(self, parent=None):
        super().__init__(parent)
        self.partner: 'DragDropList | None' = None

        self._model    = ModListModel(self)
        self._delegate = ModDelegate(self)
        self.setModel(self._model)
        self.setItemDelegate(self._delegate)

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)

        # Mouse-over tracking for hover highlight
        self.setMouseTracking(True)

        self._change_timer = QTimer(self)
        self._change_timer.setSingleShot(True)
        self._change_timer.setInterval(50)
        self._change_timer.timeout.connect(self.items_changed.emit)

        # Wire internal signals to our compat signals
        self.doubleClicked.connect(self._on_double_clicked)
        self.selectionModel().currentChanged.connect(self._on_current_changed)

        # Track layout changes for items_changed debounce
        self._model.layoutChanged.connect(self._emit_changed)
        self._model.rowsInserted.connect(self._emit_changed)
        self._model.rowsRemoved.connect(self._emit_changed)

    # ── Partner ───────────────────────────────────────────────────────────────

    def set_partner(self, other: 'DragDropList'):
        self.partner = other

    # ── Signal adapters ───────────────────────────────────────────────────────

    def _on_double_clicked(self, index: QModelIndex):
        item = self._model.item(index.row())
        if item:
            self.itemDoubleClicked.emit(item)

    def _on_current_changed(self, current: QModelIndex,
                             previous: QModelIndex):
        cur = self._model.item(current.row()) if current.isValid() else None
        prv = self._model.item(previous.row()) if previous.isValid() else None
        self.currentItemChanged.emit(cur, prv)

    def _emit_changed(self):
        self._change_timer.start()

    # ── QListWidget-compatible item API ───────────────────────────────────────

    def addItem(self, item: ModItem):
        """Append a ModItem. Accepts ModItem (not QListWidgetItem)."""
        self._model.appendItem(item)

    def insertItem(self, row: int, item: ModItem):
        """Insert a ModItem at row. If row < 0 or > count, appends."""
        if row < 0 or row >= self._model.rowCount():
            self._model.appendItem(item)
            return
        self._model.beginInsertRows(QModelIndex(), row, row)
        self._model._items.insert(row, item)
        self._model.endInsertRows()

    def takeItem(self, row: int) -> Optional[ModItem]:
        """Remove and return ModItem at row. Returns None if out of range."""
        item = self._model.item(row)
        if item is None:
            return None
        self._model.removeRow(row)
        return item

    def item(self, row: int) -> Optional[ModItem]:
        return self._model.item(row)

    def count(self) -> int:
        return self._model.rowCount()

    def row(self, item: ModItem) -> int:
        return self._model.indexOf(item)

    def clear(self):
        self._model.clear()

    def itemAt(self, pos: QPoint) -> Optional[ModItem]:
        index = self.indexAt(pos)
        if not index.isValid():
            return None
        return self._model.item(index.row())

    def selectedItems(self) -> list[ModItem]:
        rows = {i.row() for i in self.selectedIndexes() if i.isValid()}
        return [self._model.item(r) for r in sorted(rows)
                if self._model.item(r) is not None]

    # ── apply_item_widgets compatibility ──────────────────────────────────────

    def apply_item_widgets(self):
        """
        No-op in the QListView implementation — the delegate repaints
        automatically when model data changes.
        Kept for API compatibility with callers in item_builder.py etc.
        """
        self.viewport().update()

    # ── Snapshot / rebuild (used by dropEvent cross-list) ─────────────────────

    def _snapshot_items(self) -> list[dict]:
        return [
            {
                'text':    it.text,
                'mid':     it.mid,
                'color':   it.color,
                'is_new':  it.is_new,
                'tooltip': it.tooltip,
            }
            for it in self._model.allItems()
        ]

    def _rebuild_from_snapshot(self, snapshot: list[dict]):
        self._model.clear()
        for d in snapshot:
            self._model.appendItem(ModItem(
                text=d['text'], mid=d['mid'], color=d['color'],
                is_new=d.get('is_new', False), tooltip=d['tooltip']))

    # ── ID helpers ────────────────────────────────────────────────────────────

    def get_ids(self) -> list[str]:
        return [it.mid for it in self._model.allItems() if it.mid]

    # ── Filter ────────────────────────────────────────────────────────────────

    def filter_text(self, query: str):
        q = query.lower()
        for i in range(self._model.rowCount()):
            item = self._model.item(i)
            if item is None:
                continue
            hidden = q not in item.text.lower()
            item.setHidden(hidden)
            self.setRowHidden(i, hidden)

    def filter_by_ids(self, ids: set | None):
        for i in range(self._model.rowCount()):
            item = self._model.item(i)
            if item is None:
                continue
            if ids is None:
                hidden = False
            else:
                hidden = item.mid not in ids
            item.setHidden(hidden)
            self.setRowHidden(i, hidden)

    # ── Drag / drop ───────────────────────────────────────────────────────────

    def dropEvent(self, event):
        src = event.source()

        if src is self:
            # Internal reorder — let model handle via dropMimeData
            super().dropEvent(event)
            self._emit_changed()

        elif src is self.partner:
            # Cross-list transfer
            selected = src.selectedItems()
            if not selected:
                event.ignore()
                return

            # Filter out Core
            move_items = [
                it for it in selected
                if it.mid and it.mid.lower() != 'ludeon.rimworld'
            ]
            if not move_items:
                event.ignore()
                return

            move_mids = {it.mid for it in move_items}

            # Determine drop row in destination
            drop_index = self.indexAt(event.position().toPoint())
            drop_row   = (drop_index.row()
                          if drop_index.isValid()
                          else self._model.rowCount())

            # Rebuild source without moved items
            from app.core.app_settings import AppSettings
            from app.ui.styles import get_colors
            _c = get_colors(AppSettings.instance().theme)

            src_snap = [d for d in src._snapshot_items()
                        if d['mid'] not in move_mids]
            src._model.clear()
            for d in src_snap:
                src._model.appendItem(ModItem(
                    text=d['text'], mid=d['mid'], color=d['color'],
                    is_new=d.get('is_new', False), tooltip=d['tooltip']))

            for i, it in enumerate(move_items):
                new_item = ModItem(
                    text=it.text, mid=it.mid,
                    color=_c['item_normal'], is_new=False,
                    tooltip=it.tooltip)
                row = drop_row + i
                if row >= self._model.rowCount():
                    self._model.appendItem(new_item)
                else:
                    self._model.beginInsertRows(QModelIndex(), row, row)
                    self._model._items.insert(row, new_item)
                    self._model.endInsertRows()

            event.acceptProposedAction()
            self.needs_badge_refresh.emit()
            self._emit_changed()
            src._emit_changed()

        else:
            event.ignore()

    def dragEnterEvent(self, event):
        if event.source() in (self, self.partner):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.source() in (self, self.partner):
            event.acceptProposedAction()
        else:
            event.ignore()

    def popAllItems(self) -> list[ModItem]:
        return self._model.popAll()