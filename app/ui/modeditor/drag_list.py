"""Drag-and-drop list widget supporting cross-list transfer and internal reorder."""

from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView
from PyQt6.QtCore import Qt, pyqtSignal


class DragDropList(QListWidget):
    items_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.partner: 'DragDropList | None' = None
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def set_partner(self, other: 'DragDropList'):
        self.partner = other

    def dropEvent(self, event):
        src = event.source()
        if src is self:
            super().dropEvent(event)
            self.items_changed.emit()
        elif src is self.partner:
            for item in src.selectedItems():
                new = QListWidgetItem(item.text())
                new.setData(Qt.ItemDataRole.UserRole, item.data(Qt.ItemDataRole.UserRole))
                new.setForeground(item.foreground())
                new.setToolTip(item.toolTip())

                drop_row = self.row(self.itemAt(event.position().toPoint()))
                if drop_row >= 0:
                    self.insertItem(drop_row, new)
                else:
                    self.addItem(new)
                src.takeItem(src.row(item))

            event.acceptProposedAction()
            self.items_changed.emit()
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
        return [self.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.count())
                if self.item(i).data(Qt.ItemDataRole.UserRole)]

    def filter_text(self, query: str):
        q = query.lower()
        for i in range(self.count()):
            self.item(i).setHidden(q not in self.item(i).text().lower())

    def filter_by_ids(self, ids: set[str] | None):
        """Show only items whose mod_id is in ids. None = show all."""
        for i in range(self.count()):
            item = self.item(i)
            if ids is None:
                item.setHidden(False)
            else:
                mid = item.data(Qt.ItemDataRole.UserRole)
                item.setHidden(mid not in ids)