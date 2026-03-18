from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter,
    QToolBar, QStatusBar, QMessageBox, QLabel, QFileDialog
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QAction

from app.core.instance_manager import InstanceManager
from app.core.rimworld import RimWorldDetector
from app.core.launcher import Launcher
from app.core.steamcmd import SteamCMDManager, DownloadQueue
from app.core.log_parser import LogParser
from app.core.auto_detect import auto_detect_all
from app.core.steam_integration import DownloadMethod
from app.core.modlist import export_rimsort_modlist
from app.core.paths import (
    get_default_data_root, ensure_data_dirs, instances_dir, mods_dir,
    settings_path
)
from app.ui.instance_list import InstanceGridPanel
from app.ui.instance_detail import InstanceDetailPanel
from app.ui.settings_dialog import SettingsDialog
from app.utils.file_utils import load_json, save_json

DEFAULTS = {
    'rimworld_exe': '', 'data_root': '', 'steam_api_key': '',
    'steamcmd_path': '', 'steam_workshop_path': '', 'extra_mod_paths': [],
    'download_method': 'steamcmd', 'is_steam_copy': False,
    'window': {'width': 1200, 'height': 720, 'x': 80, 'y': 60},
    'auto_backup_on_launch': True, 'backup_count': 3, 'steamcmd_username': '',
    'offered_import': False,
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_json(settings_path(), DEFAULTS)
        for k, v in DEFAULTS.items():
            self.settings.setdefault(k, v)

        dr = self.settings.get('data_root') or str(get_default_data_root())
        self.settings['data_root'] = dr
        ensure_data_dirs(Path(dr))

        self.setWindowTitle("Onyx Launcher")
        w = self.settings['window']
        self.setGeometry(w.get('x', 80), w.get('y', 60),
                         w.get('width', 1200), w.get('height', 720))
        self.setMinimumSize(760, 440)

        self.rw = RimWorldDetector()
        self._init_rw()
        self.im = InstanceManager(instances_dir(Path(dr)))
        self.launcher = Launcher(
            self.settings.get('rimworld_exe', ''),
            self.settings.get('auto_backup_on_launch', True),
            self.settings.get('backup_count', 3))
        self.steamcmd = SteamCMDManager(
            self.settings.get('steamcmd_path', ''),
            str(mods_dir(Path(dr))))

        self.dl_queue = DownloadQueue(
            self.settings.get('steamcmd_path', ''),
            str(mods_dir(Path(dr))),
            max_concurrent=3,
            username=self.settings.get('steamcmd_username', ''))

        self.log_parser = LogParser()
        self._child_windows: list = []

        self._build_toolbar()
        self._build_ui()
        self._build_statusbar()
        self.refresh()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(5000)

        if not self.settings.get('rimworld_exe'):
            QTimer.singleShot(400, self._auto_detect)
        elif not self.settings.get('offered_import'):
            QTimer.singleShot(600, self._offer_import)

    def _init_rw(self):
        exe = self.settings.get('rimworld_exe', '')
        if exe and Path(exe).exists():
            self.rw.set_game_path(str(Path(exe).parent))
        paths = self._all_mod_paths()
        print(f"[Onyx] Mod search paths: {paths}")
        self.rw.get_installed_mods(paths, force_rescan=True)

    def _all_mod_paths(self) -> list[str]:
        paths = []
        dr = self.settings.get('data_root', '')
        if dr:
            p = str(mods_dir(Path(dr)))
            if p not in paths:
                paths.append(p)
        ws = self.settings.get('steam_workshop_path', '')
        if ws and ws not in paths:
            paths.append(ws)
        exe = self.settings.get('rimworld_exe', '')
        if exe:
            gm = str(Path(exe).parent / 'Mods')
            if gm not in paths:
                paths.append(gm)
        for p in self.settings.get('extra_mod_paths', []):
            if p not in paths:
                paths.append(p)
        return paths

    def _build_toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        tb.addAction(QAction("➕ Add Instance", self, triggered=self._on_new))
        tb.addAction(QAction("◆ Import .onyx", self, triggered=self._on_import_pack))
        tb.addSeparator()
        tb.addAction(QAction("🏪 Workshop", self, triggered=self._on_workshop))
        tb.addAction(QAction("📋 Logs", self, triggered=self._on_logs))
        tb.addSeparator()
        tb.addAction(QAction("⟳ Refresh", self, triggered=self.refresh))
        s = QWidget()
        from PyQt6.QtWidgets import QSizePolicy
        s.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(s)
        tb.addAction(QAction("⚙ Settings", self, triggered=self._on_settings))

    def _build_ui(self):
        c = QWidget()
        c.setStyleSheet("background:#222222;")
        self.setCentralWidget(c)
        lo = QHBoxLayout(c)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.setHandleWidth(1)

        self.grid = InstanceGridPanel(self)
        self.grid.instance_selected.connect(self._on_select)
        self.grid.instance_double_clicked.connect(self._on_launch)
        self.grid.edit_requested.connect(self._on_edit)
        self.grid.folder_requested.connect(self._open_folder)
        self.grid.export_requested.connect(self._on_export)
        self.grid.export_pack_requested.connect(self._on_export_pack)
        self.grid.copy_requested.connect(self._on_dup)
        self.grid.delete_requested.connect(self._on_del)
        self.grid.rename_requested.connect(lambda _: self.refresh())
        self.grid.setMinimumWidth(300)
        sp.addWidget(self.grid)

        self.detail = InstanceDetailPanel(self)
        self.detail.launch_requested.connect(self._on_launch)
        self.detail.edit_mods_requested.connect(self._on_edit_mods)
        self.detail.duplicate_requested.connect(self._on_dup)
        self.detail.delete_requested.connect(self._on_del)
        self.detail.export_pack_requested.connect(self._on_export_pack)
        self.detail.instance_updated.connect(self.refresh)
        self.detail.setMinimumWidth(280)
        sp.addWidget(self.detail)

        sp.setSizes([400, 800])
        lo.addWidget(sp)

    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.sl = QLabel("Ready")
        sb.addWidget(self.sl, 1)
        self.vl = QLabel(f"RimWorld {self.rw.version}" if self.rw.version else "")
        sb.addPermanentWidget(self.vl)
        self.gl = QLabel("")
        sb.addPermanentWidget(self.gl)

    def refresh(self, rescan_mods: bool = False):
        if rescan_mods:
            self.rw.get_installed_mods(self._all_mod_paths(), force_rescan=True)
        insts = self.im.scan_instances()
        self.grid.set_instances(insts)
        self.sl.setText(f"{len(insts)} instance{'s' if len(insts) != 1 else ''}")

    def _open_child(self, dlg):
        self._child_windows = [w for w in self._child_windows if w.isVisible()]
        self._child_windows.append(dlg)
        dlg.show()

    # ── Instance handlers ────────────────────────────────────────

    def _on_select(self, inst):
        self.detail.set_instance(inst, self.rw)

    def _on_new(self):
        from app.ui.instance_detail import NewInstanceDialog
        if NewInstanceDialog(self, self.rw, self.im).exec():
            self.refresh()

    def _on_launch(self, inst):
        from app.ui.launch_dialog import LaunchDialog
        dlg = LaunchDialog(self, inst, self.launcher)
        if dlg.exec():
            r = dlg.launch_result
            if r and r.success:
                self.sl.setText(f"▶ {inst.name}")
                self.gl.setText("🎮 Running")
                self.refresh()
            elif r:
                QMessageBox.critical(self, "Launch Failed", r.message)

    def _on_edit(self, inst):
        from app.ui.instance_edit import InstanceEditDialog
        self.rw.get_installed_mods(self._all_mod_paths(), force_rescan=True)
        dlg = InstanceEditDialog(None, inst, self.rw)
        dlg.instance_changed.connect(self.refresh)
        self._open_child(dlg)

    def _on_edit_mods(self, inst):
        from app.ui.modeditor import ModEditorDialog
        dlg = ModEditorDialog(self, inst, self.rw)
        if dlg.exec():
            self.refresh(rescan_mods=True)
            self.detail.set_instance(inst, self.rw)

    def _on_dup(self, inst):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Copy", "Name:",
                                        text=f"{inst.name} (Copy)")
        if ok and name:
            try:
                self.im.duplicate_instance(inst, name)
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_del(self, inst):
        if QMessageBox.warning(
            self, "Delete",
            f"Delete '{inst.name}'?\n{inst.save_count} save(s)\n{inst.path}\n\nCannot undo!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.im.delete_instance(inst)
            self.detail.clear()
            self.refresh()

    def _on_export(self, inst):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export", f"{inst.name}_modlist.txt", "Text (*.txt)")
        if path:
            installed = self.rw.get_installed_mods(self._all_mod_paths())
            names = {pid: info.name for pid, info in installed.items()}
            export_rimsort_modlist(path, inst.mods, names)
            QMessageBox.information(self, "Export", f"Exported {len(inst.mods)} mods.")

    # ── .onyx pack handlers ──────────────────────────────────────

    def _on_export_pack(self, inst):
        from app.ui.onyxpack_dialog import OnyxExportDialog
        self.rw.get_installed_mods(self._all_mod_paths(), force_rescan=True)
        dlg = OnyxExportDialog(self, inst, self.rw)
        dlg.exec()

    def _on_import_pack(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import .onyx", "",
            "Onyx Packs (*.onyx);;All Files (*)")
        if not path:
            return
        from app.ui.onyxpack_dialog import OnyxImportDialog
        self.rw.get_installed_mods(self._all_mod_paths(), force_rescan=True)
        dlg = OnyxImportDialog(self, Path(path), self.rw, self.im)
        if dlg.exec():
            self.refresh()

    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _open_folder(inst):
        import os, subprocess
        p = str(inst.path)
        if os.name == 'nt':
            subprocess.Popen(['explorer', p])
        else:
            subprocess.Popen(['xdg-open', p])

    # ── Workshop ─────────────────────────────────────────────────

    def _on_workshop(self):
        for w in self._child_windows:
            if w.isVisible() and w.windowTitle().startswith("Steam Workshop"):
                w.raise_()
                w.activateWindow()
                return

        from app.ui.workshop import WorkshopBrowserDialog
        installed = self.rw.get_installed_mods(self._all_mod_paths(), force_rescan=True)
        ws_ids = {info.workshop_id for info in installed.values() if info.workshop_id}
        method = DownloadMethod(self.settings.get('download_method', 'steamcmd'))

        dlg = WorkshopBrowserDialog(
            None,
            self.steamcmd, self.rw,
            api_key=self.settings.get('steam_api_key', ''),
            installed_workshop_ids=ws_ids,
            download_method=method,
            is_steam_copy=self.settings.get('is_steam_copy', False),
            settings=self.settings)
        dlg.destroyed.connect(lambda: self._on_child_closed(dlg))
        self._open_child(dlg)

    def _on_child_closed(self, dlg):
        if dlg in self._child_windows:
            self._child_windows.remove(dlg)
        self.rw.get_installed_mods(self._all_mod_paths(), force_rescan=True)
        self.refresh()

    # ── Logs ─────────────────────────────────────────────────────

    def _on_logs(self):
        from app.ui.log_viewer import LogViewerDialog
        dlg = LogViewerDialog(None, self.log_parser, self.detail.current_instance)
        self._open_child(dlg)

    # ── Settings ─────────────────────────────────────────────────

    def _on_settings(self):
        dlg = SettingsDialog(self, self.settings)
        if dlg.exec():
            self.settings = dlg.get_settings()
            save_json(settings_path(), self.settings)
            self._apply()

    def _apply(self):
        exe = self.settings.get('rimworld_exe', '')
        if exe:
            self.rw.set_game_path(str(Path(exe).parent))
            self.launcher.rimworld_exe = exe
            self.vl.setText(f"RimWorld {self.rw.version}")
        dr = self.settings.get('data_root', '')
        if dr:
            ensure_data_dirs(Path(dr))
            self.im.instances_root = instances_dir(Path(dr))
            self.steamcmd.mods_destination = str(mods_dir(Path(dr)))
            self.dl_queue.destination = str(mods_dir(Path(dr)))
        self.launcher.auto_backup = self.settings.get('auto_backup_on_launch', True)
        self.launcher.backup_count = self.settings.get('backup_count', 3)
        cmd = self.settings.get('steamcmd_path', '')
        if cmd:
            self.steamcmd.steamcmd_path = cmd
            self.dl_queue.steamcmd_path = cmd
        self.dl_queue.username = self.settings.get('steamcmd_username', '')
        self._init_rw()
        self.refresh()

    # ── Auto-detect ──────────────────────────────────────────────

    def _auto_detect(self):
        r = auto_detect_all()
        if r.found_rimworld:
            msg = "Onyx found your RimWorld:\n\n"
            for line in r.logs:
                msg += f"  • {line}\n"
            msg += "\nApply?"
            if QMessageBox.question(self, "Auto-Detect", msg) == QMessageBox.StandardButton.Yes:
                self.settings['rimworld_exe'] = r.rimworld_exe
                self.settings['is_steam_copy'] = r.is_steam_copy
                if r.steam_workshop_path:
                    self.settings['steam_workshop_path'] = r.steam_workshop_path
                if r.steamcmd_path:
                    self.settings['steamcmd_path'] = r.steamcmd_path
                if r.extra_mod_paths:
                    existing = set(self.settings.get('extra_mod_paths', []))
                    existing.update(r.extra_mod_paths)
                    self.settings['extra_mod_paths'] = list(existing)
                self.settings['download_method'] = 'steam_native' if r.is_steam_copy else 'steamcmd'
                save_json(settings_path(), self.settings)
                self._apply()
                QTimer.singleShot(300, self._offer_import)
        else:
            QMessageBox.information(self, "Auto-Detect",
                "Could not find RimWorld.\nSet the path in ⚙ Settings.")

    def _offer_import(self):
        if self.settings.get('offered_import'):
            return
        self.settings['offered_import'] = True
        save_json(settings_path(), self.settings)
        existing = self.im.detect_existing_rw_data()
        if not existing:
            return
        msg = (f"Found existing RimWorld data:\n\n"
               f"  Mods: {existing['mod_count']}  Saves: {existing['save_count']}\n"
               f"  {existing['path']}\n\nImport as instance?")
        if QMessageBox.question(self, "Import", msg) == QMessageBox.StandardButton.Yes:
            try:
                self.im.import_existing_data("Imported - Default", Path(existing['path']))
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _tick(self):
        if self.launcher.is_running():
            self.gl.setText("🎮 Running")
        elif self.gl.text():
            self.gl.setText("")

    def closeEvent(self, e):
        self._timer.stop()
        self.settings['window'] = {
            'width': self.width(), 'height': self.height(),
            'x': self.x(), 'y': self.y()}
        save_json(settings_path(), self.settings)
        for w in list(self._child_windows):
            w.close()
        super().closeEvent(e)