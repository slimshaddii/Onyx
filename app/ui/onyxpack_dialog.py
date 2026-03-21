"""Export and Import dialogs for .onyx modpack files."""

from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QCheckBox, QGroupBox, QGridLayout,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt  # pylint: disable=no-name-in-module

from app.core.app_settings import AppSettings
from app.core.instance import Instance
from app.core.onyxpack import (
    export_onyx, peek_onyx, check_onyx_mods,
    import_onyx, OnyxPreview, ONYX_EXTENSION,
)
from app.core.rimworld import RimWorldDetector


def _extra_mod_paths() -> list[str]:
    """Collect extra mod scan paths from settings."""
    s = AppSettings.instance()
    paths: list[str] = []
    if s.steam_workshop_path:
        paths.append(s.steam_workshop_path)
    dr = s.data_root
    if dr:
        onyx_dir = str(Path(dr) / 'onyx_mods')
        paths.append(onyx_dir)
    return paths


class OnyxExportDialog(QDialog):
    """Dialog for exporting an instance as an .onyx modpack file."""

    def __init__(self, parent, instance: Instance,
                 rw: RimWorldDetector):
        super().__init__(parent)
        self.inst = instance
        self.rw   = rw
        self.author_input: QLineEdit | None = None
        self.desc_input:   QTextEdit | None  = None
        self.config_cb:    QCheckBox | None  = None
        self.setWindowTitle(f"Export .onyx — {instance.name}")
        self.setMinimumWidth(480)
        self._build()

    def _build(self):
        """Build the export dialog UI."""
        lo = QVBoxLayout(self)
        lo.setSpacing(8)

        info = QGroupBox("Pack Info")
        gl   = QGridLayout()
        gl.setVerticalSpacing(6)

        rows = [
            ("Instance:",      f"<b>{self.inst.name}</b>"),
            ("Active mods:",   str(self.inst.mod_count)),
            ("Inactive mods:", str(len(self.inst.inactive_mods))),
            ("Version:",       self.inst.rimworld_version or '—'),
        ]
        for r, (label, value) in enumerate(rows):
            gl.addWidget(QLabel(label), r, 0)
            gl.addWidget(QLabel(value), r, 1)

        gl.addWidget(QLabel("Author:"), len(rows), 0)
        self.author_input = QLineEdit()
        self.author_input.setPlaceholderText("Your name (optional)")
        gl.addWidget(self.author_input, len(rows), 1)

        gl.addWidget(QLabel("Description:"), len(rows) + 1, 0)
        self.desc_input = QTextEdit()
        self.desc_input.setMaximumHeight(80)
        self.desc_input.setPlainText(self.inst.notes or '')
        gl.addWidget(self.desc_input, len(rows) + 1, 1)

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
        """Run the export and report result."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save .onyx",
            f"{self.inst.name}{ONYX_EXTENSION}",
            f"Onyx Packs (*{ONYX_EXTENSION});;All Files (*)")
        if not path:
            return
        if not path.endswith(ONYX_EXTENSION):
            path += ONYX_EXTENSION

        all_mods = self.rw.get_installed_mods(
            extra_mod_paths=_extra_mod_paths())
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
    """Shows a preview of an .onyx pack and imports it as a new instance.

    Parameters
    ----------
    dl_queue : DownloadQueue | None
        If supplied, missing Workshop mods are offered for auto-download
        after import. Pass None to skip the download offer.
    """

    def __init__(self, parent, onyx_path: Path,
                 rw: RimWorldDetector, instance_manager,
                 dl_queue=None):
        super().__init__(parent)
        self.onyx_path  = onyx_path
        self.rw         = rw
        self.im         = instance_manager
        self.dl_queue   = dl_queue
        self._preview: OnyxPreview | None = None

        self.created_instance = None
        self.missing_mods: list     = []

        self._info_labels: dict[str, QLabel] = {}
        self.desc_label:    QLabel | None     = None
        self.name_input:    QLineEdit | None  = None
        self.status_label:  QLabel | None     = None
        self.mod_list:      QListWidget | None = None
        self.config_cb:     QCheckBox | None  = None
        self.warning_label: QLabel | None     = None
        self.error_label:   QLabel | None     = None
        self.import_btn:    QPushButton | None = None

        self.setWindowTitle("Import .onyx — Onyx Launcher")
        self.setMinimumSize(560, 520)
        self._build()
        self._load_preview()

    def _build(self):
        """Build the import dialog UI."""
        lo = QVBoxLayout(self)
        lo.setSpacing(8)

        info = QGroupBox("Pack Info")
        grid = QGridLayout()
        grid.setVerticalSpacing(4)
        for row, key in enumerate(
                ('Name', 'Author', 'Version',
                 'Active', 'Inactive', 'Created')):
            lbl = QLabel(f"{key}:")
            lbl.setStyleSheet("font-weight:bold;color:#8a8ea0;")
            val = QLabel("—")
            grid.addWidget(lbl, row, 0)
            grid.addWidget(val, row, 1)
            self._info_labels[key] = val
        info.setLayout(grid)
        lo.addWidget(info)

        self.desc_label = QLabel("")
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet(
            "color:#aaa;font-size:11px;")
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
        self.mod_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        ml.addWidget(self.mod_list)
        mod_group.setLayout(ml)
        lo.addWidget(mod_group, 1)

        self.config_cb = QCheckBox("Import config files")
        self.config_cb.setChecked(True)
        lo.addWidget(self.config_cb)

        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet(
            "color:#ffaa00;font-weight:bold;")
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        lo.addWidget(self.warning_label)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(
            "color:#ff4444;font-weight:bold;")
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
        """Load and display the .onyx pack preview."""
        preview = peek_onyx(self.onyx_path)
        if not preview.valid:
            self.error_label.setText(f"❌ {preview.error}")
            self.error_label.show()
            self.import_btn.setEnabled(False)
            return

        installed = self.rw.get_installed_mods(
            extra_mod_paths=_extra_mod_paths())
        preview   = check_onyx_mods(preview, installed)
        self._preview = preview
        m = preview.manifest

        self._populate_info_labels(m, preview)
        self._populate_mod_list(preview, set(installed.keys()))
        self._populate_warnings(preview)

    def _populate_info_labels(self, m, preview: OnyxPreview) -> None:
        """Fill the info grid labels from manifest data."""
        self._info_labels['Name'].setText(
            f"<b>{m.name}</b>" if m.name else "—")
        self._info_labels['Author'].setText(m.author or "—")
        self._info_labels['Version'].setText(
            m.rimworld_version or "—")

        n_active = sum(1 for mod in preview.mods if mod.required)
        n_inactive = sum(
            1 for mod in preview.mods if not mod.required)
        self._info_labels['Active'].setText(str(n_active))
        self._info_labels['Inactive'].setText(str(n_inactive))

        if m.created:
            try:
                dt = datetime.fromisoformat(m.created)
                self._info_labels['Created'].setText(
                    dt.strftime("%b %d, %Y %H:%M"))
            except ValueError:
                self._info_labels['Created'].setText(
                    m.created[:16])

        if m.description:
            self.desc_label.setText(m.description[:300])

        self.name_input.setText(m.name or self.onyx_path.stem)

        if not preview.has_config:
            self.config_cb.setEnabled(False)
            self.config_cb.setChecked(False)
            self.config_cb.setText(
                "Import config files (not included in pack)")

    def _populate_mod_list(self, preview: OnyxPreview,
                           installed_set: set[str]) -> None:
        """Fill the mod QListWidget from preview data."""
        self.mod_list.clear()
        for mod in preview.mods:
            found  = mod.id in installed_set
            color  = '#81c784' if found else '#ff6b6b'
            icon   = '✅' if found else '❌'
            suffix = '' if mod.required else '  (inactive)'
            text   = f"{icon}  {mod.name}  [{mod.id}]{suffix}"
            tooltip = (f"Workshop ID: {mod.workshop_id}"
                       if not found and mod.workshop_id else '')

            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, mod.id)
            if tooltip:
                it.setToolTip(tooltip)
            self.mod_list.addItem(it)

            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"color:{color}; background:transparent; "
                f"padding:2px 5px;")
            if tooltip:
                lbl.setToolTip(tooltip)
            self.mod_list.setItemWidget(it, lbl)

    def _populate_warnings(self, preview: OnyxPreview) -> None:
        """Show status counts and missing-mod warnings."""
        n_inst = len(preview.installed_mods)
        n_miss = len(preview.missing_mods)
        self.status_label.setText(
            f"<span style='color:#81c784'>"
            f"✅ {n_inst} installed</span>  "
            f"<span style='color:#ff6b6b'>"
            f"❌ {n_miss} missing</span>  "
            f"<span style='color:#888'>"
            f"({len(preview.mods)} total)</span>")

        if n_miss > 0:
            ws_count = sum(
                1 for mod in preview.missing_mods
                if mod.workshop_id)
            msg = f"⚠ {n_miss} mod(s) not installed."
            if ws_count:
                msg += f" {ws_count} available on Workshop."
                if self.dl_queue:
                    msg += " You can download them after import."
            self.warning_label.setText(msg)
            self.warning_label.show()

    def _do_import(self):
        """Validate and run the import."""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(
                self, "Error", "Enter an instance name.")
            return
        if self.im.instance_exists(name):
            QMessageBox.warning(
                self, "Error", f"'{name}' already exists.")
            return

        inst, missing, error = import_onyx(
            self.onyx_path, self.im, name,
            install_config=self.config_cb.isChecked())

        if error:
            QMessageBox.critical(self, "Import Failed", error)
            return

        self.created_instance = inst
        self.missing_mods     = missing

        lines = [f"✅ Created instance '{name}'"]
        if inst:
            lines.append(
                f"  Active: {inst.mod_count} mods")
            if inst.inactive_mods:
                lines.append(
                    f"  Inactive: {len(inst.inactive_mods)} mods")
        if missing:
            lines.append(
                f"\n⚠ {len(missing)} mod(s) not installed:")
            for mod in missing[:5]:
                lines.append(f"  • {mod.name} [{mod.id}]")
            if len(missing) > 5:
                lines.append(
                    f"  … and {len(missing) - 5} more")

        downloadable = [
            mod for mod in missing if mod.workshop_id]

        if (downloadable and self.dl_queue
                and self.dl_queue.is_configured):
            lines.append(
                f"\n{len(downloadable)} mod(s) can be "
                f"downloaded from Workshop.")
            msg = '\n'.join(lines)
            reply = QMessageBox.question(
                self, "Import Complete — Download Missing?",
                msg + "\n\nDownload missing mods now?",
                (QMessageBox.StandardButton.Yes
                 | QMessageBox.StandardButton.No),
                QMessageBox.StandardButton.Yes)

            if reply == QMessageBox.StandardButton.Yes:
                self.accept()
                self._queue_downloads(downloadable)
                return
        else:
            if downloadable and not self.dl_queue:
                lines.append(
                    "\nTip: Configure SteamCMD in Settings "
                    "to auto-download missing mods.")
            QMessageBox.information(
                self, "Import Complete", '\n'.join(lines))

        self.accept()

    def _queue_downloads(self, mods: list):
        """Show download manager for missing mods."""
        from app.ui.modeditor.download_manager import DownloadManagerWindow  # pylint: disable=import-outside-toplevel

        _s = AppSettings.instance()
        if not _s.steamcmd_path or not Path(
                _s.steamcmd_path).exists():
            QMessageBox.warning(
                self, "SteamCMD Not Configured",
                "Set the SteamCMD path in Settings to "
                "download mods.")
            return

        pairs = [(mod.workshop_id, mod.name)
                 for mod in mods if mod.workshop_id]
        if not pairs:
            return

        mgr = DownloadManagerWindow(self.dl_queue, self)
        mgr.queue_and_show(pairs)

    def _on_downloads_complete(self, results: list):
        """Handle download completion results."""
        ok  = sum(1 for _, s, _ in results if s)
        bad = len(results) - ok
        if ok and bad:
            QMessageBox.information(
                self, "Downloads Complete",
                f"Downloaded {ok} mod(s).\n{bad} failed.")
        elif ok:
            QMessageBox.information(
                self, "Downloads Complete",
                f"Downloaded {ok} mod(s) successfully.")
        elif bad:
            QMessageBox.warning(
                self, "Downloads Failed",
                f"All {bad} download(s) failed.\n"
                "Check SteamCMD configuration in Settings.")
