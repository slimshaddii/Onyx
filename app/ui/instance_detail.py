from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QGroupBox, QGridLayout, QDialog, QLineEdit,
    QFileDialog, QComboBox, QMessageBox, QScrollArea
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from app.core.instance import Instance
from app.core.instance_manager import InstanceManager
from app.core.rimworld import RimWorldDetector
from app.core.modlist import get_vanilla_modlist, parse_rimsort_modlist
from app.utils.file_utils import human_size, get_folder_size


class InstanceDetailPanel(QWidget):
    launch_requested = pyqtSignal(object)
    edit_mods_requested = pyqtSignal(object)
    duplicate_requested = pyqtSignal(object)
    delete_requested = pyqtSignal(object)
    export_pack_requested = pyqtSignal(object)
    instance_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_instance = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        self._notes_timer = QTimer(self)
        self._notes_timer.setSingleShot(True)
        self._notes_timer.setInterval(800)
        self._notes_timer.timeout.connect(self._do_save_notes)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.content = QWidget()
        self.cl = QVBoxLayout(self.content)
        self.cl.setSpacing(10)

        self.name_label = QLabel("Select an instance")
        self.name_label.setObjectName("heading")
        self.cl.addWidget(self.name_label)

        self.path_label = QLabel("")
        self.path_label.setObjectName("statLabel")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.cl.addWidget(self.path_label)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.launch_btn = QPushButton("▶  Launch")
        self.launch_btn.setObjectName("primaryButton")
        self.launch_btn.clicked.connect(self._emit_launch)
        btn_row.addWidget(self.launch_btn)

        self.edit_mods_btn = QPushButton("📦  Edit Mods")
        self.edit_mods_btn.clicked.connect(self._emit_edit_mods)
        btn_row.addWidget(self.edit_mods_btn)

        self.duplicate_btn = QPushButton("📋  Duplicate")
        self.duplicate_btn.clicked.connect(self._emit_dup)
        btn_row.addWidget(self.duplicate_btn)

        self.folder_btn = QPushButton("📁  Folder")
        self.folder_btn.clicked.connect(self._open_folder)
        btn_row.addWidget(self.folder_btn)

        self.export_pack_btn = QPushButton("◆")
        self.export_pack_btn.setFixedWidth(42)
        self.export_pack_btn.setToolTip("Export as .onyx pack")
        self.export_pack_btn.clicked.connect(self._emit_export_pack)
        btn_row.addWidget(self.export_pack_btn)

        self.delete_btn = QPushButton("🗑")
        self.delete_btn.setObjectName("dangerButton")
        self.delete_btn.setFixedWidth(42)
        self.delete_btn.setToolTip("Delete this instance")
        self.delete_btn.clicked.connect(self._emit_del)
        btn_row.addWidget(self.delete_btn)

        self.cl.addLayout(btn_row)

        # Details
        det_group = QGroupBox("Details")
        det_grid = QGridLayout()
        det_grid.setVerticalSpacing(6)

        self._det_labels = {}
        for row, key in enumerate([
            'Version', 'Active Mods', 'Inactive Mods', 'Save Files',
            'Instance Size', 'Created', 'Last Played', 'Playtime'
        ]):
            lbl = QLabel(f"{key}:")
            lbl.setStyleSheet("font-weight:bold; color:#8a8ea0;")
            val = QLabel("-")
            det_grid.addWidget(lbl, row, 0)
            det_grid.addWidget(val, row, 1)
            self._det_labels[key] = val

        det_group.setLayout(det_grid)
        self.cl.addWidget(det_group)

        self.missing_label = QLabel("")
        self.missing_label.setStyleSheet("color:#c62828; font-weight:bold;")
        self.missing_label.setWordWrap(True)
        self.missing_label.hide()
        self.cl.addWidget(self.missing_label)

        # Saves
        saves_group = QGroupBox("Saves")
        self.saves_layout = QVBoxLayout()
        saves_group.setLayout(self.saves_layout)
        self.cl.addWidget(saves_group)

        # Notes
        notes_group = QGroupBox("Notes")
        nl = QVBoxLayout()
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(90)
        self.notes_edit.setPlaceholderText("Instance notes...")
        self.notes_edit.textChanged.connect(self._notes_timer.start)
        nl.addWidget(self.notes_edit)
        notes_group.setLayout(nl)
        self.cl.addWidget(notes_group)

        self.cl.addStretch()
        scroll.setWidget(self.content)
        layout.addWidget(scroll)
        self._set_enabled(False)

    def _set_enabled(self, on):
        for w in (self.launch_btn, self.edit_mods_btn, self.duplicate_btn,
                  self.delete_btn, self.folder_btn, self.notes_edit,
                  self.export_pack_btn):
            w.setEnabled(on)

    def clear(self):
        self.current_instance = None
        self.name_label.setText("Select an instance")
        self.path_label.setText("")
        self._set_enabled(False)

    def set_instance(self, inst: Instance, rw: RimWorldDetector = None):
        self.current_instance = inst
        self._set_enabled(True)
        self.name_label.setText(inst.name)
        self.path_label.setText(str(inst.path))

        d = self._det_labels
        d['Version'].setText(inst.rimworld_version or '—')
        d['Active Mods'].setText(str(inst.mod_count))
        d['Inactive Mods'].setText(str(len(inst.inactive_mods)))
        d['Save Files'].setText(str(inst.save_count))
        try:
            import threading
            def _calc_size():
                try:
                    size = get_folder_size(inst.path)
                    d['Instance Size'].setText(human_size(size))
                except Exception:
                    d['Instance Size'].setText('—')
            threading.Thread(target=_calc_size, daemon=True).start()
        except Exception:
            d['Instance Size'].setText('—')
        d['Created'].setText(self._fmt_date(inst.created))
        d['Last Played'].setText(self._fmt_date(inst.last_played) or 'Never')
        h, m = divmod(inst.total_playtime_minutes, 60)
        d['Playtime'].setText(f"{h}h {m}m" if h else f"{m}m")

        if rw and inst.mods:
            missing = rw.find_missing_mods(inst.mods)
            if missing:
                self.missing_label.setText(
                    f"⚠ {len(missing)} mod(s) missing: " +
                    ", ".join(missing[:8]) +
                    (f" +{len(missing)-8} more" if len(missing) > 8 else ""))
                self.missing_label.show()
            else:
                self.missing_label.hide()
        else:
            self.missing_label.hide()

        while self.saves_layout.count():
            child = self.saves_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        saves = inst.get_save_files()
        if saves:
            for s in saves[:8]:
                row = QHBoxLayout()
                row.addWidget(QLabel(f"📄 {s['name']}"))
                row.addStretch()
                row.addWidget(QLabel(human_size(s['size'])))
                w = QWidget()
                w.setLayout(row)
                self.saves_layout.addWidget(w)
            if len(saves) > 8:
                self.saves_layout.addWidget(QLabel(f"… +{len(saves)-8} more"))
        else:
            self.saves_layout.addWidget(QLabel("No saves yet"))

        self.notes_edit.blockSignals(True)
        self.notes_edit.setPlainText(inst.notes or '')
        self.notes_edit.blockSignals(False)

    @staticmethod
    def _fmt_date(iso: str) -> str:
        if not iso:
            return ''
        try:
            return datetime.fromisoformat(iso).strftime("%b %d, %Y  %H:%M")
        except (ValueError, TypeError):
            return iso[:16]

    def _emit_launch(self):
        if self.current_instance:
            self.launch_requested.emit(self.current_instance)

    def _emit_edit_mods(self):
        if self.current_instance:
            self.edit_mods_requested.emit(self.current_instance)

    def _emit_dup(self):
        if self.current_instance:
            self.duplicate_requested.emit(self.current_instance)

    def _emit_del(self):
        if self.current_instance:
            self.delete_requested.emit(self.current_instance)

    def _emit_export_pack(self):
        if self.current_instance:
            self.export_pack_requested.emit(self.current_instance)

    def _open_folder(self):
        if self.current_instance:
            import os, subprocess
            p = str(self.current_instance.path)
            if os.name == 'nt':
                subprocess.Popen(['explorer', p])
            else:
                subprocess.Popen(['xdg-open', p])

    def _do_save_notes(self):
        if self.current_instance:
            self.current_instance.notes = self.notes_edit.toPlainText()
            self.current_instance.save()


class NewInstanceDialog(QDialog):
    def __init__(self, parent, rw: RimWorldDetector, mgr: InstanceManager):
        super().__init__(parent)
        self.rw = rw
        self.mgr = mgr
        self.setWindowTitle("New Instance")
        self.setMinimumWidth(480)
        self._build()

    def _build(self):
        lo = QVBoxLayout(self)

        lo.addWidget(QLabel("Instance Name:"))
        self.name_in = QLineEdit()
        self.name_in.setPlaceholderText("My Playthrough")
        lo.addWidget(self.name_in)

        lo.addWidget(QLabel("Template:"))
        self.tmpl = QComboBox()
        self.tmpl.addItems([
            "Vanilla (Core only)",
            "Vanilla + All DLCs",
            "Import from RimSort .txt",
            "Import from ModsConfig.xml",
            "Copy existing instance",
            "Empty (no mods)",
            "Import from .onyx pack",
        ])
        self.tmpl.currentIndexChanged.connect(self._tmpl_changed)
        lo.addWidget(self.tmpl)

        self.import_row = QWidget()
        ir = QHBoxLayout(self.import_row)
        ir.setContentsMargins(0, 0, 0, 0)
        self.import_path = QLineEdit()
        self.import_path.setPlaceholderText("File path...")
        ir.addWidget(self.import_path)
        b = QPushButton("Browse")
        b.clicked.connect(self._browse_import)
        ir.addWidget(b)
        self.import_row.hide()
        lo.addWidget(self.import_row)

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

    def _tmpl_changed(self, idx):
        self.import_row.setVisible(idx in (2, 3, 6))
        self.copy_row.setVisible(idx == 4)
        if idx == 6:
            self.name_in.setPlaceholderText("(set during import)")
        else:
            self.name_in.setPlaceholderText("My Playthrough")

    def _browse_import(self):
        idx = self.tmpl.currentIndex()
        if idx == 2:
            p, _ = QFileDialog.getOpenFileName(self, "RimSort list", "", "Text (*.txt)")
        elif idx == 6:
            p, _ = QFileDialog.getOpenFileName(
                self, "Import .onyx", "",
                "Onyx Packs (*.onyx);;All Files (*)")
        else:
            p, _ = QFileDialog.getOpenFileName(self, "ModsConfig.xml", "", "XML (*.xml)")
        if p:
            self.import_path.setText(p)

    def _create(self):
        name = self.name_in.text().strip()
        notes = self.notes_in.toPlainText().strip()
        idx = self.tmpl.currentIndex()

        if idx == 6:
            p = self.import_path.text().strip()
            if not p:
                QMessageBox.warning(self, "Error", "Select an .onyx file.")
                return
            from app.ui.onyxpack_dialog import OnyxImportDialog
            dlg = OnyxImportDialog(self, Path(p), self.rw, self.mgr)
            if dlg.exec():
                self.accept()
            return

        if not name:
            QMessageBox.warning(self, "Error", "Enter a name.")
            return

        try:
            if idx == 0:
                self.mgr.create_vanilla_instance(name)
                inst = Instance.load(self.mgr.instances_root / name)
                if inst:
                    inst.notes = notes
                    inst.save()
            elif idx == 1:
                dlcs = self.rw.get_detected_dlcs()
                self.mgr.create_vanilla_instance(name, dlcs)
                inst = Instance.load(self.mgr.instances_root / name)
                if inst:
                    inst.notes = notes
                    inst.save()
            elif idx == 2:
                p = self.import_path.text().strip()
                if not p:
                    QMessageBox.warning(self, "Error", "Select a file.")
                    return
                mods = parse_rimsort_modlist(p)
                if not mods:
                    QMessageBox.warning(self, "Error", "No mods found.")
                    return
                self.mgr.create_instance(name, mods=mods, notes=notes)
            elif idx == 3:
                p = self.import_path.text().strip()
                if not p:
                    QMessageBox.warning(self, "Error", "Select a file.")
                    return
                from app.core.modlist import read_mods_config
                mods, ver, _ = read_mods_config(Path(p).parent)
                self.mgr.create_instance(name, mods=mods, version=ver, notes=notes)
            elif idx == 4:
                src = self.copy_combo.currentData()
                if src:
                    new = self.mgr.duplicate_instance(src, name)
                    new.notes = notes
                    new.save()
                else:
                    QMessageBox.warning(self, "Error", "No instance to copy.")
                    return
            elif idx == 5:
                self.mgr.create_instance(name, mods=[], notes=notes)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))