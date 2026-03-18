from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QComboBox, QFrame, QScrollArea, QMenu,
    QInputDialog, QFileDialog, QMessageBox, QColorDialog
)
from PyQt6.QtCore import pyqtSignal, Qt, QSize, QTimer
from PyQt6.QtGui import QMouseEvent, QFont, QPixmap, QAction

from app.core.instance import Instance
from app.core.icons import load_icon, generate_icon, get_color_choices


class InstanceCard(QFrame):
    clicked = pyqtSignal(object)
    double_clicked = pyqtSignal(object)
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
                lp = datetime.fromisoformat(instance.last_played).strftime("%b %d")
            except Exception:
                lp = instance.last_played[:10]
        lp_l = QLabel(lp)
        lp_l.setObjectName("cardStat")
        lp_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(lp_l)

    def set_selected(self, sel: bool):
        self.setObjectName("instanceCardSelected" if sel else "instanceCard")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.instance)
        elif e.button() == Qt.MouseButton.RightButton:
            self.context_requested.emit(self.instance, self.mapToGlobal(e.pos()))
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.instance)
        super().mouseDoubleClickEvent(e)


class InstanceGridPanel(QWidget):
    instance_selected = pyqtSignal(object)
    instance_double_clicked = pyqtSignal(object)
    rename_requested = pyqtSignal(object)
    change_icon_requested = pyqtSignal(object)
    edit_requested = pyqtSignal(object)
    launch_requested = pyqtSignal(object)
    folder_requested = pyqtSignal(object)
    export_requested = pyqtSignal(object)
    export_pack_requested = pyqtSignal(object)  # NEW
    copy_requested = pyqtSignal(object)
    delete_requested = pyqtSignal(object)

    SORTS = [
        ("Name ↑", lambda x: x.name.lower(), False),
        ("Name ↓", lambda x: x.name.lower(), True),
        ("Last Played", lambda x: x.last_played or '', True),
        ("Mods ↓", lambda x: x.mod_count, True),
        ("Saves ↓", lambda x: x.save_count, True),
        ("Newest", lambda x: x.created or '', True),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.instances: list[Instance] = []
        self._cards: list[InstanceCard] = []
        self._selected_instance: Instance | None = None
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._rebuild)
        self._build()

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
        self.sort_cb = QComboBox()
        for lbl, _, _ in self.SORTS:
            self.sort_cb.addItem(lbl)
        self.sort_cb.currentIndexChanged.connect(self._rebuild)
        self.sort_cb.setFixedWidth(110)
        filt.addWidget(self.sort_cb)
        lo.addLayout(filt)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.gc = QWidget()
        self.gl = QGridLayout(self.gc)
        self.gl.setSpacing(6)
        self.gl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.gc)
        lo.addWidget(self.scroll, 1)

    def set_instances(self, insts: list[Instance]):
        self.instances = insts
        self._rebuild()

    def _rebuild(self):
        while self.gl.count():
            w = self.gl.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._cards.clear()

        q = self.search.text().lower()
        filt = [i for i in self.instances if q in i.name.lower()]
        si = self.sort_cb.currentIndex()
        if 0 <= si < len(self.SORTS):
            _, fn, rev = self.SORTS[si]
            filt.sort(key=fn, reverse=rev)

        vw = self.scroll.viewport().width() if self.scroll.viewport().width() > 50 else 350
        cols = max(1, (vw - 6) // 158)

        for idx, inst in enumerate(filt):
            card = InstanceCard(inst)
            card.clicked.connect(self._on_click)
            card.double_clicked.connect(self.instance_double_clicked.emit)
            card.context_requested.connect(self._show_context)
            if self._selected_instance and inst is self._selected_instance:
                card.set_selected(True)
            self.gl.addWidget(card, idx // cols, idx % cols)
            self._cards.append(card)

        self.cnt.setText(f"{len(filt)}/{len(self.instances)}")

    def _on_click(self, inst):
        self._selected_instance = inst
        for c in self._cards:
            c.set_selected(c.instance is inst)
        self.instance_selected.emit(inst)

    def _show_context(self, inst: Instance, pos):
        m = QMenu(self)
        m.addAction("▶  Launch", lambda: self.instance_double_clicked.emit(inst))
        m.addSeparator()
        m.addAction("✏️  Edit…", lambda: self.edit_requested.emit(inst))
        m.addAction("🎨  Change Icon", lambda: self._change_icon(inst))
        m.addAction("✏️  Rename", lambda: self._rename(inst))
        m.addSeparator()
        m.addAction("📁  Open Folder", lambda: self.folder_requested.emit(inst))
        m.addAction("📤  Export Modlist", lambda: self.export_requested.emit(inst))
        m.addAction("📦  Export .onyx", lambda: self.export_pack_requested.emit(inst))
        m.addAction("📋  Copy Instance", lambda: self.copy_requested.emit(inst))
        m.addSeparator()
        m.addAction("🗑  Delete", lambda: self.delete_requested.emit(inst))
        m.exec(pos)

    def _rename(self, inst: Instance):
        name, ok = QInputDialog.getText(self, "Rename", "New name:", text=inst.name)
        if ok and name.strip():
            inst.name = name.strip()
            inst.save()
            self.rename_requested.emit(inst)

    def _change_icon(self, inst: Instance):
        m = QMenu(self)
        m.addAction("🎨  Pick Color…", lambda: self._pick_color(inst))
        m.addAction("🖼  Custom Image…", lambda: self._pick_image(inst))
        m.addSeparator()
        colors = get_color_choices()
        for color in colors[:10]:
            act = m.addAction("  ██  " + color)
            act.triggered.connect(lambda checked, c=color: self._set_color(inst, c))
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
            import shutil
            dest = inst.path / 'icon.png'
            shutil.copy2(path, str(dest))
            self._rebuild()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._cards:
        # Debounce: only rebuild 150ms after resize stops
            self._resize_timer.start(150)