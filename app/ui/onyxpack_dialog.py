"""Export and Import dialogs for .onyx modpack files."""

from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QCheckBox, QGroupBox, QGridLayout,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from app.core.instance import Instance
from app.core.rimworld import RimWorldDetector
from app.core.onyxpack import (
    export_onyx, peek_onyx, check_onyx_mods,
    import_onyx, OnyxPreview, ONYX_EXTENSION
)


class OnyxExportDialog(QDialog):
    def __init__(self, parent, instance: Instance, rw: RimWorldDetector):
        super().__init__(parent)
        self.inst = instance
        self.rw = rw
        self.setWindowTitle(f"Export .onyx — {instance.name}")
        self.setMinimumWidth(480)
        self._build()

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setSpacing(8)

        info = QGroupBox("Pack Info")
        gl = QGridLayout()
        gl.setVerticalSpacing(6)
        gl.addWidget(QLabel("Instance:"), 0, 0)
        gl.addWidget(QLabel(f"<b>{self.inst.name}</b>"), 0, 1)
        gl.addWidget(QLabel("Active mods:"), 1, 0)
        gl.addWidget(QLabel(f"{self.inst.mod_count}"), 1, 1)
        gl.addWidget(QLabel("Inactive mods:"), 2, 0)
        gl.addWidget(QLabel(f"{len(self.inst.inactive_mods)}"), 2, 1)
        gl.addWidget(QLabel("Version:"), 3, 0)
        gl.addWidget(QLabel(self.inst.rimworld_version or '—'), 3, 1)
        gl.addWidget(QLabel("Author:"), 4, 0)
        self.author_input = QLineEdit()
        self.author_input.setPlaceholderText("Your name (optional)")
        gl.addWidget(self.author_input, 4, 1)
        gl.addWidget(QLabel("Description:"), 5, 0)
        self.desc_input = QTextEdit()
        self.desc_input.setMaximumHeight(80)
        self.desc_input.setPlainText(self.inst.notes or '')
        gl.addWidget(self.desc_input, 5, 1)
        info.setLayout(gl)
        lo.addWidget(info)

        self.config_cb = QCheckBox("Include config files")
        lo.addWidget(self.config_cb)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        exp = QPushButton("◆ Export .onyx")
        exp.setObjectName("primaryButton")
        exp.clicked.connect(self._export)
        btns.addWidget(exp)
        lo.addLayout(btns)

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save .onyx", f"{self.inst.name}{ONYX_EXTENSION}",
            f"Onyx Packs (*{ONYX_EXTENSION});;All Files (*)")
        if not path:
            return
        if not path.endswith(ONYX_EXTENSION):
            path += ONYX_EXTENSION

        all_mods = self.rw.get_installed_mods()
        ok, msg = export_onyx(
            self.inst, Path(path), all_mods,
            include_config=self.config_cb.isChecked(),
            author=self.author_input.text().strip(),
            description=self.desc_input.toPlainText().strip())

        if ok:
            QMessageBox.information(self, "Export", f"✅ {msg}")
            self.accept()
        else:
            QMessageBox.critical(self, "Export Failed", msg)


class OnyxImportDialog(QDialog):
    def __init__(self, parent, onyx_path: Path,
                 rw: RimWorldDetector, instance_manager):
        super().__init__(parent)
        self.onyx_path = onyx_path
        self.rw = rw
        self.im = instance_manager
        self.created_instance = None
        self.missing_mods = []

        self.setWindowTitle("Import .onyx — Onyx Launcher")
        self.setMinimumSize(560, 480)
        self._build()
        self._load_preview()

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setSpacing(8)

        info = QGroupBox("Pack Info")
        self.info_grid = QGridLayout()
        self.info_grid.setVerticalSpacing(4)
        self._info_labels = {}
        for row, key in enumerate(['Name', 'Author', 'Version', 'Active', 'Inactive', 'Created']):
            lbl = QLabel(f"{key}:")
            lbl.setStyleSheet("font-weight:bold;color:#8a8ea0;")
            val = QLabel("—")
            self.info_grid.addWidget(lbl, row, 0)
            self.info_grid.addWidget(val, row, 1)
            self._info_labels[key] = val
        info.setLayout(self.info_grid)
        lo.addWidget(info)

        self.desc_label = QLabel("")
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color:#aaa;font-size:11px;")
        self.desc_label.setMaximumHeight(50)
        lo.addWidget(self.desc_label)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Instance name:"))
        self.name_input = QLineEdit()
        name_row.addWidget(self.name_input)
        lo.addLayout(name_row)

        mod_group = QGroupBox("Mods")
        ml = QVBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size:11px;")
        ml.addWidget(self.status_label)
        self.mod_list = QListWidget()
        self.mod_list.setStyleSheet("font-size:11px;")
        ml.addWidget(self.mod_list)
        mod_group.setLayout(ml)
        lo.addWidget(mod_group, 1)

        self.config_cb = QCheckBox("Import config files")
        self.config_cb.setChecked(True)
        lo.addWidget(self.config_cb)

        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color:#ffb74d;font-weight:bold;")
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        lo.addWidget(self.warning_label)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#f44336;font-weight:bold;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        lo.addWidget(self.error_label)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        self.import_btn = QPushButton("◆ Import")
        self.import_btn.setObjectName("primaryButton")
        self.import_btn.clicked.connect(self._do_import)
        btns.addWidget(self.import_btn)
        lo.addLayout(btns)

    def _load_preview(self):
        preview = peek_onyx(self.onyx_path)
        if not preview.valid:
            self.error_label.setText(f"❌ {preview.error}")
            self.error_label.show()
            self.import_btn.setEnabled(False)
            return

        installed = self.rw.get_installed_mods()
        preview = check_onyx_mods(preview, installed)
        self._preview = preview
        m = preview.manifest

        self._info_labels['Name'].setText(f"<b>{m.name}</b>" if m.name else "—")
        self._info_labels['Author'].setText(m.author or "—")
        self._info_labels['Version'].setText(m.rimworld_version or "—")
        n_active = len([mod for mod in preview.mods if mod.required])
        n_inactive = len([mod for mod in preview.mods if not mod.required])
        self._info_labels['Active'].setText(str(n_active))
        self._info_labels['Inactive'].setText(str(n_inactive))
        if m.created:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(m.created)
                self._info_labels['Created'].setText(dt.strftime("%b %d, %Y %H:%M"))
            except Exception:
                self._info_labels['Created'].setText(m.created[:16])

        if m.description:
            self.desc_label.setText(m.description[:300])
        self.name_input.setText(m.name or self.onyx_path.stem)

        if not preview.has_config:
            self.config_cb.setEnabled(False)
            self.config_cb.setChecked(False)
            self.config_cb.setText("Import config files (not included)")

        self.mod_list.clear()
        installed_set = set(installed.keys())
        for mod in preview.mods:
            found = mod.id in installed_set
            icon = "✅" if found else "❌"
            req = "" if mod.required else " (inactive)"
            it = QListWidgetItem(f"{icon}  {mod.name}  [{mod.id}]{req}")
            it.setData(Qt.ItemDataRole.UserRole, mod.id)
            it.setForeground(QColor('#81c784' if found else '#ff6b6b'))
            if not found and mod.workshop_id:
                it.setToolTip(f"Workshop ID: {mod.workshop_id}")
            self.mod_list.addItem(it)

        n_inst = len(preview.installed_mods)
        n_miss = len(preview.missing_mods)
        self.status_label.setText(
            f"<span style='color:#81c784'>✅ {n_inst} installed</span>  "
            f"<span style='color:#ff6b6b'>❌ {n_miss} missing</span>  "
            f"<span style='color:#888'>({len(preview.mods)} total)</span>")

        if n_miss > 0:
            ws = sum(1 for m in preview.missing_mods if m.workshop_id)
            msg = f"⚠ {n_miss} mod(s) not installed."
            if ws:
                msg += f" {ws} available on Workshop."
            self.warning_label.setText(msg)
            self.warning_label.show()

    def _do_import(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Enter an instance name.")
            return
        if self.im.instance_exists(name):
            QMessageBox.warning(self, "Error", f"'{name}' already exists.")
            return

        inst, missing, error = import_onyx(
            self.onyx_path, self.im, name,
            install_config=self.config_cb.isChecked())

        if error:
            QMessageBox.critical(self, "Import Failed", error)
            return

        self.created_instance = inst
        self.missing_mods = missing

        msg = f"✅ Created instance '{name}'"
        if inst:
            msg += f"\n  Active: {inst.mod_count} mods"
            msg += f"\n  Inactive: {len(inst.inactive_mods)} mods"
        if missing:
            msg += f"\n\n⚠ {len(missing)} mod(s) not installed."
        QMessageBox.information(self, "Import Complete", msg)
        self.accept()