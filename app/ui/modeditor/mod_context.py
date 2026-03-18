"""Context menus, delete, redownload, and dep-ignore for ModEditorDialog."""

import shutil
from pathlib import Path
from PyQt6.QtWidgets import QMenu, QMessageBox
from PyQt6.QtCore import Qt

from app.core.steamcmd import DownloadQueue
from app.core.modlist import VANILLA_AND_DLCS


class ModContext:
    """
    Mixin for ModEditorDialog.
    Requires: self.active, self.avail, self.inst, self.rw,
              self.all_mods, self.names,
              self._rem_sel(), self._add_sel(),
              self._remove_from_instance_batch(),
              self._ignored_deps_set(),
              self._refresh_badges(), self._update(),
              self._update_empty_hint(),
              self.avail.apply_item_widgets()
    """

    def _ctx_active(self, pos):
        it = self.active.itemAt(pos)
        if not it:
            return
        mid  = it.mid
        info = self.all_mods.get(mid)
        m    = QMenu(self)

        rem = m.addAction("Deactivate")
        if mid.lower() == 'ludeon.rimworld':
            rem.setEnabled(False)
            rem.setText("Deactivate (Core — required)")
        else:
            rem.triggered.connect(self._rem_sel)

        if info and info.dependencies:
            active_set = set(self.active.get_ids())
            ignored    = self._ignored_deps_set()

            ignorable = [
                dep for dep in info.dependencies
                if dep not in active_set
                and f"{mid}:{dep}" not in ignored
            ]
            if ignorable:
                m.addSeparator()
                ignore_menu = m.addMenu("Ignore dependency warning…")
                for dep in ignorable:
                    dep_name = self.names.get(dep, dep)
                    dep_key  = f"{mid}:{dep}"
                    ignore_menu.addAction(
                        f"Ignore '{dep_name}'",
                        lambda dk=dep_key: self._ignore_dep(dk))

            already_ignored = [
                dep for dep in info.dependencies
                if f"{mid}:{dep}" in ignored
            ]
            if already_ignored:
                restore_menu = m.addMenu("Remove ignored warning…")
                for dep in already_ignored:
                    dep_name = self.names.get(dep, dep)
                    dep_key  = f"{mid}:{dep}"
                    restore_menu.addAction(
                        f"Restore '{dep_name}'",
                        lambda dk=dep_key: self._restore_dep(dk))

        if (info and info.path and info.path.exists()
                and mid not in VANILLA_AND_DLCS):
            m.addSeparator()
            m.addAction("🗑 Delete mod files…",
                        lambda: self._del_mod(mid))

        if info and info.workshop_id:
            m.addAction("⟳ Redownload from Workshop",
                        lambda: self._redownload_mod(mid))
            from app.core.steam_integration import open_workshop_page
            m.addAction("Workshop page",
                        lambda: open_workshop_page(info.workshop_id))

        m.exec(self.active.mapToGlobal(pos))

    def _ctx_avail(self, pos):
        it = self.avail.itemAt(pos)
        if not it:
            return
        mid      = it.mid
        info     = self.all_mods.get(mid)
        selected = self.avail.selectedItems()
        m        = QMenu(self)
        m.addAction("Activate →", self._add_sel)

        removable = [
            i for i in selected
            if i.mid not in VANILLA_AND_DLCS
        ]
        if removable:
            m.addSeparator()
            label = ("Remove from Instance" if len(removable) == 1
                     else f"Remove {len(removable)} from Instance")
            m.addAction(label,
                        lambda: self._remove_from_instance_batch(removable))

        if (info and info.path and info.path.exists()
                and mid not in VANILLA_AND_DLCS):
            m.addSeparator()
            m.addAction("🗑 Delete mod files…",
                        lambda: self._del_mod(mid))

        if info and info.workshop_id:
            m.addAction("⟳ Redownload from Workshop",
                        lambda: self._redownload_mod(mid))
            from app.core.steam_integration import open_workshop_page
            m.addAction("Workshop page",
                        lambda: open_workshop_page(info.workshop_id))

        m.exec(self.avail.mapToGlobal(pos))

    def _del_mod(self, mid: str):
        info = self.all_mods.get(mid)
        if not info or not info.path:
            QMessageBox.warning(self, "Delete", "Cannot find mod path.")
            return

        name     = info.name
        mod_path = info.path

        if not mod_path.exists():
            QMessageBox.warning(self, "Delete",
                                f"Mod folder not found:\n{mod_path}")
            return

        reply = QMessageBox.question(
            self, "Delete Mod Files",
            f"Permanently delete '{name}'?\n\n"
            f"  {mod_path}\n\n"
            f"This cannot be undone. The mod will be removed from this "
            f"instance and deleted from disk.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)

        if reply != QMessageBox.StandardButton.Yes:
            return

        for lst in (self.active, self.avail):
            for i in range(lst.count()):
                if lst.item(i) and lst.item(i).data(
                        Qt.ItemDataRole.UserRole) == mid:
                    lst.takeItem(i)
                    break

        from app.core.app_settings import AppSettings
        from app.core.mod_linker import delete_mod_permanently
        _s = AppSettings.instance()

        workshop_id   = info.workshop_id or info.path.name
        onyx_mods_dir = Path(_s.data_root) / 'mods' if _s.data_root else None
        game_mods_dir = (Path(_s.rimworld_exe).parent / 'Mods'
                         if _s.rimworld_exe else None)

        if onyx_mods_dir:
            result = delete_mod_permanently(
                workshop_id=workshop_id,
                onyx_mods_dir=onyx_mods_dir,
                game_mods_dir=game_mods_dir or Path(),
                steamcmd_path=_s.steamcmd_path)
            if result['errors']:
                QMessageBox.warning(
                    self, "Delete",
                    "Deleted with warnings:\n" +
                    "\n".join(result['errors']))
        else:
            try:
                shutil.rmtree(str(mod_path))
            except Exception as e:
                QMessageBox.critical(self, "Delete Failed", str(e))
                return

        self.all_mods = self.rw.get_installed_mods(force_rescan=True,
                                                    max_age_seconds=0)
        self.names    = {pid: i.name for pid, i in self.all_mods.items()}

        self.avail.apply_item_widgets()
        self._update_empty_hint()
        self._update()
        QMessageBox.information(self, "Deleted", f"'{name}' was deleted.")

    def _redownload_mod(self, mid: str):
        info = self.all_mods.get(mid)
        if not info or not info.workshop_id:
            QMessageBox.warning(
                self, "Redownload",
                "This mod has no Workshop ID — cannot redownload.")
            return

        from app.core.app_settings import AppSettings
        _s            = AppSettings.instance()
        steamcmd_path = _s.steamcmd_path
        data_root     = _s.data_root

        if not steamcmd_path or not Path(steamcmd_path).exists():
            QMessageBox.warning(
                self, "SteamCMD Not Configured",
                "Set the SteamCMD path in Settings to redownload mods.")
            return
        if not data_root:
            QMessageBox.warning(self, "Error", "Data root not configured.")
            return

        from app.ui.modeditor.download_dialog import DownloadProgressDialog
        queue = DownloadQueue(
            steamcmd_path=steamcmd_path,
            destination=str(Path(data_root) / 'mods'),
            max_concurrent=1,
            username=_s.steamcmd_username)          # ← fixed

        dlg = DownloadProgressDialog(
            self, queue, [(info.workshop_id, info.name)])
        dlg.setWindowTitle(f"Redownloading — {info.name}")
        dlg.downloads_complete.connect(
            lambda results: self._on_redownload_done(results, info.name))
        dlg.exec()

    def _on_redownload_done(self, results: list, mod_name: str):
        ok = sum(1 for _, s, _ in results if s)
        if ok:
            self.all_mods = self.rw.get_installed_mods(force_rescan=True,
                                                        max_age_seconds=0)
            self.names    = {pid: i.name for pid, i in self.all_mods.items()}
            self._refresh_badges()
            self.active.apply_item_widgets()
            QMessageBox.information(
                self, "Redownload Complete",
                f"'{mod_name}' was redownloaded successfully.")
        else:
            msg = results[0][2] if results else "Unknown error"
            QMessageBox.warning(
                self, "Redownload Failed",
                f"Failed to redownload '{mod_name}':\n{msg}")

    def _ignore_dep(self, dep_key: str):
        if dep_key not in self.inst.ignored_deps:
            self.inst.ignored_deps.append(dep_key)
            self.inst.save()
        self._refresh_badges()
        self.active.apply_item_widgets()
        self._update()

    def _restore_dep(self, dep_key: str):
        if dep_key in self.inst.ignored_deps:
            self.inst.ignored_deps.remove(dep_key)
            self.inst.save()
        self._refresh_badges()
        self.active.apply_item_widgets()
        self._update()