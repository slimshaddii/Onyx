"""
Drag-and-drop mod list — QListView + QAbstractListModel + QStyledItemDelegate.

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
    apply_item_widgets()   — trigger repaint
    filter_text(q)         — show/hide by text search
    filter_by_ids(ids)     — show/hide by mod id set
    set_partner(other)     — set cross-list drag partner
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import (  # pylint: disable=no-name-in-module
    Qt, QAbstractListModel, QModelIndex, QMimeData,
    QSize, QRect, QPoint, pyqtSignal, QTimer,
)
from PyQt6.QtGui import (  # pylint: disable=no-name-in-module
    QPainter, QColor, QFontMetrics,
)
from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QListView, QStyledItemDelegate, QStyleOptionViewItem,
    QAbstractItemView, QStyle,
)

from app.core.app_settings import AppSettings
from app.ui.styles import get_colors

COLOR_ROLE = Qt.ItemDataRole.UserRole + 10
TEXT_ROLE  = Qt.ItemDataRole.UserRole + 11
NEW_ROLE   = Qt.ItemDataRole.UserRole + 12
MID_ROLE   = Qt.ItemDataRole.UserRole


class ModItem:  # pylint: disable=invalid-name
    """
    Data container for one mod row. Replaces QListWidgetItem.
    Exposed via item(i), selectedItems(), takeItem(i), etc.
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

    def data(self, role: int):
        """Return display data for the given Qt item role."""
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

    def setData(self, role: int, value):  # noqa: N802
        """Set display data for the given Qt item role."""
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

    def toolTip(self) -> str:  # noqa: N802
        """Return the tooltip string."""
        return self.tooltip

    def setText(self, text: str):  # noqa: N802
        """Set the display text (ignores empty strings for compat)."""
        if text:
            self.text = text

    def setToolTip(self, tip: str):  # noqa: N802
        """Set the tooltip string."""
        self.tooltip = tip

    def setHidden(self, hidden: bool):  # noqa: N802
        """Show or hide this item."""
        self.hidden = hidden

    def isHidden(self) -> bool:  # noqa: N802
        """Return True if this item is hidden."""
        return self.hidden


class ModListModel(QAbstractListModel):  # pylint: disable=invalid-name
    """Stores ModItems. Supports drag/drop reordering via MIME data."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[ModItem] = []

    def rowCount(self, _parent: QModelIndex = QModelIndex()) -> int:  # pylint: disable=invalid-name
        """Return the number of items in the model."""
        return len(self._items)

    def data(self, index: QModelIndex,
             role: int = Qt.ItemDataRole.DisplayRole):
        """Return item data for the given index and role."""
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        return self._items[index.row()].data(role)

    def setData(self, index: QModelIndex, value,  # pylint: disable=invalid-name
                role: int = Qt.ItemDataRole.EditRole) -> bool:
        """Set item data for the given index and role."""
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return False
        self._items[index.row()].setData(role, value)
        self.dataChanged.emit(index, index, [role])
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """Return item flags (enabled, selectable, draggable, droppable)."""
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.isValid():
            base |= (Qt.ItemFlag.ItemIsDragEnabled |
                     Qt.ItemFlag.ItemIsDropEnabled)
        return base

    def supportedDropActions(self) -> Qt.DropAction:  # pylint: disable=invalid-name
        """Return supported drop actions (MoveAction only)."""
        return Qt.DropAction.MoveAction

    def mimeTypes(self) -> list[str]:  # pylint: disable=invalid-name
        """Return accepted MIME types for drag/drop."""
        return ['application/x-onyx-mod-row']

    def mimeData(self, indexes: list[QModelIndex]) -> QMimeData:  # pylint: disable=invalid-name
        """Encode selected row indices into MIME data."""
        mime = QMimeData()
        rows = sorted({i.row() for i in indexes if i.isValid()})
        mime.setData('application/x-onyx-mod-row',
                     ','.join(str(r) for r in rows).encode())
        return mime

    def dropMimeData(self, data: QMimeData, action: Qt.DropAction,  # pylint: disable=invalid-name
                     row: int, _column: int,
                     _parent: QModelIndex) -> bool:
        """Handle drop — reorder items based on MIME row data."""
        if action == Qt.DropAction.IgnoreAction:
            return True
        if not data.hasFormat('application/x-onyx-mod-row'):
            return False

        raw = data.data('application/x-onyx-mod-row').data().decode()
        src_rows  = [int(r) for r in raw.split(',') if r]
        insert_at = row if row >= 0 else len(self._items)

        moving = [self._items[r] for r in sorted(src_rows)
                  if 0 <= r < len(self._items)]

        for r in sorted(src_rows, reverse=True):
            if 0 <= r < len(self._items):
                if r < insert_at:
                    insert_at -= 1
                self._items.pop(r)

        for i, item in enumerate(moving):
            self._items.insert(insert_at + i, item)

        self.layoutChanged.emit()
        return True

    def appendItem(self, item: ModItem) -> None:  # pylint: disable=invalid-name
        """Append a ModItem to the end of the list."""
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append(item)
        self.endInsertRows()

    def removeRow(self, row: int,  # pylint: disable=invalid-name
                  parent: QModelIndex = QModelIndex()) -> bool:
        """Remove the item at the given row. Returns False if out of range."""
        if not 0 <= row < len(self._items):
            return False
        self.beginRemoveRows(parent, row, row)
        self._items.pop(row)
        self.endRemoveRows()
        return True

    def clear(self) -> None:
        """Remove all items."""
        if not self._items:
            return
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def item(self, row: int) -> Optional[ModItem]:
        """Return the ModItem at the given row, or None."""
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def indexOf(self, item: ModItem) -> int:  # pylint: disable=invalid-name
        """Return the index of item, or -1 if not found."""
        try:
            return self._items.index(item)
        except ValueError:
            return -1

    def indexOfMid(self, mid: str) -> int:  # pylint: disable=invalid-name
        """Return the index of the first item with the given package_id, or -1."""
        for i, it in enumerate(self._items):
            if it.mid == mid:
                return i
        return -1

    def allItems(self) -> list[ModItem]:  # pylint: disable=invalid-name
        """Return a copy of all items."""
        return list(self._items)

    def popAll(self) -> list[ModItem]:  # pylint: disable=invalid-name
        """Remove and return all items atomically."""
        if not self._items:
            return []
        self.beginResetModel()
        items = list(self._items)
        self._items.clear()
        self.endResetModel()
        return items


class ModDelegate(QStyledItemDelegate):
    """
    Paints each row:  ● ModName [package.id]   [NEW]

    Only called for visible rows — lazy rendering benefit.
    """

    _DOT_W      = 18
    _PILL_PAD_H = 4
    _PILL_PAD_V = 2
    _SPACING    = 6
    _ROW_H      = 26

    def sizeHint(self, option: QStyleOptionViewItem,  # pylint: disable=invalid-name
                 _index: QModelIndex) -> QSize:
        """Return the preferred row size."""
        return QSize(option.rect.width(), self._ROW_H)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex) -> None:
        """Paint one row with a colored dot, mod name, and optional NEW pill."""
        painter.save()

        c      = get_colors(AppSettings.instance().theme)
        rect   = option.rect
        color  = index.data(COLOR_ROLE) or c['item_normal']
        text   = index.data(TEXT_ROLE)  or ''
        is_new = bool(index.data(NEW_ROLE))

        if option.state & QStyle.StateFlag.State_Selected:
            bg = QColor(c['accent'])
            bg.setAlpha(60)
            painter.fillRect(rect, bg)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, QColor(c['bg_mid']))
        else:
            painter.fillRect(rect, QColor(c['bg_panel']))

        x  = rect.left() + 4
        cy = rect.center().y()

        painter.setPen(QColor(color))
        dot_font = painter.font()
        dot_font.setPointSize(7)
        painter.setFont(dot_font)
        painter.drawText(QRect(x, rect.top(), self._DOT_W, rect.height()),
                         Qt.AlignmentFlag.AlignCenter, '●')
        x += self._DOT_W + self._SPACING

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


class DragDropList(QListView):  # pylint: disable=invalid-name
    """
    Drop-in replacement for the old QListWidget-based DragDropList.

    Signals
    -------
    items_changed       — debounced, emitted after any add/remove/reorder
    needs_badge_refresh — emitted after cross-list drag
    itemDoubleClicked   — emits ModItem
    currentItemChanged  — emits (ModItem | None, ModItem | None)
    """

    items_changed       = pyqtSignal()
    needs_badge_refresh = pyqtSignal()
    itemDoubleClicked   = pyqtSignal(object)
    currentItemChanged  = pyqtSignal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.partner: DragDropList | None = None

        self._model    = ModListModel(self)
        self._delegate = ModDelegate(self)
        self.setModel(self._model)
        self.setItemDelegate(self._delegate)

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setMouseTracking(True)

        self._change_timer = QTimer(self)
        self._change_timer.setSingleShot(True)
        self._change_timer.setInterval(50)
        self._change_timer.timeout.connect(self.items_changed.emit)

        self.doubleClicked.connect(self._on_double_clicked)
        self.selectionModel().currentChanged.connect(self._on_current_changed)

        self._model.layoutChanged.connect(self._emit_changed)
        self._model.rowsInserted.connect(self._emit_changed)
        self._model.rowsRemoved.connect(self._emit_changed)

    def set_partner(self, other: DragDropList) -> None:
        """Set the partner list for cross-list drag/drop."""
        self.partner = other

    def _on_double_clicked(self, index: QModelIndex) -> None:
        item = self._model.item(index.row())
        if item:
            self.itemDoubleClicked.emit(item)

    def _on_current_changed(self, current: QModelIndex,
                             previous: QModelIndex) -> None:
        cur = self._model.item(current.row()) if current.isValid() else None
        prv = self._model.item(previous.row()) if previous.isValid() else None
        self.currentItemChanged.emit(cur, prv)

    def _emit_changed(self) -> None:
        self._change_timer.start()

    def addItem(self, item: ModItem) -> None:  # pylint: disable=invalid-name
        """Append a ModItem."""
        self._model.appendItem(item)

    def insertItem(self, row: int, item: ModItem) -> None:  # pylint: disable=invalid-name
        """Insert a ModItem at row. Appends if row is out of range."""
        if row < 0 or row >= self._model.rowCount():
            self._model.appendItem(item)
            return
        self._model.beginInsertRows(QModelIndex(), row, row)
        self._model._items.insert(row, item)  # pylint: disable=protected-access
        self._model.endInsertRows()

    def takeItem(self, row: int) -> Optional[ModItem]:  # pylint: disable=invalid-name
        """Remove and return the ModItem at row, or None if out of range."""
        item = self._model.item(row)
        if item is None:
            return None
        self._model.removeRow(row)
        return item

    def item(self, row: int) -> Optional[ModItem]:
        """Return the ModItem at row, or None."""
        return self._model.item(row)

    def count(self) -> int:
        """Return the total number of items."""
        return self._model.rowCount()

    def row(self, item: ModItem) -> int:
        """Return the index of item, or -1."""
        return self._model.indexOf(item)

    def clear(self) -> None:
        """Remove all items."""
        self._model.clear()

    def itemAt(self, pos: QPoint) -> Optional[ModItem]:  # pylint: disable=invalid-name
        """Return the ModItem at the given viewport position, or None."""
        index = self.indexAt(pos)
        if not index.isValid():
            return None
        return self._model.item(index.row())

    def selectedItems(self) -> list[ModItem]:  # pylint: disable=invalid-name
        """Return all currently selected ModItems."""
        rows = {i.row() for i in self.selectedIndexes() if i.isValid()}
        return [self._model.item(r) for r in sorted(rows)
                if self._model.item(r) is not None]

    def apply_item_widgets(self) -> None:
        """Trigger a repaint. Kept for API compatibility."""
        self.viewport().update()

    def _snapshot_items(self) -> list[dict]:
        return [
            {'text': it.text, 'mid': it.mid, 'color': it.color,
             'is_new': it.is_new, 'tooltip': it.tooltip}
            for it in self._model.allItems()
        ]

    def _rebuild_from_snapshot(self, snapshot: list[dict]) -> None:
        self._model.clear()
        for d in snapshot:
            self._model.appendItem(ModItem(
                text=d['text'], mid=d['mid'], color=d['color'],
                is_new=d.get('is_new', False), tooltip=d['tooltip']))

    def get_ids(self) -> list[str]:
        """Return ordered list of package_ids for all items."""
        return [it.mid for it in self._model.allItems() if it.mid]

    def filter_text(self, query: str) -> None:
        """Show/hide items by text match."""
        q = query.lower()
        for i in range(self._model.rowCount()):
            item = self._model.item(i)
            if item is None:
                continue
            hidden = q not in item.text.lower()
            item.setHidden(hidden)
            self.setRowHidden(i, hidden)

    def filter_by_ids(self, ids: set | None) -> None:
        """Show/hide items by package_id set. None shows all."""
        for i in range(self._model.rowCount()):
            item = self._model.item(i)
            if item is None:
                continue
            hidden = False if ids is None else item.mid not in ids
            item.setHidden(hidden)
            self.setRowHidden(i, hidden)

    def dropEvent(self, event):  # pylint: disable=invalid-name
        """Handle drop — internal reorder or cross-list transfer."""
        src = event.source()

        if src is self:
            super().dropEvent(event)
            self._emit_changed()

        elif src is self.partner:
            selected = src.selectedItems()
            if not selected:
                event.ignore()
                return

            move_items = [it for it in selected
                          if it.mid and it.mid.lower() != 'ludeon.rimworld']
            if not move_items:
                event.ignore()
                return

            move_mids = {it.mid for it in move_items}

            drop_index = self.indexAt(event.position().toPoint())
            drop_row   = (drop_index.row() if drop_index.isValid()
                          else self._model.rowCount())

            c = get_colors(AppSettings.instance().theme)

            # pylint: disable=protected-access
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
                    color=c['item_normal'], is_new=False,
                    tooltip=it.tooltip)
                row = drop_row + i
                if row >= self._model.rowCount():
                    self._model.appendItem(new_item)
                else:
                    self._model.beginInsertRows(QModelIndex(), row, row)
                    self._model._items.insert(row, new_item)
                    self._model.endInsertRows()
            # pylint: enable=protected-access

            event.acceptProposedAction()
            self.needs_badge_refresh.emit()
            self._emit_changed()
            src._emit_changed()  # pylint: disable=protected-access

        else:
            event.ignore()

    def dragEnterEvent(self, event) -> None:  # pylint: disable=invalid-name
        """Accept drag events from self or partner."""
        if event.source() in (self, self.partner):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # pylint: disable=invalid-name
        """Accept drag move events from self or partner."""
        if event.source() in (self, self.partner):
            event.acceptProposedAction()
        else:
            event.ignore()

    def popAllItems(self) -> list[ModItem]:  # pylint: disable=invalid-name
        """Remove and return all items atomically."""
        return self._model.popAll()
