import os
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter,
    QToolBar, QStatusBar, QMessageBox, QLabel, QFileDialog,
    QSizePolicy,
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
from app.core.app_settings import AppSettings
from app.core.mod_watcher import ModWatcher
from app.core.paths import (
    get_default_data_root, ensure_data_dirs, instances_dir, mods_dir,
)
from app.ui.instance_list import InstanceGridPanel
from app.ui.instance_detail import InstanceDetailPanel
from app.ui.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self._s = AppSettings.instance()
        self.settings = self._s.as_dict()
        for k, v in {
            'rimworld_exe': '', 'data_root': '', 'steam_api_key': '',
            'steamcmd_path': '', 'steam_workshop_path': '',
            'extra_mod_paths': [], 'download_method': 'steamcmd',
            'is_steam_copy': False,
            'window': {'width': 1200, 'height': 720, 'x': 80, 'y': 60},
            'auto_backup_on_launch': True, 'backup_count': 3,
            'steamcmd_username': '', 'offered_import': False,
        }.items():
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
        from app.ui.modeditor.download_manager import DownloadManagerWindow
        self._download_manager = DownloadManagerWindow(self.dl_queue, self)
        self.log_parser = LogParser()
        self._child_windows: list = []

        self._mod_watcher = ModWatcher(self)
        self._mod_watcher.mods_changed.connect(self._on_mods_changed_on_disk)
        self._update_watcher_paths()

        self._build_toolbar()
        self._build_ui()
        self._build_statusbar()
        self.refresh()

        self._install_shortcuts()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(5000)

        self._apply_theme()

        if not self.settings.get('rimworld_exe'):
            QTimer.singleShot(400, self._auto_detect)
        elif not self.settings.get('offered_import'):
            QTimer.singleShot(600, self._offer_import)
        if self._s.update_check_mode == 'auto':
            QTimer.singleShot(3000, self._auto_check_updates)


    # ── RimWorld / mod scan helpers ───────────────────────────────────────────

    def _all_mod_paths(self) -> list[str]:
        paths: list[str] = []
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

    def _init_rw(self):
        self.rw._mods_cache.clear()
        self.rw._cache_time = 0.0
        exe = self.settings.get('rimworld_exe', '')
        if exe and Path(exe).exists():
            self.rw.set_game_path(str(Path(exe).parent))
        self.rw.get_installed_mods(self._all_mod_paths(), force_rescan=True)

    def _rescan_mods(self):
        return self.rw.get_installed_mods(self._all_mod_paths(),
                                          force_rescan=True,
                                          max_age_seconds=0)

    # ── File watcher ──────────────────────────────────────────────────────────

    def _update_watcher_paths(self):
        self._mod_watcher.update_paths(
            extra_mod_paths=self.settings.get('extra_mod_paths', []),
            steam_workshop_path=self.settings.get('steam_workshop_path', ''),
            rimworld_exe=self.settings.get('rimworld_exe', ''),
        )

    def _on_mods_changed_on_disk(self):
        self._rescan_mods()
        self.refresh()
        self.sl.setText("Mods updated")

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self, force: bool = False):
        from PyQt6.QtWidgets import QApplication
        from app.ui.styles import DARK_STYLESHEET, LIGHT_STYLESHEET
        app        = QApplication.instance()
        new_theme  = self._s.theme
        last_theme = getattr(self, '_last_theme', None)

        sheet = DARK_STYLESHEET if new_theme == 'dark' else LIGHT_STYLESHEET
        app.setStyleSheet(sheet)

        # Only repaint all widgets when theme actually changed
        if force or new_theme != last_theme:
            self._last_theme = new_theme
            for widget in app.allWidgets():
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()

        if self.detail.current_instance is not None:
            self.detail.actions.set_enabled(True)
        else:
            self.detail.actions.set_enabled(False)

    # ── Shortcuts ─────────────────────────────────────────────────────────────

    def _install_shortcuts(self):
        from PyQt6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self._on_new)
        QShortcut(QKeySequence(Qt.Key.Key_F5), self).activated.connect(
            lambda: self.refresh(rescan_mods=False))
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(
            lambda: self.refresh(rescan_mods=True))

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        tb.addAction(QAction("➕ Add Instance",  self, triggered=self._on_new))
        tb.addAction(QAction("◆ Import .onyx",  self, triggered=self._on_import_pack))
        tb.addSeparator()
        tb.addAction(QAction("🏪 Workshop",      self, triggered=self._on_workshop))
        tb.addAction(QAction("📋 Logs",          self, triggered=self._on_logs))
        tb.addSeparator()
        tb.addAction(QAction("Downloads", self,
                             triggered=self._on_downloads))
        tb.addAction(QAction("Library", self,
                             triggered=self._on_library))
        tb.addAction(QAction("Check Updates", self,
                             triggered=self._on_check_updates))
        tb.addSeparator()
        tb.addAction(QAction("⟳ Refresh",        self, triggered=self.refresh))
        spacer = QWidget()
        spacer.setObjectName("toolbarSpacer")
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(QAction("🔍 Find Mod",      self, triggered=self._on_find_mod))
        tb.addAction(QAction("⚙ Settings",       self, triggered=self._on_settings))

    def _build_ui(self):
        c = QWidget()
        c.setObjectName("centralWidget")
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
        self.ml = QLabel("")
        self.ml.setStyleSheet("color:#888;font-size:10px;")
        sb.addPermanentWidget(self.ml)
        self.vl = QLabel(
            f"RimWorld {self.rw.version}" if self.rw.version else "")
        sb.addPermanentWidget(self.vl)
        self.gl = QLabel("")
        sb.addPermanentWidget(self.gl)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self, rescan_mods: bool = False):
        if rescan_mods:
            self._rescan_mods()
        insts = self.im.scan_instances()
        self.grid.set_instances(insts)
        n = len(insts)
        self.sl.setText(f"{n} instance{'s' if n != 1 else ''}")
        # Use cache — don't force rescan on every refresh
        installed = self.rw.get_installed_mods(self._all_mod_paths())
        self.ml.setText(f"{len(installed)} mods installed")

    def _open_child(self, dlg):
        self._child_windows = [w for w in self._child_windows if w.isVisible()]
        self._child_windows.append(dlg)
        dlg.show()

    # ── Instance handlers ─────────────────────────────────────────────────────

    def _on_select(self, inst):
        self.detail.set_instance(inst, self.rw)

    def _on_new(self):
        from app.ui.instance_new_dialog import NewInstanceDialog
        if NewInstanceDialog(self, self.rw, self.im,
                             dl_queue=self.dl_queue).exec():
            self.refresh()

    def _on_launch(self, inst):
        from app.ui.launch_dialog import LaunchDialog

        # Skip dialog if user previously checked "remember"
        if inst.mods_configured:
            from app.core.app_settings import AppSettings
            from pathlib import Path
            _s        = AppSettings.instance()
            dr        = _s.data_root
            exe       = _s.rimworld_exe
            onyx_mods = Path(dr)  / 'mods' if dr  else None
            inst_exe  = getattr(inst, 'rimworld_exe_override', '') or exe
            game_mods = Path(inst_exe).parent / 'Mods' if inst_exe else None

            all_mods  = self.rw.get_installed_mods(self._all_mod_paths())
            r = self.launcher.launch(
                inst,
                inst.launch_args,
                log_to_instance=True,
                onyx_mods_dir=onyx_mods,
                game_mods_dir=game_mods,
                all_mods=all_mods)

            if r and r.success:
                self.sl.setText(f"▶ {inst.name}")
                self.gl.setText("🎮 Running")
                self.refresh()
            elif r:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Launch Failed", r.message)
            return

        # First time or remember unchecked — show dialog
        dlg = LaunchDialog(self, inst, self.launcher)
        if dlg.exec():
            r = dlg.launch_result
            if r and r.success:
                self.sl.setText(f"▶ {inst.name}")
                self.gl.setText("🎮 Running")
                self.refresh()
            elif r:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Launch Failed", r.message)

    def _on_edit(self, inst):
        from app.ui.instance_edit import InstanceEditDialog
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
        name, ok = QInputDialog.getText(
            self, "Copy", "Name:", text=f"{inst.name} (Copy)")
        if ok and name:
            try:
                self.im.duplicate_instance(inst, name)
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_del(self, inst):
        if QMessageBox.warning(
            self, "Delete",
            f"Delete '{inst.name}'?\n"
            f"{inst.save_count} save(s)\n{inst.path}\n\nCannot undo!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.im.delete_instance(inst)
            self.detail.clear()
            self.refresh()

    def _on_export(self, inst):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export", f"{inst.name}_modlist.txt", "Text (*.txt)")
        if path:
            installed = self.rw.get_installed_mods(self._all_mod_paths())
            names     = {pid: info.name for pid, info in installed.items()}
            export_rimsort_modlist(path, inst.mods, names)
            QMessageBox.information(
                self, "Export", f"Exported {len(inst.mods)} mods.")

    # ── .onyx pack handlers ───────────────────────────────────────────────────

    def _on_export_pack(self, inst):
        from app.ui.onyxpack_dialog import OnyxExportDialog
        OnyxExportDialog(self, inst, self.rw).exec()

    def _on_import_pack(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import .onyx", "",
            "Onyx Packs (*.onyx);;All Files (*)")
        if not path:
            return
        from app.ui.onyxpack_dialog import OnyxImportDialog
        self._rescan_mods()
        dlg = OnyxImportDialog(self, Path(path), self.rw, self.im,
                               dl_queue=self.dl_queue)
        if dlg.exec():
            self.refresh()

    # ── Find mod ──────────────────────────────────────────────────────────────

    def _on_find_mod(self):
        from app.ui.mod_search_dialog import ModSearchDialog
        installed = self.rw.get_installed_mods(self._all_mod_paths())
        insts     = self.im.scan_instances()
        ModSearchDialog(self, insts, installed).exec()

    # ── Folder ────────────────────────────────────────────────────────────────

    @staticmethod
    def _open_folder(inst):
        p = str(inst.path)
        if os.name == 'nt':
            subprocess.Popen(['explorer', p])
        else:
            subprocess.Popen(['xdg-open', p])

    # ── Workshop ──────────────────────────────────────────────────────────────

    def _on_workshop(self):
        for w in self._child_windows:
            if w.isVisible() and w.windowTitle().startswith("Steam Workshop"):
                w.raise_()
                w.activateWindow()
                return

        from app.ui.workshop import WorkshopBrowserDialog
        installed = self.rw.get_installed_mods(self._all_mod_paths())
        ws_ids    = {info.workshop_id
                     for info in installed.values() if info.workshop_id}
        method    = DownloadMethod(
            self.settings.get('download_method', 'steamcmd'))

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
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: (self._rescan_mods(), self.refresh()))

    # ── Logs ──────────────────────────────────────────────────────────────────

    def _on_logs(self):
        from app.ui.log_viewer import LogViewerDialog
        inst = self.detail.current_instance
        LogViewerDialog(None, self.log_parser, inst).exec()

    # ── Downloads ──────────────────────────────────────────────────────────────

    def _on_downloads(self):
        self._download_manager.show()
        self._download_manager.raise_()
        self._download_manager.activateWindow()

    def _on_library(self):
        from app.ui.mod_library_dialog import ModLibraryDialog
        from pathlib import Path
        dr = self.settings.get('data_root', '')
        if not dr:
            QMessageBox.warning(
                self, "Library",
                "Data root not configured. Set it in Settings.")
            return
        dlg = ModLibraryDialog(
            self,
            Path(dr) / 'mods',
            download_manager=self._download_manager)
        dlg.exec()
        # Rescan in case mods were deleted
        self._rescan_mods()
        self.refresh()


    # ── Updates ────────────────────────────────────────────────────────────────

    def _on_check_updates(self):
        from app.ui.mod_update_dialog import ModUpdateDialog
        from pathlib import Path
        dr = self.settings.get('data_root', '')
        if not dr:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Check Updates",
                "Data root not configured. Set it in Settings.")
            return
        dlg = ModUpdateDialog(
            self, self.rw, Path(dr),
            download_manager=self._download_manager)
        dlg.exec()

    def _auto_check_updates(self):
        """
        Background update check on startup.
        Shows badge count in status bar if updates found.
        Runs silently — no dialog unless user clicks the status label.
        """
        from pathlib import Path
        import threading
        dr = self.settings.get('data_root', '')
        if not dr:
            return

        rw = self.rw

        def _run():
            try:
                from app.core.mod_update_checker import (
                    ModTimestampStore, check_updates)
                from app.core.paths import mods_dir
                from app.core.app_settings import AppSettings
                _s     = AppSettings.instance()
                paths  = []
                if _s.data_root:
                    paths.append(str(mods_dir(Path(_s.data_root))))
                if _s.steam_workshop_path:
                    paths.append(_s.steam_workshop_path)

                installed = rw.get_installed_mods(extra_mod_paths=paths)
                store     = ModTimestampStore(Path(dr))

                ws_ids:    list[str]      = []
                names:     dict[str, str] = {}
                mod_paths: dict[str, str] = {}

                for pid, info in installed.items():
                    if info.workshop_id:
                        ws_ids.append(info.workshop_id)
                        names[info.workshop_id]     = info.name
                        mod_paths[info.workshop_id] = str(info.path)

                results = check_updates(ws_ids, store, names, mod_paths)
                updates = [r for r in results if r.has_update]

                if updates:
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(
                        0,
                        lambda: self.sl.setText(
                            f"{len(updates)} mod update(s) available — "
                            f"click Check Updates"))
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    # ── Settings ──────────────────────────────────────────────────────────────

    def _on_settings(self):
        dlg = SettingsDialog(self, self.settings)
        if dlg.exec():
            self.settings = dlg.get_settings()
            self._s.update(self.settings)
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
            self.im.instances_root         = instances_dir(Path(dr))
            self.steamcmd.mods_destination = str(mods_dir(Path(dr)))
            self.dl_queue.destination      = str(mods_dir(Path(dr)))
        self.launcher.auto_backup  = self.settings.get('auto_backup_on_launch', True)
        self.launcher.backup_count = self.settings.get('backup_count', 3)
        cmd = self.settings.get('steamcmd_path', '')
        if cmd:
            self.steamcmd.steamcmd_path = cmd
            self.dl_queue.steamcmd_path = cmd
        self.dl_queue.username = self.settings.get('steamcmd_username', '')
        self._update_watcher_paths()
        self._init_rw()
        self._apply_theme(force=True)
        self.refresh()

    # ── Auto-detect ───────────────────────────────────────────────────────────

    def _auto_detect(self):
        r = auto_detect_all()
        if r.found_rimworld:
            msg = "Onyx found your RimWorld:\n\n"
            for line in r.logs:
                msg += f"  • {line}\n"
            msg += "\nApply?"
            if (QMessageBox.question(self, "Auto-Detect", msg)
                    == QMessageBox.StandardButton.Yes):
                self.settings['rimworld_exe']  = r.rimworld_exe
                self.settings['is_steam_copy'] = r.is_steam_copy
                if r.steam_workshop_path:
                    self.settings['steam_workshop_path'] = r.steam_workshop_path
                if r.steamcmd_path:
                    self.settings['steamcmd_path'] = r.steamcmd_path
                if r.extra_mod_paths:
                    existing = set(self.settings.get('extra_mod_paths', []))
                    existing.update(r.extra_mod_paths)
                    self.settings['extra_mod_paths'] = list(existing)
                self.settings['download_method'] = (
                    'steam_native' if r.is_steam_copy else 'steamcmd')
                self._s.update(self.settings)
                self._apply()
                QTimer.singleShot(300, self._offer_import)
        else:
            QMessageBox.information(
                self, "Auto-Detect",
                "Could not find RimWorld.\nSet the path in ⚙ Settings.")

    def _offer_import(self):
        if self.settings.get('offered_import'):
            return
        self.settings['offered_import'] = True
        self._s.update(self.settings)
        existing = self.im.detect_existing_rw_data()
        if not existing:
            return
        msg = (f"Found existing RimWorld data:\n\n"
               f"  Mods: {existing['mod_count']}  "
               f"Saves: {existing['save_count']}\n"
               f"  {existing['path']}\n\nImport as instance?")
        if (QMessageBox.question(self, "Import", msg)
                == QMessageBox.StandardButton.Yes):
            try:
                self.im.import_existing_data(
                    "Imported - Default", Path(existing['path']))
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    # ── Timer tick ────────────────────────────────────────────────────────────

    def _tick(self):
        if self.launcher.is_running():
            self.gl.setText("🎮 Running")
            self._was_running = True
        elif getattr(self, '_was_running', False):
            self._was_running = False
            self.gl.setText("")
            inst = self.detail.current_instance
            if inst and self.launcher._launch_time:
                mins = self.launcher.get_playtime_minutes()
                if mins > 0:
                    inst.total_playtime_minutes += mins
                    inst.save()
                    self.detail.set_instance(inst, self.rw)
                self.launcher._launch_time = None
        else:
            self.gl.setText("")

    def closeEvent(self, e):
        self._timer.stop()
        self._mod_watcher.stop()
        self.settings['window'] = {
            'width': self.width(), 'height': self.height(),
            'x': self.x(), 'y': self.y()}
        self._s.update(self.settings)
        for w in list(self._child_windows):
            w.close()
        super().closeEvent(e)