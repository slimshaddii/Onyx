"""Drag-and-drop list widget supporting cross-list transfer and internal reorder."""

from PyQt6.QtWidgets import (
    QListWidget, QListWidgetItem, QAbstractItemView,
    QLabel, QWidget, QHBoxLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

COLOR_ROLE = Qt.ItemDataRole.UserRole + 10
TEXT_ROLE  = Qt.ItemDataRole.UserRole + 11
NEW_ROLE   = Qt.ItemDataRole.UserRole + 12   # bool — show [NEW] pill


class DragDropList(QListWidget):
    items_changed       = pyqtSignal()
    needs_badge_refresh = pyqtSignal()

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
        for i in range(self.count()):
            item = self.item(i)
            if item is None:
                continue

            text      = item.data(TEXT_ROLE) or item.text() or ''
            color_str = item.data(COLOR_ROLE) or '#e0e0e0'
            is_new    = bool(item.data(NEW_ROLE))
            tooltip   = item.toolTip()

            existing = self.itemWidget(item)
            if isinstance(existing, QWidget) and existing.property('onyx_item'):
                dot  = existing.findChild(QLabel, 'dot')
                name = existing.findChild(QLabel, 'name')
                pill = existing.findChild(QLabel, 'pill')
                if dot:
                    dot.setStyleSheet(
                        f"color:{color_str}; background:transparent;")
                if name:
                    name.setText(text)
                    name.setToolTip(tooltip)
                if pill:
                    pill.setVisible(is_new)
            else:
                # ── Container — must be transparent so QListWidget
                #    selection/hover highlight shows through cleanly ──────────
                container = QWidget()
                container.setProperty('onyx_item', True)
                # Transparent background — let QListWidget draw selection
                container.setAttribute(
                    Qt.WidgetAttribute.WA_TranslucentBackground, True)
                container.setStyleSheet("background:transparent;")

                row = QHBoxLayout(container)
                row.setContentsMargins(4, 0, 6, 0)   # left/right padding only
                row.setSpacing(6)
                row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

                # ── Colored dot ───────────────────────────────────────────────
                dot = QLabel("●")
                dot.setObjectName('dot')
                dot.setFixedWidth(14)
                dot.setAlignment(
                    Qt.AlignmentFlag.AlignCenter |
                    Qt.AlignmentFlag.AlignVCenter)
                dot.setStyleSheet(
                    f"color:{color_str}; background:transparent; "
                    f"font-size:9px;")
                row.addWidget(dot)

                # ── Mod name ──────────────────────────────────────────────────
                name_lbl = QLabel(text)
                name_lbl.setObjectName('name')
                name_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                name_lbl.setStyleSheet(
                    "color:#e0e0e0; background:transparent;")
                name_lbl.setToolTip(tooltip)
                row.addWidget(name_lbl, 1)

                # ── [NEW] pill ────────────────────────────────────────────────
                pill = QLabel("NEW")
                pill.setObjectName('pill')
                pill.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                pill.setStyleSheet(
                    "color:#1a1a1a; background:#74d4cc; "
                    "border-radius:3px; padding:0px 4px; "
                    "font-size:8px; font-weight:bold;")
                pill.setVisible(is_new)
                row.addWidget(pill)

                self.setItemWidget(item, container)

                # Set item height to match container
                item.setSizeHint(container.sizeHint().expandedTo(
                    __import__('PyQt6.QtCore', fromlist=['QSize']).QSize(0, 26)))

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
                'is_new':  bool(it.data(NEW_ROLE)),
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
            it.setData(NEW_ROLE,   data.get('is_new', False))
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
                    'color':   '#e0e0e0',
                    'is_new':  False,
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
                it.setData(NEW_ROLE,   data.get('is_new', False))
                it.setToolTip(data['tooltip'])
                src.addItem(it)

            drop_row = self.row(self.itemAt(event.position().toPoint()))
            for data in items_data:
                it = QListWidgetItem()
                it.setData(Qt.ItemDataRole.UserRole, data['mid'])
                it.setData(COLOR_ROLE, '#e0e0e0')
                it.setData(TEXT_ROLE,  data['text'])
                it.setData(NEW_ROLE,   False)
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