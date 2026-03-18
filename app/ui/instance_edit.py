"""
Edit Instance window.
Tabs: Overview, Mods, Saves, Notes, Log, Settings, Ignored Deps
"""

from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QGroupBox, QGridLayout, QLineEdit, QCheckBox, QMessageBox,
    QFileDialog, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from app.core.instance import Instance
from app.core.rimworld import RimWorldDetector
from app.core.launcher import Launcher
from app.core.log_parser import LogParser
from app.core.modlist import read_mods_config, export_rimsort_modlist
from app.utils.file_utils import human_size, get_folder_size


class InstanceEditDialog(QDialog):
    instance_changed = pyqtSignal()

    def __init__(self, parent, instance: Instance,
                 rw: RimWorldDetector = None):
        super().__init__(parent)
        self.inst = instance
        self.rw   = rw
        self.setWindowTitle(f"Edit — {instance.name}")
        self.setMinimumSize(700, 520)
        self.resize(760, 580)
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(8, 8, 8, 8)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel(
            f"<b style='font-size:15px;color:#7c8aff'>{self.inst.name}</b>"))
        hdr.addStretch()
        hdr.addWidget(QLabel(
            f"📦 {self.inst.mod_count} mods  •  💾 {self.inst.save_count} saves"))
        lo.addLayout(hdr)

        tabs = QTabWidget()
        tabs.addTab(self._build_overview_tab(), "📊 Overview")
        tabs.addTab(self._build_mods_tab(),     "📦 Mods")
        tabs.addTab(self._build_saves_tab(),    "Saves")
        tabs.addTab(self._build_notes_tab(),    "Notes")
        tabs.addTab(self._build_log_tab(),      "📋 Log")
        tabs.addTab(self._build_settings_tab(), "⚙ Settings")
        tabs.addTab(self._build_ignored_tab(),  "🚫 Ignored Deps")
        lo.addWidget(tabs)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save)
        btns.addWidget(save_btn)
        lo.addLayout(btns)

    # ── Overview tab ──────────────────────────────────────────────────────

    def _build_overview_tab(self) -> QWidget:
        w  = QWidget()
        lo = QVBoxLayout(w)

        info = QGroupBox("Instance Info")
        ig   = QGridLayout()
        ig.setVerticalSpacing(4)

        fields = {
            'Path':        str(self.inst.path),
            'Version':     self.inst.rimworld_version or '—',
            'Created':     self._fmt(self.inst.created),
            'Last Played': self._fmt(self.inst.last_played) or 'Never',
            'Playtime': (
                f"{self.inst.total_playtime_minutes // 60}h "
                f"{self.inst.total_playtime_minutes % 60}m"),
            'Size': '…',
        }
        self._ig = ig  # keep ref for size update
        for r, (k, v) in enumerate(fields.items()):
            ig.addWidget(QLabel(f"<b>{k}:</b>"), r, 0)
            vl = QLabel(v)
            vl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            ig.addWidget(vl, r, 1)

        info.setLayout(ig)
        lo.addWidget(info)
        lo.addStretch()

        import threading
        def _calc():
            try:
                size = human_size(get_folder_size(self.inst.path))
            except Exception:
                size = '—'
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._set_size_label(size))
        threading.Thread(target=_calc, daemon=True).start()

        return w

    def _set_size_label(self, text: str):
        ig = self._ig
        for r in range(ig.rowCount()):
            lbl = ig.itemAtPosition(r, 0)
            if lbl and lbl.widget() and 'Size' in lbl.widget().text():
                val = ig.itemAtPosition(r, 1)
                if val and val.widget():
                    val.widget().setText(text)
                break

    # ── Mods tab ──────────────────────────────────────────────────────────

    def _build_mods_tab(self) -> QWidget:
        w  = QWidget()
        lo = QVBoxLayout(w)

        mods, _, _ = read_mods_config(self.inst.config_dir)
        lo.addWidget(QLabel(f"Active mods: {len(mods)}"))

        self.mod_list = QListWidget()
        installed = self.rw.get_installed_mods() if self.rw else {}
        for mid in mods:
            name  = installed[mid].name if mid in installed else mid
            found = mid in installed
            item  = QListWidgetItem(
                f"{'✔' if found else '✖'} {name}  [{mid}]")
            if not found:
                item.setForeground(Qt.GlobalColor.red)
            self.mod_list.addItem(item)
        lo.addWidget(self.mod_list)

        mod_btns = QHBoxLayout()
        edit_btn = QPushButton("📦 Open Mod Editor")
        edit_btn.setObjectName("primaryButton")
        edit_btn.clicked.connect(self._open_mod_editor)
        mod_btns.addWidget(edit_btn)
        exp_btn = QPushButton("📤 Export Modlist")
        exp_btn.clicked.connect(self._export_mods)
        mod_btns.addWidget(exp_btn)
        mod_btns.addStretch()
        lo.addLayout(mod_btns)
        return w

    # ── Saves tab ─────────────────────────────────────────────────────────

    def _build_saves_tab(self) -> QWidget:
        w  = QWidget()
        lo = QVBoxLayout(w)

        self.saves_list = QListWidget()
        for s in self.inst.get_save_files():
            try:
                dt = datetime.fromisoformat(
                    s['modified']).strftime("%b %d %H:%M")
            except Exception:
                dt = s['modified'][:16]
            self.saves_list.addItem(
                f"📄 {s['name']}  —  {human_size(s['size'])}  —  {dt}")
        if not self.saves_list.count():
            lo.addWidget(QLabel("No saves yet."))
        lo.addWidget(self.saves_list)

        sv_btns = QHBoxLayout()
        sv_open_btn = QPushButton("Open Saves Folder")
        sv_open_btn.clicked.connect(
            lambda: self._open_path(self.inst.saves_dir))
        sv_btns.addWidget(sv_open_btn)
        sv_btns.addStretch()
        lo.addLayout(sv_btns)
        return w

    # ── Notes tab ─────────────────────────────────────────────────────────

    def _build_notes_tab(self) -> QWidget:
        w  = QWidget()
        lo = QVBoxLayout(w)
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlainText(self.inst.notes or '')
        self.notes_edit.setPlaceholderText(
            "Write notes about this instance…")
        lo.addWidget(self.notes_edit)
        return w

    # ── Log tab ───────────────────────────────────────────────────────────

    def _build_log_tab(self) -> QWidget:
        w  = QWidget()
        lo = QVBoxLayout(w)

        log_path = self.inst.path / 'Player.log'
        if log_path.exists():
            try:
                text     = log_path.read_text(
                    encoding='utf-8', errors='replace')[-50000:]
                log_view = QTextEdit()
                log_view.setReadOnly(True)
                log_view.setPlainText(text)
                log_view.setStyleSheet(
                    "font-family:Consolas; font-size:10px;")
                lo.addWidget(log_view)
            except Exception:
                lo.addWidget(QLabel("Could not read log file."))
        else:
            lo.addWidget(QLabel(
                "No log file. Launch the game first."))

        open_log_btn = QPushButton("Open Full Log Viewer")
        open_log_btn.clicked.connect(self._open_log_viewer)
        lo.addWidget(open_log_btn)
        return w

    # ── Settings tab ─────────────────────────────────────────────────────

    def _build_settings_tab(self) -> QWidget:
        """
        Mirrors the launch-dialog checkboxes so the user can pre-configure
        arguments without launching. Also carries the remember / skip flag.
        """
        w  = QWidget()
        lo = QVBoxLayout(w)
        lo.setSpacing(8)

        # ── Launch-arg checkboxes (same source as LaunchDialog) ───────────
        common = Launcher.get_common_launch_args()

        args_group = QGroupBox("Launch Arguments")
        ag_lo      = QVBoxLayout()

        self._settings_arg_cbs:    list[tuple[QCheckBox, dict]] = []
        self._settings_arg_inputs: dict[str, QLineEdit]         = {}

        current_args = set(self.inst.launch_args)

        for a in common:
            row = QHBoxLayout()
            cb  = QCheckBox(a['arg'])
            cb.setToolTip(a['desc'])
            cb.setChecked(a['arg'] in current_args)
            row.addWidget(cb)
            row.addWidget(QLabel(a['desc']))

            if a.get('has_value'):
                vi = QLineEdit()
                vi.setFixedWidth(80)
                vi.setPlaceholderText(a.get('default', ''))
                # Find existing value in saved args
                args_list = self.inst.launch_args
                if a['arg'] in args_list:
                    try:
                        idx = args_list.index(a['arg'])
                        if idx + 1 < len(args_list):
                            vi.setText(args_list[idx + 1])
                    except ValueError:
                        pass
                row.addWidget(vi)
                self._settings_arg_inputs[a['arg']] = vi

            row.addStretch()
            self._settings_arg_cbs.append((cb, a))
            ag_lo.addLayout(row)

        # Custom args (anything not in common)
        ag_lo.addWidget(QLabel("Custom arguments:"))
        self._custom_args = QLineEdit()
        self._custom_args.setPlaceholderText("Extra arguments…")
        known        = {a['arg'] for a in common}
        custom_parts = []
        i = 0
        while i < len(self.inst.launch_args):
            arg = self.inst.launch_args[i]
            if arg not in known and arg not in self._settings_arg_inputs:
                custom_parts.append(arg)
            elif arg in self._settings_arg_inputs:
                i += 1
            i += 1
        self._custom_args.setText(' '.join(custom_parts))
        ag_lo.addWidget(self._custom_args)

        args_group.setLayout(ag_lo)
        lo.addWidget(args_group)

        # ── Remember / skip dialog flag ───────────────────────────────────
        self._remember_cb = QCheckBox(
            "Skip launch dialog (use these arguments directly)")
        self._remember_cb.setToolTip(
            "When checked, double-clicking Launch will start the game "
            "immediately using the arguments above, bypassing the dialog.")
        self._remember_cb.setChecked(self.inst.mods_configured)
        lo.addWidget(self._remember_cb)

        # ── Group / tag ───────────────────────────────────────────────────
        lo.addWidget(QLabel("Group / Tag:"))
        self.group_edit = QLineEdit()
        self.group_edit.setText(self.inst.group or '')
        self.group_edit.setPlaceholderText(
            "e.g. Vanilla, Modded, Testing")
        lo.addWidget(self.group_edit)
        lo.addWidget(QLabel(
            "<small style='color:#888;'>"
            "Common: -popupwindow, -screen-fullscreen 0, "
            "-screen-width 1920, -screen-height 1080, -force-d3d11"
            "</small>"))
        lo.addStretch()
        return w

    # ── Ignored deps tab ──────────────────────────────────────────────────

    def _build_ignored_tab(self) -> QWidget:
        """
        Shows all suppressed dependency warnings for this instance.
        Format per entry: "mod_id:dep_id"
        Displays as: "<mod name> → <dep name> [Remove]"
        """
        w  = QWidget()
        lo = QVBoxLayout(w)
        lo.setSpacing(6)

        lo.addWidget(QLabel(
            "<b>Suppressed dependency warnings</b><br>"
            "<small style='color:#888;'>"
            "These warnings are hidden in the mod editor. "
            "Remove an entry to re-enable the warning.</small>"))

        # Scroll area for the list of ignored pairs
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._ignored_container = QWidget()
        self._ignored_layout    = QVBoxLayout(self._ignored_container)
        self._ignored_layout.setSpacing(4)
        self._ignored_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._ignored_container)
        lo.addWidget(scroll, 1)

        # Populate
        self._populate_ignored()

        # Bottom: clear-all button
        clear_btn = QPushButton("🗑 Clear All")
        clear_btn.setObjectName("dangerButton")
        clear_btn.clicked.connect(self._clear_all_ignored)
        btns_row = QHBoxLayout()
        btns_row.addStretch()
        btns_row.addWidget(clear_btn)
        lo.addLayout(btns_row)
        return w

    def _populate_ignored(self):
        """Rebuild the ignored-deps list from instance data."""
        # Clear existing widgets
        while self._ignored_layout.count():
            item = self._ignored_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        installed = self.rw.get_installed_mods() if self.rw else {}

        if not self.inst.ignored_deps:
            empty = QLabel(
                "<i style='color:#555;'>No suppressed warnings.</i>")
            self._ignored_layout.addWidget(empty)
            return

        for entry in list(self.inst.ignored_deps):
            parts = entry.split(':', 1)
            if len(parts) != 2:
                continue
            mod_id, dep_id = parts

            mod_name = (installed[mod_id].name
                        if mod_id in installed else mod_id)
            dep_name = (installed[dep_id].name
                        if dep_id in installed else dep_id)

            row = QFrame()
            row.setStyleSheet(
                "QFrame { background:#2a2a2a; border-radius:4px; "
                "padding:2px; }")
            row_lo = QHBoxLayout(row)
            row_lo.setContentsMargins(8, 4, 8, 4)

            lbl = QLabel(
                f"<b>{mod_name}</b>"
                f"<span style='color:#888;'> needs </span>"
                f"<b>{dep_name}</b>"
                f"<span style='color:#555; font-size:10px;'>"
                f"  [{entry}]</span>")
            lbl.setWordWrap(True)
            row_lo.addWidget(lbl, 1)

            rem_btn = QPushButton("✕ Remove")
            rem_btn.setFixedWidth(80)
            rem_btn.setFixedHeight(22)
            rem_btn.setStyleSheet(
                "font-size:10px; padding:1px 6px; "
                "background:#3a2a2a; color:#cc6666; "
                "border:1px solid #663333; border-radius:3px;")
            # Capture entry by value
            rem_btn.clicked.connect(
                lambda checked, e=entry: self._remove_ignored(e))
            row_lo.addWidget(rem_btn)

            self._ignored_layout.addWidget(row)

    def _remove_ignored(self, entry: str):
        if entry in self.inst.ignored_deps:
            self.inst.ignored_deps.remove(entry)
            self.inst.save()
            self._populate_ignored()

    def _clear_all_ignored(self):
        if not self.inst.ignored_deps:
            return
        if QMessageBox.question(
            self, "Clear All",
            "Remove all suppressed dependency warnings?",
        ) == QMessageBox.StandardButton.Yes:
            self.inst.ignored_deps.clear()
            self.inst.save()
            self._populate_ignored()

    # ── Save ─────────────────────────────────────────────────────────────

    def _save(self):
        self.inst.notes = self.notes_edit.toPlainText()
        self.inst.group = self.group_edit.text().strip()

        # Rebuild launch_args from Settings tab checkboxes
        args: list[str] = []
        for cb, a in self._settings_arg_cbs:
            if cb.isChecked():
                args.append(a['arg'])
                if a.get('has_value') and a['arg'] in self._settings_arg_inputs:
                    v = self._settings_arg_inputs[a['arg']].text().strip()
                    args.append(v or a.get('default', ''))

        custom = self._custom_args.text().strip()
        if custom:
            args.extend(custom.split())

        self.inst.launch_args    = args
        self.inst.mods_configured = self._remember_cb.isChecked()
        self.inst.save()
        self.instance_changed.emit()
        self.accept()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _open_mod_editor(self):
        from app.ui.modeditor import ModEditorDialog
        if self.rw and ModEditorDialog(self, self.inst, self.rw).exec():
            self.instance_changed.emit()
            self.accept()

    def _export_mods(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export", "modlist.txt", "Text (*.txt)")
        if path:
            installed = self.rw.get_installed_mods() if self.rw else {}
            names     = {pid: i.name for pid, i in installed.items()}
            export_rimsort_modlist(path, self.inst.mods, names)
            QMessageBox.information(
                self, "Export", f"Exported {len(self.inst.mods)} mods.")

    def _open_log_viewer(self):
        from app.ui.log_viewer import LogViewerDialog
        LogViewerDialog(self, LogParser(), self.inst).exec()

    def _open_path(self, path: Path):
        import os
        import subprocess
        path.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            subprocess.Popen(['explorer', str(path)])
        else:
            subprocess.Popen(['xdg-open', str(path)])

    @staticmethod
    def _fmt(iso: str) -> str:
        if not iso:
            return ''
        try:
            return datetime.fromisoformat(iso).strftime("%b %d, %Y  %H:%M")
        except Exception:
            return iso[:16]