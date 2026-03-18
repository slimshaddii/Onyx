"""Drag-and-drop list widget supporting cross-list transfer and internal reorder."""

from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

COLOR_ROLE = Qt.ItemDataRole.UserRole + 10
TEXT_ROLE  = Qt.ItemDataRole.UserRole + 11


class DragDropList(QListWidget):
    items_changed       = pyqtSignal()
    needs_badge_refresh = pyqtSignal()   # emitted after cross-list drop

    def __init__(self, parent=None):
        super().__init__(parent)
        self.partner: 'DragDropList | None' = None
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        self._change_timer = QTimer()
        self._change_timer.setSingleShot(True)
        self._change_timer.setInterval(50)
        self._change_timer.timeout.connect(self.items_changed.emit)

    def set_partner(self, other: 'DragDropList'):
        self.partner = other

    def _emit_changed(self):
        self._change_timer.start()

    def apply_item_widgets(self):
        """Apply (or update) a colored QLabel on every item."""
        for i in range(self.count()):
            item = self.item(i)
            if item is None:
                continue

            text      = item.data(TEXT_ROLE) or item.text() or ''
            color_str = item.data(COLOR_ROLE) or '#e0e0e0'
            tooltip   = item.toolTip()

            existing = self.itemWidget(item)
            if isinstance(existing, QLabel):
                existing.setText(text)
                existing.setToolTip(tooltip)
                existing.setStyleSheet(
                    f"color:{color_str}; background:transparent; padding:2px 5px;")
            else:
                lbl = QLabel(text)
                lbl.setToolTip(tooltip)
                lbl.setStyleSheet(
                    f"color:{color_str}; background:transparent; padding:2px 5px;")
                self.setItemWidget(item, lbl)

            item.setText('')

    def _snapshot_items(self) -> list[dict]:
        result = []
        for i in range(self.count()):
            it = self.item(i)
            if it is None:
                continue
            result.append({
                'text':    it.data(TEXT_ROLE) or '',
                'mid':     it.data(Qt.ItemDataRole.UserRole),
                'color':   it.data(COLOR_ROLE) or '#e0e0e0',
                'tooltip': it.toolTip(),
            })
        return result

    def _rebuild_from_snapshot(self, snapshot: list[dict]):
        self.clear()
        for data in snapshot:
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, data['mid'])
            it.setData(COLOR_ROLE, data['color'])
            it.setData(TEXT_ROLE,  data['text'])
            it.setToolTip(data['tooltip'])
            self.addItem(it)
        self.apply_item_widgets()

    def dropEvent(self, event):
        src = event.source()

        if src is self:
            super().dropEvent(event)
            self.apply_item_widgets()
            self._emit_changed()

        elif src is self.partner:
            selected = src.selectedItems()
            if not selected:
                event.ignore()
                return

            move_ids, items_data = set(), []
            for item in selected:
                mid = item.data(Qt.ItemDataRole.UserRole)
                if mid and mid.lower() == 'ludeon.rimworld':
                    continue
                items_data.append({
                    'text':    item.data(TEXT_ROLE) or '',
                    'mid':     mid,
                    'color':   item.data(COLOR_ROLE) or '#e0e0e0',
                    'tooltip': item.toolTip(),
                })
                move_ids.add(mid)

            if not items_data:
                event.ignore()
                return

            self.setUpdatesEnabled(False)
            src.setUpdatesEnabled(False)

            src_snap = [d for d in src._snapshot_items()
                        if d['mid'] not in move_ids]
            src.clear()
            for data in src_snap:
                it = QListWidgetItem()
                it.setData(Qt.ItemDataRole.UserRole, data['mid'])
                it.setData(COLOR_ROLE, data['color'])
                it.setData(TEXT_ROLE,  data['text'])
                it.setToolTip(data['tooltip'])
                src.addItem(it)

            drop_row = self.row(self.itemAt(event.position().toPoint()))
            for data in items_data:
                it = QListWidgetItem()
                it.setData(Qt.ItemDataRole.UserRole, data['mid'])
                # NOTE: Do NOT copy color/text from avail — badges will be
                # recomputed by needs_badge_refresh → _on_items_changed.
                # Set neutral defaults so apply_item_widgets renders something
                # visible while the refresh is pending.
                it.setData(COLOR_ROLE, '#e0e0e0')
                it.setData(TEXT_ROLE,  data['text'])
                it.setToolTip(data['tooltip'])
                if drop_row >= 0:
                    self.insertItem(drop_row, it)
                    drop_row += 1
                else:
                    self.addItem(it)

            src.setUpdatesEnabled(True)
            self.setUpdatesEnabled(True)

            src.apply_item_widgets()
            self.apply_item_widgets()

            event.acceptProposedAction()

            # Emit needs_badge_refresh so the dialog can recompute badges
            # for the active list (colors, [NEW], error/warn prefixes).
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

    def get_ids(self) -> list[str]:
        return [
            self.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.count())
            if self.item(i) and self.item(i).data(Qt.ItemDataRole.UserRole)
        ]

    def filter_text(self, query: str):
        q = query.lower()
        for i in range(self.count()):
            it = self.item(i)
            if it is None:
                continue
            text = (it.data(TEXT_ROLE) or it.text() or '').lower()
            it.setHidden(q not in text)

    def filter_by_ids(self, ids: set | None):
        for i in range(self.count()):
            item = self.item(i)
            if item is None:
                continue
            if ids is None:
                item.setHidden(False)
            else:
                item.setHidden(
                    item.data(Qt.ItemDataRole.UserRole) not in ids)