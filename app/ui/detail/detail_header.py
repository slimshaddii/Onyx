"""Instance name + path display."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt


class DetailHeader(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(2)

        self.name_label = QLabel("Select an instance")
        self.name_label.setObjectName("heading")
        lo.addWidget(self.name_label)

        self.path_label = QLabel("")
        self.path_label.setObjectName("statLabel")
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lo.addWidget(self.path_label)

    def set_instance(self, name: str, path: str):
        self.name_label.setText(name)
        self.path_label.setText(path)

    def clear(self):
        self.name_label.setText("Select an instance")
        self.path_label.setText("")