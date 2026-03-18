"""
New Instance dialog — choose a template and create a new instance.

Templates
---------
0  Vanilla (Core only)
1  Vanilla + All DLCs
2  Import from RimSort .txt
3  Import from ModsConfig.xml
4  Copy existing instance
5  Empty (no mods)
6  Import from .onyx pack
"""

import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QComboBox, QFileDialog, QMessageBox,
    QWidget,
)
from PyQt6.QtCore import Qt

from app.core.instance import Instance
from app.core.instance_manager import InstanceManager
from app.core.rimworld import RimWorldDetector
from app.core.modlist import parse_rimsort_modlist


class NewInstanceDialog(QDialog):
    def __init__(self, parent, rw: RimWorldDetector,
                 mgr: InstanceManager, dl_queue=None):
        super().__init__(parent)
        self.rw       = rw
        self.mgr      = mgr
        self.dl_queue = dl_queue
        self.setWindowTitle("New Instance")
        self.setMinimumWidth(480)
        self._build()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build(self):
        lo = QVBoxLayout(self)

        lo.addWidget(QLabel("Instance Name:"))
        self.name_in = QLineEdit()
        self.name_in.setPlaceholderText("My Playthrough")
        lo.addWidget(self.name_in)

        lo.addWidget(QLabel("Template:"))
        self.tmpl = QComboBox()
        self.tmpl.addItems([
            "Vanilla (Core only)",          # 0
            "Vanilla + All DLCs",           # 1
            "Import from RimSort .txt",     # 2
            "Import from ModsConfig.xml",   # 3
            "Copy existing instance",       # 4
            "Empty (no mods)",              # 5
            "Import from .onyx pack",       # 6
        ])
        self.tmpl.currentIndexChanged.connect(self._on_tmpl_changed)
        lo.addWidget(self.tmpl)

        # File-picker row (templates 2, 3, 6)
        self.import_row = QWidget()
        ir = QHBoxLayout(self.import_row)
        ir.setContentsMargins(0, 0, 0, 0)
        self.import_path = QLineEdit()
        self.import_path.setPlaceholderText("File path…")
        ir.addWidget(self.import_path)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse)
        ir.addWidget(browse)
        self.import_row.hide()
        lo.addWidget(self.import_row)

        # Instance-picker row (template 4)
        self.copy_row = QWidget()
        cr = QHBoxLayout(self.copy_row)
        cr.setContentsMargins(0, 0, 0, 0)
        self.copy_combo = QComboBox()
        for inst in self.mgr.scan_instances():
            self.copy_combo.addItem(inst.name, inst)
        cr.addWidget(self.copy_combo)
        self.copy_row.hide()
        lo.addWidget(self.copy_row)

        lo.addWidget(QLabel("Notes (optional):"))
        self.notes_in = QTextEdit()
        self.notes_in.setMaximumHeight(50)
        lo.addWidget(self.notes_in)

        btns = QHBoxLayout()
        ok = QPushButton("Create")
        ok.setObjectName("primaryButton")
        ok.clicked.connect(self._create)
        btns.addWidget(ok)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        lo.addLayout(btns)

    def _on_tmpl_changed(self, idx: int):
        self.import_row.setVisible(idx in (2, 3, 6))
        self.copy_row.setVisible(idx == 4)
        self.name_in.setPlaceholderText(
            "(set during import)" if idx == 6 else "My Playthrough")

    def _browse(self):
        idx = self.tmpl.currentIndex()
        filters = {
            2: ("RimSort list",   "Text (*.txt)"),
            3: ("ModsConfig.xml", "XML (*.xml)"),
            6: ("Onyx Pack",      "Onyx Packs (*.onyx);;All Files (*)"),
        }
        title, filt = filters.get(idx, ("File", "All Files (*)"))
        p, _ = QFileDialog.getOpenFileName(self, title, "", filt)
        if p:
            self.import_path.setText(p)

    # ── Creation dispatch ─────────────────────────────────────────────────

    def _create(self):
        idx   = self.tmpl.currentIndex()
        notes = self.notes_in.toPlainText().strip()

        # .onyx import delegates to its own dialog
        if idx == 6:
            return self._create_from_onyx()

        name = self.name_in.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Enter a name.")
            return

        handlers = {
            0: self._create_vanilla,
            1: self._create_vanilla_dlc,
            2: self._create_from_rimsort,
            3: self._create_from_modsconfig,
            4: self._create_copy,
            5: self._create_empty,
        }

        try:
            handlers[idx](name, notes)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Per-template creators ─────────────────────────────────────────────

    def _create_vanilla(self, name: str, notes: str):
        self.mgr.create_vanilla_instance(name)
        self._attach_notes(name, notes)

    def _create_vanilla_dlc(self, name: str, notes: str):
        self.mgr.create_vanilla_instance(name, self.rw.get_detected_dlcs())
        self._attach_notes(name, notes)

    def _create_from_rimsort(self, name: str, notes: str):
        p = self._require_path()
        if p is None:
            return
        mods = parse_rimsort_modlist(p)
        if not mods:
            QMessageBox.warning(self, "Error", "No mods found in file.")
            return
        self.mgr.create_instance(name, mods=mods, notes=notes)

    def _create_from_modsconfig(self, name: str, notes: str):
        p = self._require_path()
        if p is None:
            return
        from app.core.modlist import read_mods_config
        mods, ver, _ = read_mods_config(Path(p).parent)
        self.mgr.create_instance(name, mods=mods, version=ver, notes=notes)

    def _create_copy(self, name: str, notes: str):
        src = self.copy_combo.currentData()
        if not src:
            QMessageBox.warning(self, "Error", "No instance to copy.")
            return
        new = self.mgr.duplicate_instance(src, name)
        new.notes = notes
        new.save()

    def _create_empty(self, name: str, notes: str):
        self.mgr.create_instance(name, mods=[], notes=notes)

    def _create_from_onyx(self):
        p = self.import_path.text().strip()
        if not p:
            QMessageBox.warning(self, "Error", "Select an .onyx file.")
            return
        from app.ui.onyxpack_dialog import OnyxImportDialog
        dlg = OnyxImportDialog(self, Path(p), self.rw, self.mgr,
                               dl_queue=self.dl_queue)
        if dlg.exec():
            self.accept()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _require_path(self) -> str | None:
        """Return the import path or show a warning and return None."""
        p = self.import_path.text().strip()
        if not p:
            QMessageBox.warning(self, "Error", "Select a file.")
            return None
        return p

    def _attach_notes(self, name: str, notes: str):
        """Write notes to an instance that was created without them."""
        if not notes:
            return
        inst = Instance.load(self.mgr.instances_root / name)
        if inst:
            inst.notes = notes
            inst.save()