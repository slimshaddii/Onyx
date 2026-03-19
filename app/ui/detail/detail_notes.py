"""
Notes GroupBox with 800 ms debounced autosave.

The parent (InstanceDetailPanel) owns the Instance reference;
this widget calls inst.save() directly after updating inst.notes.
"""

from typing import Optional

from PyQt6.QtCore import QTimer  # pylint: disable=no-name-in-module
from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QWidget, QVBoxLayout, QTextEdit, QGroupBox,
)

from app.core.instance import Instance


class DetailNotes(QWidget):
    """
    Notes panel with an 800 ms debounced autosave.

    Text changes are debounced so that rapid keystrokes do not trigger
    a save on every character; the save fires 800 ms after the last change.
    Signals are blocked during programmatic text updates to prevent
    spurious autosaves.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)

        notes_group = QGroupBox("Notes")
        nl          = QVBoxLayout()

        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(90)
        self.notes_edit.setPlaceholderText("Instance notes...")
        self.notes_edit.setEnabled(False)
        nl.addWidget(self.notes_edit)
        notes_group.setLayout(nl)
        lo.addWidget(notes_group)

        self._inst: Optional[Instance] = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(800)
        self._timer.timeout.connect(self._autosave)

        self.notes_edit.textChanged.connect(self._timer.start)

    def set_instance(self, inst: Instance) -> None:
        """Load notes from inst and enable editing."""
        self._inst = inst
        self.notes_edit.setEnabled(True)
        self.notes_edit.blockSignals(True)
        self.notes_edit.setPlainText(inst.notes or '')
        self.notes_edit.blockSignals(False)

    def clear(self) -> None:
        """Clear the notes field and disable editing."""
        self._inst = None
        self.notes_edit.setEnabled(False)
        self.notes_edit.blockSignals(True)
        self.notes_edit.setPlainText('')
        self.notes_edit.blockSignals(False)

    def _autosave(self) -> None:
        if self._inst:
            self._inst.notes = self.notes_edit.toPlainText()
            self._inst.save()
