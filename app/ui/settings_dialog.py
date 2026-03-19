"""Settings dialog for configuring Onyx Launcher preferences."""

import platform
import webbrowser

from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QGridLayout, QFileDialog,
    QCheckBox, QSpinBox, QListWidget, QComboBox, QTextEdit,
)

from app.core.app_settings import AppSettings
from app.core.auto_detect import auto_detect_all
from app.core.paths import get_default_data_root


class SettingsDialog(QDialog):
    """Dialog for editing Onyx Launcher configuration settings."""

    def __init__(self, parent, settings: dict):
        super().__init__(parent)
        self.s = dict(settings)
        self.setWindowTitle("Settings — Onyx Launcher")
        self.setMinimumWidth(620)
        self._build()
        self._load()

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setSpacing(8)

        dr = QHBoxLayout()
        db = QPushButton("🔍 Auto-Detect")
        db.setObjectName("primaryButton")
        db.clicked.connect(self._detect)
        dr.addWidget(db)
        dr.addStretch()
        lo.addLayout(dr)

        g1 = QGroupBox("Paths")
        gl = QGridLayout()
        gl.setVerticalSpacing(6)

        gl.addWidget(QLabel("RimWorld exe:"), 0, 0)
        self.exe = QLineEdit()
        gl.addWidget(self.exe, 0, 1)
        gl.addWidget(self._browse_btn(self.exe, file=True), 0, 2)

        gl.addWidget(QLabel("Data folder:"), 1, 0)
        self.data = QLineEdit()
        self.data.setPlaceholderText(str(get_default_data_root()))
        self.data.setToolTip("Root folder for instances, mods, icons, logs")
        gl.addWidget(self.data, 1, 1)
        gl.addWidget(self._browse_btn(self.data, file=False), 1, 2)

        gl.addWidget(QLabel("Game type:"), 2, 0)
        self.copy_cb = QComboBox()
        self.copy_cb.addItems(["Non-Steam", "Steam"])
        gl.addWidget(self.copy_cb, 2, 1, 1, 2)

        g1.setLayout(gl)
        lo.addWidget(g1)

        g2 = QGroupBox("Workshop Downloads")
        g2l = QGridLayout()
        g2l.setVerticalSpacing(6)

        g2l.addWidget(QLabel("Method:"), 0, 0)
        self.method = QComboBox()
        self.method.addItem("SteamCMD", "steamcmd")
        self.method.addItem("Steam native", "steam_native")
        g2l.addWidget(self.method, 0, 1, 1, 2)

        g2l.addWidget(QLabel("SteamCMD:"), 1, 0)
        self.cmd = QLineEdit()
        g2l.addWidget(self.cmd, 1, 1)
        g2l.addWidget(self._browse_btn(self.cmd, file=True), 1, 2)

        g2l.addWidget(QLabel("CMD login:"), 2, 0)
        self.cmd_user = QLineEdit()
        self.cmd_user.setPlaceholderText("anonymous")
        g2l.addWidget(self.cmd_user, 2, 1, 1, 2)

        g2l.addWidget(QLabel("Workshop path:"), 3, 0)
        self.ws = QLineEdit()
        self.ws.setPlaceholderText("Auto-detected")
        g2l.addWidget(self.ws, 3, 1)
        g2l.addWidget(self._browse_btn(self.ws, file=False), 3, 2)

        g2l.addWidget(QLabel("API key:"), 4, 0)
        self.api = QLineEdit()
        self.api.setEchoMode(QLineEdit.EchoMode.Password)
        self.api.setPlaceholderText("Optional — for workshop search")
        g2l.addWidget(self.api, 4, 1)
        qb = QPushButton("?")
        qb.setFixedWidth(28)
        qb.clicked.connect(
            lambda: webbrowser.open("https://steamcommunity.com/dev/apikey"))
        g2l.addWidget(qb, 4, 2)

        g2.setLayout(g2l)
        lo.addWidget(g2)

        g3 = QGroupBox("Extra Mod Folders")
        g3l = QVBoxLayout()
        self.paths_list = QListWidget()
        self.paths_list.setMaximumHeight(70)
        g3l.addWidget(self.paths_list)
        pr = QHBoxLayout()
        ab = QPushButton("Add")
        ab.clicked.connect(self._add_path)
        pr.addWidget(ab)
        rb = QPushButton("Remove")
        rb.clicked.connect(
            lambda: self.paths_list.takeItem(self.paths_list.currentRow())
            if self.paths_list.currentRow() >= 0 else None)
        pr.addWidget(rb)
        pr.addStretch()
        g3l.addLayout(pr)
        g3.setLayout(g3l)
        lo.addWidget(g3)

        g4 = QGroupBox("Backups")
        g4l = QHBoxLayout()
        self.bk = QCheckBox("Auto-backup before launch")
        g4l.addWidget(self.bk)
        g4l.addWidget(QLabel("Max:"))
        self.bk_n = QSpinBox()
        self.bk_n.setRange(1, 20)
        g4l.addWidget(self.bk_n)
        g4l.addStretch()
        g4.setLayout(g4l)
        lo.addWidget(g4)

        g5 = QGroupBox("Appearance")
        g5l = QHBoxLayout()
        g5l.addWidget(QLabel("Theme:"))
        self.theme_cb = QComboBox()
        self.theme_cb.addItems(["Dark", "Light"])
        g5l.addWidget(self.theme_cb)

        g5l.addWidget(QLabel("Mod updates:"))
        self.update_cb = QComboBox()
        self.update_cb.addItem("Check on startup (background)", "auto")
        self.update_cb.addItem("Manual only",                   "manual")
        self.update_cb.addItem("Disabled",                      "disabled")
        g5l.addWidget(self.update_cb)
        g5l.addStretch()
        g5.setLayout(g5l)
        lo.addWidget(g5)

        self.det_log = QTextEdit()
        self.det_log.setReadOnly(True)
        self.det_log.setMaximumHeight(80)
        self.det_log.hide()
        lo.addWidget(self.det_log)

        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(self._btn("Cancel", self.reject))
        btns.addWidget(self._btn("Save", self._save, primary=True))
        lo.addLayout(btns)

    def _btn(self, text, slot, primary=False):
        b = QPushButton(text)
        if primary:
            b.setObjectName("primaryButton")
        b.clicked.connect(slot)
        return b

    def _browse_btn(self, target: QLineEdit, file=False):
        b = QPushButton("…")
        b.setFixedWidth(28)
        if file:
            b.clicked.connect(lambda: self._browse_file(target))
        else:
            b.clicked.connect(lambda: self._browse_dir(target))
        return b

    def _browse_file(self, t):
        if platform.system() == 'Windows':
            filt = "Exe (*.exe);;All Files (*)"
        else:
            filt = "All Files (*)"
        p, _ = QFileDialog.getOpenFileName(self, "Select", "", filt)
        if p:
            t.setText(p)

    def _browse_dir(self, t):
        p = QFileDialog.getExistingDirectory(self, "Select folder")
        if p:
            t.setText(p)

    def _add_path(self):
        p = QFileDialog.getExistingDirectory(self, "Add mod folder")
        if p:
            self.paths_list.addItem(p)

    def _load(self):
        self.exe.setText(self.s.get('rimworld_exe', ''))
        self.data.setText(self.s.get('data_root', ''))
        self.cmd.setText(self.s.get('steamcmd_path', ''))
        self.cmd_user.setText(self.s.get('steamcmd_username', ''))
        self.ws.setText(self.s.get('steam_workshop_path', ''))
        self.api.setText(self.s.get('steam_api_key', ''))
        self.bk.setChecked(self.s.get('auto_backup_on_launch', True))
        self.bk_n.setValue(self.s.get('backup_count', 3))
        self.copy_cb.setCurrentIndex(1 if self.s.get('is_steam_copy') else 0)
        self.method.setCurrentIndex(
            1 if self.s.get('download_method') == 'steam_native' else 0)
        for p in self.s.get('extra_mod_paths', []):
            self.paths_list.addItem(p)
        mode = AppSettings.instance().update_check_mode
        idx  = self.update_cb.findData(mode)
        self.update_cb.setCurrentIndex(max(0, idx))

    def _detect(self):
        self.det_log.show()
        self.det_log.clear()
        r = auto_detect_all()
        for line in r.logs:
            self.det_log.append(f"  {line}")
        if r.found_rimworld:
            self.exe.setText(r.rimworld_exe)
            self.copy_cb.setCurrentIndex(1 if r.is_steam_copy else 0)
            self.method.setCurrentIndex(1 if r.is_steam_copy else 0)
        if r.steam_workshop_path:
            self.ws.setText(r.steam_workshop_path)
        if r.steamcmd_path:
            self.cmd.setText(r.steamcmd_path)
        if r.extra_mod_paths:
            existing = {self.paths_list.item(i).text()
                        for i in range(self.paths_list.count())}
            for p in r.extra_mod_paths:
                if p not in existing:
                    self.paths_list.addItem(p)
        self.det_log.append(
            "\n✅ Done" if r.found_rimworld else "\n⚠ RimWorld not found")

    def _save(self):
        self.s['rimworld_exe']        = self.exe.text().strip()
        self.s['data_root']           = (self.data.text().strip()
                                         or str(get_default_data_root()))
        self.s['steamcmd_path']       = self.cmd.text().strip()
        self.s['steamcmd_username']   = self.cmd_user.text().strip()
        self.s['steam_workshop_path'] = self.ws.text().strip()
        self.s['steam_api_key']       = self.api.text().strip()
        self.s['auto_backup_on_launch'] = self.bk.isChecked()
        self.s['backup_count']        = self.bk_n.value()
        self.s['is_steam_copy']       = self.copy_cb.currentIndex() == 1
        self.s['download_method']     = self.method.currentData()
        self.s['extra_mod_paths']     = [
            self.paths_list.item(i).text()
            for i in range(self.paths_list.count())]
        self.s['update_check_mode']   = self.update_cb.currentData()
        self.accept()

    def get_settings(self) -> dict:
        """Return a copy of the current settings dict."""
        return dict(self.s)
