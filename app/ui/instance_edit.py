"""
Edit Instance window.
Tabs: Overview, Mods, Saves, Notes, Log, Settings,
Ignored Deps
"""

import platform
import threading
from datetime import datetime

from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QDialog, QVBoxLayout, QHBoxLayout,
    QTabWidget, QWidget, QLabel, QPushButton,
    QTextEdit, QListWidget, QListWidgetItem,
    QGroupBox, QGridLayout, QLineEdit,
    QCheckBox, QMessageBox, QFileDialog,
    QScrollArea, QFrame,
)
from PyQt6.QtCore import (  # pylint: disable=no-name-in-module
    Qt, pyqtSignal, QTimer,
)

from app.core.instance import Instance
from app.core.launcher import Launcher
from app.core.log_parser import LogParser
from app.core.modlist import (
    read_mods_config, export_rimsort_modlist,
)
from app.core.rimworld import RimWorldDetector
from app.ui.detail.edit_saves import EditSavesTab
from app.utils.file_utils import (
    human_size, get_folder_size,
)

_SEV_ICON: dict[str, str] = {
    'error':       '❌',
    'dep':         '📦',
    'warning':     '⚠',
    'order':       '🔃',
    'performance': '🐢',
    'info':        'ℹ',
}


class InstanceEditDialog(QDialog):
    """Dialog for editing instance settings across
    multiple tabs."""

    instance_changed = pyqtSignal()

    def __init__(self, parent,
                 instance: Instance,
                 rw: RimWorldDetector = None):
        super().__init__(parent)
        self.inst = instance
        self.rw   = rw
        self.setWindowTitle(
            f"Edit — {instance.name}")
        self.setMinimumSize(780, 600)
        self.resize(860, 660)

        self._ig: (
            QGridLayout | None) = None
        self.mod_list: (
            QListWidget | None) = None
        self.notes_edit: (
            QTextEdit | None) = None
        self._settings_arg_cbs: (
            list | None) = None
        self._settings_arg_inputs: (
            dict | None) = None
        self._custom_args: (
            QLineEdit | None) = None
        self._remember_cb: (
            QCheckBox | None) = None
        self.group_edit: (
            QLineEdit | None) = None
        self._exe_override: (
            QLineEdit | None) = None
        self._ignored_container: (
            QWidget | None) = None
        self._ignored_layout: (
            QVBoxLayout | None) = None
        self._saves_tab: (
            EditSavesTab | None) = None

        self._build()

    # ── Build ────────────────────────────────────

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(8, 8, 8, 8)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel(
            f"<b style='font-size:15px;"
            f"color:#7c8aff'>"
            f"{self.inst.name}</b>"))
        hdr.addStretch()
        hdr.addWidget(QLabel(
            f"📦 {self.inst.mod_count} mods"
            f"  •  "
            f"💾 {self.inst.save_count} saves"))
        lo.addLayout(hdr)

        tabs = QTabWidget()
        tabs.addTab(
            self._build_overview_tab(),
            "📊 Overview")
        tabs.addTab(
            self._build_mods_tab(),
            "📦 Mods")

        self._saves_tab = EditSavesTab(
            self, self.inst, self.rw)
        self._saves_tab.instance_changed \
            .connect(self.instance_changed.emit)
        tabs.addTab(self._saves_tab, "Saves")

        tabs.addTab(
            self._build_notes_tab(), "Notes")
        tabs.addTab(
            self._build_log_tab(), "📋 Log")
        tabs.addTab(
            self._build_settings_tab(),
            "⚙ Settings")
        tabs.addTab(
            self._build_ignored_tab(),
            "🚫 Ignored Warnings")
        lo.addWidget(tabs)

        self.instance_changed.connect(
            self._saves_tab.refresh)

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

    # ── Overview Tab ─────────────────────────────

    def _build_overview_tab(self) -> QWidget:
        w  = QWidget()
        lo = QVBoxLayout(w)
        info = QGroupBox("Instance Info")
        ig   = QGridLayout()
        ig.setVerticalSpacing(4)
        pt = self.inst.total_playtime_minutes
        fields = {
            'Path': str(self.inst.path),
            'Version': (
                self.inst.rimworld_version
                or '—'),
            'Created': self._fmt(
                self.inst.created),
            'Last Played': (
                self._fmt(
                    self.inst.last_played)
                or 'Never'),
            'Playtime': (
                f"{pt // 60}h {pt % 60}m"),
            'Size': '…',
        }
        self._ig = ig
        for r, (k, v) in enumerate(
                fields.items()):
            ig.addWidget(
                QLabel(f"<b>{k}:</b>"), r, 0)
            vl = QLabel(v)
            vl.setTextInteractionFlags(
                Qt.TextInteractionFlag
                .TextSelectableByMouse)
            ig.addWidget(vl, r, 1)
        info.setLayout(ig)
        lo.addWidget(info)
        lo.addStretch()

        def _calc():
            try:
                size = human_size(
                    get_folder_size(
                        self.inst.path))
            except Exception:  # pylint: disable=broad-exception-caught
                # daemon thread — folder stat
                # failure is non-fatal
                size = '—'
            QTimer.singleShot(
                0,
                lambda: self._set_size(size))

        threading.Thread(
            target=_calc, daemon=True).start()
        return w

    def _set_size(self, text: str):
        ig = self._ig
        for r in range(ig.rowCount()):
            lbl = ig.itemAtPosition(r, 0)
            if (lbl and lbl.widget()
                    and 'Size'
                    in lbl.widget().text()):
                val = ig.itemAtPosition(r, 1)
                if val and val.widget():
                    val.widget().setText(text)
                break

    # ── Mods Tab ─────────────────────────────────

    def _build_mods_tab(self) -> QWidget:
        w  = QWidget()
        lo = QVBoxLayout(w)
        mods, _, _ = read_mods_config(
            self.inst.config_dir)
        lo.addWidget(QLabel(
            f"Active mods: {len(mods)}"))
        self.mod_list = QListWidget()
        installed = (
            self.rw.get_installed_mods()
            if self.rw else {})
        for mid in mods:
            name = (
                installed[mid].name
                if mid in installed else mid)
            found = mid in installed
            item = QListWidgetItem(
                f"{'✔' if found else '✖'}"
                f" {name}  [{mid}]")
            if not found:
                item.setForeground(
                    Qt.GlobalColor.red)
            self.mod_list.addItem(item)
        lo.addWidget(self.mod_list)

        mod_btns = QHBoxLayout()
        edit_btn = QPushButton(
            "📦 Open Mod Editor")
        edit_btn.setObjectName("primaryButton")
        edit_btn.clicked.connect(
            self._open_mod_editor)
        mod_btns.addWidget(edit_btn)
        exp_btn = QPushButton(
            "📤 Export Modlist")
        exp_btn.clicked.connect(
            self._export_mods)
        mod_btns.addWidget(exp_btn)
        mod_btns.addStretch()
        lo.addLayout(mod_btns)
        return w

    # ── Notes Tab ────────────────────────────────

    def _build_notes_tab(self) -> QWidget:
        w  = QWidget()
        lo = QVBoxLayout(w)
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlainText(
            self.inst.notes or '')
        self.notes_edit.setPlaceholderText(
            "Write notes about this "
            "instance…")
        lo.addWidget(self.notes_edit)
        return w

    # ── Log Tab ──────────────────────────────────

    def _build_log_tab(self) -> QWidget:
        w  = QWidget()
        lo = QVBoxLayout(w)
        log_path = (
            self.inst.path / 'Player.log')
        if log_path.exists():
            try:
                text = log_path.read_text(
                    encoding='utf-8',
                    errors='replace')[-50000:]
                lv = QTextEdit()
                lv.setReadOnly(True)
                lv.setPlainText(text)
                lv.setStyleSheet(
                    "font-family:Consolas;"
                    " font-size:10px;")
                lo.addWidget(lv)
            except OSError:
                lo.addWidget(QLabel(
                    "Could not read log."))
        else:
            lo.addWidget(QLabel(
                "No log file. Launch the "
                "game first."))
        btn = QPushButton(
            "Open Full Log Viewer")
        btn.clicked.connect(
            self._open_log_viewer)
        lo.addWidget(btn)
        return w

    # ── Settings Tab ─────────────────────────────

    def _build_settings_tab(self) -> QWidget:
        """Pre-configure launch args, group,
        and exe override."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy
            .ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none;"
            " background: transparent; }")
        w  = QWidget()
        lo = QVBoxLayout(w)
        lo.setSpacing(8)
        common = Launcher.get_common_launch_args()
        args_group = QGroupBox(
            "Launch Arguments")
        ag_lo = QVBoxLayout()
        self._settings_arg_cbs = []
        self._settings_arg_inputs = {}
        current_args = set(
            self.inst.launch_args)
        for a in common:
            row = QHBoxLayout()
            cb = QCheckBox(a['arg'])
            cb.setToolTip(a['desc'])
            cb.setChecked(
                a['arg'] in current_args)
            row.addWidget(cb)
            row.addWidget(QLabel(a['desc']))
            if a.get('has_value'):
                vi = QLineEdit()
                vi.setFixedWidth(80)
                vi.setPlaceholderText(
                    a.get('default', ''))
                al = self.inst.launch_args
                if a['arg'] in al:
                    try:
                        idx = al.index(a['arg'])
                        if idx + 1 < len(al):
                            vi.setText(
                                al[idx + 1])
                    except ValueError:
                        pass
                row.addWidget(vi)
                self._settings_arg_inputs[
                    a['arg']] = vi
            row.addStretch()
            self._settings_arg_cbs.append(
                (cb, a))
            ag_lo.addLayout(row)
        ag_lo.addWidget(QLabel(
            "Custom arguments:"))
        self._custom_args = QLineEdit()
        self._custom_args.setPlaceholderText(
            "Extra arguments…")
        known = {a['arg'] for a in common}
        custom_parts: list[str] = []
        i = 0
        while i < len(self.inst.launch_args):
            arg = self.inst.launch_args[i]
            if (arg not in known
                    and arg not in
                    self._settings_arg_inputs):
                custom_parts.append(arg)
            elif (arg
                    in self._settings_arg_inputs):
                i += 1
            i += 1
        self._custom_args.setText(
            ' '.join(custom_parts))
        ag_lo.addWidget(self._custom_args)
        args_group.setLayout(ag_lo)
        lo.addWidget(args_group)

        self._remember_cb = QCheckBox(
            "Skip launch dialog")
        self._remember_cb.setToolTip(
            "Use these arguments directly, "
            "bypassing the launch dialog.")
        self._remember_cb.setChecked(
            self.inst.mods_configured)
        lo.addWidget(self._remember_cb)

        lo.addWidget(QLabel("Group / Tag:"))
        self.group_edit = QLineEdit()
        self.group_edit.setText(
            self.inst.group or '')
        self.group_edit.setPlaceholderText(
            "e.g. Vanilla, Modded, Testing")
        lo.addWidget(self.group_edit)

        exe_group = QGroupBox(
            "RimWorld Override")
        exe_lo = QVBoxLayout()
        exe_lo.addWidget(QLabel(
            "Leave blank for global path."))
        exe_row = QHBoxLayout()
        self._exe_override = QLineEdit()
        self._exe_override.setText(
            getattr(self.inst,
                    'rimworld_exe_override',
                    ''))
        self._exe_override.setPlaceholderText(
            "e.g. D:/RimWorld15/"
            "RimWorldWin64.exe")
        exe_row.addWidget(
            self._exe_override, 1)
        browse = QPushButton("Browse…")
        browse.setFixedWidth(70)
        browse.clicked.connect(
            self._browse_exe_override)
        exe_row.addWidget(browse)
        clear = QPushButton("Clear")
        clear.setFixedWidth(62)
        clear.clicked.connect(
            self._exe_override.clear)
        exe_row.addWidget(clear)
        exe_lo.addLayout(exe_row)
        exe_group.setLayout(exe_lo)
        lo.addWidget(exe_group)
        lo.addStretch()
        scroll.setWidget(w)
        return scroll

    # ── Ignored Tab ──────────────────────────────

    def _build_ignored_tab(self) -> QWidget:
        """Suppressed dep and error badges."""
        w  = QWidget()
        lo = QVBoxLayout(w)
        lo.setSpacing(6)
        lo.addWidget(QLabel(
            "<b>Suppressed warnings</b><br>"
            "<small style='color:#888;'>"
            "Remove to re-enable.</small>"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy
            .ScrollBarAlwaysOff)
        self._ignored_container = QWidget()
        self._ignored_layout = QVBoxLayout(
            self._ignored_container)
        self._ignored_layout.setSpacing(4)
        self._ignored_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(
            self._ignored_container)
        lo.addWidget(scroll, 1)
        self._populate_ignored()
        clear_btn = QPushButton("🗑 Clear All")
        clear_btn.setObjectName("dangerButton")
        clear_btn.clicked.connect(
            self._clear_all_ignored)
        br = QHBoxLayout()
        br.addStretch()
        br.addWidget(clear_btn)
        lo.addLayout(br)
        return w

    def _populate_ignored(self):
        while self._ignored_layout.count():
            item = self._ignored_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        installed = (
            self.rw.get_installed_mods()
            if self.rw else {})
        has_d = bool(self.inst.ignored_deps)
        has_e = bool(self.inst.ignored_errors)
        if not has_d and not has_e:
            self._ignored_layout.addWidget(QLabel(
                "<i style='color:#555;'>"
                "No suppressed warnings.</i>"))
            return
        if has_d:
            self._ignored_layout.addWidget(QLabel(
                "<b style='color:#ff8800;'>"
                "📦 Dependency</b>"))
            for entry in list(
                    self.inst.ignored_deps):
                parts = entry.split(':', 1)
                if len(parts) != 2:
                    continue
                mod_id, dep_id = parts
                mn = (installed[mod_id].name
                      if mod_id in installed
                      else mod_id)
                dn = (installed[dep_id].name
                      if dep_id in installed
                      else dep_id)
                self._ignored_layout.addWidget(
                    self._mk_ign_row(
                        f"<b>{mn}</b>"
                        f" needs <b>{dn}</b>"
                        f"<br><small "
                        f"style='color:#555;'>"
                        f"{entry}</small>",
                        lambda _, e=entry:
                            self._rm_dep(e)))
        if has_e:
            self._ignored_layout.addWidget(QLabel(
                "<b style='color:#ff4444;'>"
                "🚫 Errors/Warnings</b>"))
            for entry in list(
                    self.inst.ignored_errors):
                parts = entry.split(':', 2)
                if len(parts) != 3:
                    continue
                mid, sev, msg = parts
                mn = (installed[mid].name
                      if mid in installed
                      else mid)
                ico = _SEV_ICON.get(sev, '⚠')
                self._ignored_layout.addWidget(
                    self._mk_ign_row(
                        f"<b>{mn}</b>: "
                        f"{ico} {msg}"
                        f"<br><small "
                        f"style='color:#555;'>"
                        f"[{sev}]</small>",
                        lambda _, e=entry:
                            self._rm_err(e)))

    def _mk_ign_row(self, html: str,
                    slot) -> QFrame:
        row = QFrame()
        row.setStyleSheet(
            "QFrame { background:#2a2a2a;"
            " border-radius:4px;"
            " padding:2px; }")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 4, 8, 4)
        lbl = QLabel(html)
        lbl.setWordWrap(True)
        rl.addWidget(lbl, 1)
        btn = QPushButton("✕")
        btn.setFixedSize(28, 22)
        btn.setStyleSheet(
            "font-size:10px;"
            " background:#3a2a2a;"
            " color:#cc6666;"
            " border:1px solid #663333;"
            " border-radius:3px;")
        btn.clicked.connect(slot)
        rl.addWidget(btn)
        return row

    def _rm_dep(self, entry: str):
        if entry in self.inst.ignored_deps:
            self.inst.ignored_deps.remove(entry)
            self.inst.save()
            self._populate_ignored()

    def _rm_err(self, entry: str):
        if entry in self.inst.ignored_errors:
            self.inst.ignored_errors.remove(
                entry)
            self.inst.save()
            self._populate_ignored()

    def _clear_all_ignored(self):
        if (not self.inst.ignored_deps
                and not self.inst.ignored_errors):
            return
        if QMessageBox.question(
            self, "Clear All",
            "Remove all suppressed warnings?",
        ) == QMessageBox.StandardButton.Yes:
            self.inst.ignored_deps.clear()
            self.inst.ignored_errors.clear()
            self.inst.save()
            self._populate_ignored()

    # ── Save / Actions ───────────────────────────

    def _save(self):
        self.inst.notes = (
            self.notes_edit.toPlainText())
        self.inst.group = (
            self.group_edit.text().strip())
        args: list[str] = []
        for cb, a in self._settings_arg_cbs:
            if cb.isChecked():
                args.append(a['arg'])
                if (a.get('has_value')
                        and a['arg'] in
                        self._settings_arg_inputs):
                    v = (
                        self._settings_arg_inputs[
                            a['arg']]
                        .text().strip())
                    args.append(
                        v or a.get(
                            'default', ''))
        custom = (
            self._custom_args.text().strip())
        if custom:
            args.extend(custom.split())
        self.inst.rimworld_exe_override = (
            self._exe_override.text().strip())
        self.inst.launch_args = args
        self.inst.mods_configured = (
            self._remember_cb.isChecked())
        self.inst.save()
        self.instance_changed.emit()
        self.accept()

    def _open_mod_editor(self):
        from app.ui.modeditor import ModEditorDialog  # pylint: disable=import-outside-toplevel
        if self.rw and ModEditorDialog(
                self, self.inst, self.rw).exec():
            self.instance_changed.emit()
            self.accept()

    def _export_mods(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export", "modlist.txt",
            "Text (*.txt)")
        if path:
            installed = (
                self.rw.get_installed_mods()
                if self.rw else {})
            names = {
                pid: i.name
                for pid, i
                in installed.items()}
            export_rimsort_modlist(
                path, self.inst.mods, names)
            QMessageBox.information(
                self, "Export",
                f"Exported {len(self.inst.mods)}"
                f" mods.")

    def _open_log_viewer(self):
        from app.ui.log_viewer import LogViewerDialog  # pylint: disable=import-outside-toplevel
        LogViewerDialog(
            self, LogParser(), self.inst).exec()

    def _browse_exe_override(self):
        if platform.system() == 'Windows':
            filt = (
                "Executable (*.exe);;"
                "All Files (*)")
        else:
            filt = "All Files (*)"
        path, _ = QFileDialog.getOpenFileName(
            self, "Select RimWorld Executable",
            "", filt)
        if path:
            self._exe_override.setText(path)

    @staticmethod
    def _fmt(iso: str) -> str:
        if not iso:
            return ''
        try:
            return (
                datetime.fromisoformat(iso)
                .strftime("%b %d, %Y  %H:%M"))
        except ValueError:
            return iso[:16]
