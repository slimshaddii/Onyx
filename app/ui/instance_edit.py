"""
Edit Instance window — opens like Prism's instance editor.
Tabs: Mods, Saves, Notes, Log, Settings
"""

from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QGroupBox, QGridLayout, QLineEdit, QCheckBox, QMessageBox,
    QFileDialog
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

    def __init__(self, parent, instance: Instance, rw: RimWorldDetector = None):
        super().__init__(parent)
        self.inst = instance
        self.rw = rw
        self.setWindowTitle(f"Edit — {instance.name}")
        self.setMinimumSize(700, 500)
        self.resize(750, 550)
        self._build()

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(8, 8, 8, 8)

        # Header
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel(f"<b style='font-size:15px;color:#7c8aff'>{self.inst.name}</b>"))
        hdr.addStretch()
        hdr.addWidget(QLabel(f"📦 {self.inst.mod_count} mods  •  💾 {self.inst.save_count} saves"))
        lo.addLayout(hdr)

        tabs = QTabWidget()

        # ── Overview tab ──
        overview = QWidget()
        ov_lo = QVBoxLayout(overview)

        info = QGroupBox("Instance Info")
        ig = QGridLayout()
        ig.setVerticalSpacing(4)
        fields = {
            'Path': str(self.inst.path),
            'Version': self.inst.rimworld_version or '—',
            'Created': self._fmt(self.inst.created),
            'Last Played': self._fmt(self.inst.last_played) or 'Never',
            'Playtime': f"{self.inst.total_playtime_minutes // 60}h {self.inst.total_playtime_minutes % 60}m",
            'Size': human_size(get_folder_size(self.inst.path)),
        }
        for r, (k, v) in enumerate(fields.items()):
            ig.addWidget(QLabel(f"<b>{k}:</b>"), r, 0)
            vl = QLabel(v)
            vl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            ig.addWidget(vl, r, 1)
        info.setLayout(ig)
        ov_lo.addWidget(info)
        ov_lo.addStretch()
        tabs.addTab(overview, "📊 Overview")

        # ── Mods tab ──
        mods_tab = QWidget()
        mt_lo = QVBoxLayout(mods_tab)

        mods, _, _ = read_mods_config(self.inst.config_dir)
        mt_lo.addWidget(QLabel(f"Active mods: {len(mods)}"))
        self.mod_list = QListWidget()
        installed = self.rw.get_installed_mods() if self.rw else {}
        for mid in mods:
            name = installed[mid].name if mid in installed else mid
            found = mid in installed
            item = QListWidgetItem(f"{'✔' if found else '✖'} {name}  [{mid}]")
            if not found:
                item.setForeground(Qt.GlobalColor.red)
            self.mod_list.addItem(item)
        mt_lo.addWidget(self.mod_list)

        mod_btns = QHBoxLayout()
        edit_btn = QPushButton("📦 Open Mod Editor")
        edit_btn.setObjectName("primaryButton")
        edit_btn.clicked.connect(self._open_mod_editor)
        mod_btns.addWidget(edit_btn)
        exp_btn = QPushButton("📤 Export Modlist")
        exp_btn.clicked.connect(self._export_mods)
        mod_btns.addWidget(exp_btn)
        mod_btns.addStretch()
        mt_lo.addLayout(mod_btns)
        tabs.addTab(mods_tab, "📦 Mods")

        # ── Saves tab ──
        saves_tab = QWidget()
        sv_lo = QVBoxLayout(saves_tab)
        self.saves_list = QListWidget()
        for s in self.inst.get_save_files():
            try:
                dt = datetime.fromisoformat(s['modified']).strftime("%b %d %H:%M")
            except Exception:
                dt = s['modified'][:16]
            self.saves_list.addItem(f"📄 {s['name']}  —  {human_size(s['size'])}  —  {dt}")
        if not self.saves_list.count():
            sv_lo.addWidget(QLabel("No saves yet."))
        sv_lo.addWidget(self.saves_list)

        sv_btns = QHBoxLayout()
        sv_btns.addWidget(QPushButton("📂 Open Saves Folder",
                          clicked=lambda: self._open_path(self.inst.saves_dir)))
        sv_btns.addStretch()
        sv_lo.addLayout(sv_btns)
        tabs.addTab(saves_tab, "💾 Saves")

        # ── Notes tab ──
        notes_tab = QWidget()
        nt_lo = QVBoxLayout(notes_tab)
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlainText(self.inst.notes or '')
        self.notes_edit.setPlaceholderText("Write notes about this instance…")
        nt_lo.addWidget(self.notes_edit)
        tabs.addTab(notes_tab, "📝 Notes")

        # ── Log tab ──
        log_tab = QWidget()
        lg_lo = QVBoxLayout(log_tab)
        log_path = self.inst.path / 'Player.log'
        if log_path.exists():
            try:
                text = log_path.read_text(encoding='utf-8', errors='replace')[-50000:]
                log_view = QTextEdit()
                log_view.setReadOnly(True)
                log_view.setPlainText(text)
                log_view.setStyleSheet("font-family:Consolas; font-size:10px;")
                lg_lo.addWidget(log_view)
            except Exception:
                lg_lo.addWidget(QLabel("Could not read log file."))
        else:
            lg_lo.addWidget(QLabel("No log file. Launch the game first."))
        open_log_btn = QPushButton("📋 Open Full Log Viewer",
                                   clicked=self._open_log_viewer)
        lg_lo.addWidget(open_log_btn)
        tabs.addTab(log_tab, "📋 Log")

        # ── Settings tab ──
        set_tab = QWidget()
        st_lo = QVBoxLayout(set_tab)
        st_lo.addWidget(QLabel("Launch Arguments:"))
        self.args_edit = QLineEdit()
        self.args_edit.setText(' '.join(self.inst.launch_args))
        self.args_edit.setPlaceholderText("-popupwindow -screen-width 1920 …")
        st_lo.addWidget(self.args_edit)
        st_lo.addWidget(QLabel(
            "<small>Common: -popupwindow, -screen-fullscreen 0, "
            "-screen-width 1920, -screen-height 1080, -force-d3d11</small>"))
        st_lo.addStretch()
        tabs.addTab(set_tab, "⚙ Settings")

        lo.addWidget(tabs)

        # Bottom buttons
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(QPushButton("Cancel", clicked=self.reject))
        save = QPushButton("Save")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._save)
        btns.addWidget(save)
        lo.addLayout(btns)

    def _save(self):
        self.inst.notes = self.notes_edit.toPlainText()
        args_text = self.args_edit.text().strip()
        self.inst.launch_args = args_text.split() if args_text else []
        self.inst.save()
        self.instance_changed.emit()
        self.accept()

    def _open_mod_editor(self):
        from app.ui.modeditor import ModEditorDialog
        if self.rw:
            if ModEditorDialog(self, self.inst, self.rw).exec():
                self.instance_changed.emit()
                self.accept()

    def _export_mods(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export", "modlist.txt", "Text (*.txt)")
        if path:
            installed = self.rw.get_installed_mods() if self.rw else {}
            names = {pid: info.name for pid, info in installed.items()}
            export_rimsort_modlist(path, self.inst.mods, names)
            QMessageBox.information(self, "Export", f"Exported {len(self.inst.mods)} mods.")

    def _open_log_viewer(self):
        from app.ui.log_viewer import LogViewerDialog
        LogViewerDialog(self, LogParser(), self.inst).exec()

    def _open_path(self, path: Path):
        import os, subprocess
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