from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QLineEdit, QGroupBox, QGridLayout
)
from PyQt6.QtCore import Qt
from app.core.instance import Instance
from app.core.launcher import Launcher, LaunchResult
from app.core.paths import settings_path  # FIX #1: centralized settings path
from app.utils.file_utils import load_json

# FIX #1: Removed hardcoded SETTINGS_PATH


class LaunchDialog(QDialog):
    def __init__(self, parent, instance: Instance, launcher: Launcher):
        super().__init__(parent)
        self.instance = instance
        self.launcher = launcher
        self.launch_result = None
        self._main_window = parent

        self.setWindowTitle(f"Launch — {instance.name}")
        self.setMinimumWidth(500)
        self._build()

    def _build(self):
        lo = QVBoxLayout(self)

        info = QGroupBox("Instance")
        gl = QGridLayout()
        gl.addWidget(QLabel("Name:"), 0, 0)
        gl.addWidget(QLabel(f"<b>{self.instance.name}</b>"), 0, 1)
        gl.addWidget(QLabel("Mods:"), 1, 0)
        gl.addWidget(QLabel(str(self.instance.mod_count)), 1, 1)
        gl.addWidget(QLabel("Saves:"), 2, 0)
        gl.addWidget(QLabel(str(self.instance.save_count)), 2, 1)
        gl.addWidget(QLabel("Path:"), 3, 0)
        pl = QLabel(str(self.instance.path))
        pl.setStyleSheet("color:#6c7086;font-size:11px;")
        gl.addWidget(pl, 3, 1)
        info.setLayout(gl)
        lo.addWidget(info)

        ag = QGroupBox("Launch Arguments")
        al = QVBoxLayout()

        common = Launcher.get_common_launch_args()
        self.arg_cbs = []
        self.arg_inputs = {}

        for a in common:
            row = QHBoxLayout()
            cb = QCheckBox(a['arg'])
            cb.setToolTip(a['desc'])
            cb.setChecked(a['arg'] in self.instance.launch_args)
            row.addWidget(cb)
            row.addWidget(QLabel(a['desc']))

            vi = None
            if a.get('has_value'):
                vi = QLineEdit()
                vi.setFixedWidth(80)
                vi.setPlaceholderText(a.get('default', ''))
                if a['arg'] in self.instance.launch_args:
                    try:
                        idx = self.instance.launch_args.index(a['arg'])
                        if idx + 1 < len(self.instance.launch_args):
                            vi.setText(self.instance.launch_args[idx + 1])
                    except ValueError:
                        pass
                row.addWidget(vi)
                self.arg_inputs[a['arg']] = vi

            row.addStretch()
            self.arg_cbs.append((cb, a))
            al.addLayout(row)

        al.addWidget(QLabel("Custom:"))
        self.custom = QLineEdit()
        self.custom.setPlaceholderText("Extra arguments…")
        known = {a['arg'] for a in common}
        custom_parts = []
        i = 0
        while i < len(self.instance.launch_args):
            arg = self.instance.launch_args[i]
            if arg not in known and not any(
                    arg == self.instance.launch_args[j-1] and self.instance.launch_args[j-1] in self.arg_inputs
                    for j in range(i, i+1)):
                custom_parts.append(arg)
            elif arg in self.arg_inputs:
                i += 1
            i += 1
        self.custom.setText(' '.join(custom_parts))
        al.addWidget(self.custom)

        self.log_cb = QCheckBox("Redirect log to instance")
        self.log_cb.setChecked(True)
        al.addWidget(self.log_cb)
        ag.setLayout(al)
        lo.addWidget(ag)

        self.save_cb = QCheckBox("Remember arguments")
        self.save_cb.setChecked(True)
        lo.addWidget(self.save_cb)

        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(QPushButton("Cancel", clicked=self.reject))
        lb = QPushButton("▶ Launch")
        lb.setObjectName("primaryButton")
        lb.clicked.connect(self._launch)
        btns.addWidget(lb)
        lo.addLayout(btns)

    def _launch(self):
        extra = []
        for cb, a in self.arg_cbs:
            if cb.isChecked():
                extra.append(a['arg'])
                if a.get('has_value') and a['arg'] in self.arg_inputs:
                    v = self.arg_inputs[a['arg']].text().strip()
                    extra.append(v or a.get('default', ''))

        c = self.custom.text().strip()
        if c:
            extra.extend(c.split())

        if self.save_cb.isChecked():
            self.instance.launch_args = extra
            self.instance.save()

        # FIX #1: Use centralized settings path
        settings = load_json(settings_path(), {})
        dr = settings.get('data_root', '')
        exe = settings.get('rimworld_exe', '')

        onyx_mods = Path(dr) / 'mods' if dr else None
        game_mods = Path(exe).parent / 'Mods' if exe else None

        all_mods = None
        if self._main_window and hasattr(self._main_window, 'rw'):
            all_mods = self._main_window.rw.get_installed_mods()

        self.launch_result = self.launcher.launch(
            self.instance, extra,
            log_to_instance=self.log_cb.isChecked(),
            onyx_mods_dir=onyx_mods,
            game_mods_dir=game_mods,
            all_mods=all_mods)
        self.accept()