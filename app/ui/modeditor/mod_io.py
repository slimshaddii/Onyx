"""Save and backup logic for ModEditorDialog."""

import threading
from pathlib import Path
from PyQt6.QtWidgets import QMessageBox

from app.core.modlist import (
    write_mods_config, read_mods_config, VANILLA_AND_DLCS,
)
from app.core.mod_linker import sync_instance_mods
from app.core.dep_resolver import analyze_modlist
from app.core.mod_history import ModHistory
from app.utils.file_utils import load_json, backup_folder


class ModIO:
    """
    Mixin for ModEditorDialog.
    Requires: self.active, self.inst, self.rw, self.all_mods,
              self._avail_ids(), self._ignored_deps_set(),
              self._mods_changed_from_original()
    """

    def _mods_changed_from_original(self) -> bool:
        return set(self.active.get_ids()) != self._original_mods

    def _backup_saves_if_needed(self):
        """
        Backs up saves on a daemon thread so it never blocks the UI.
        Only runs if saves exist and the mod list changed.
        """
        if not self.inst.has_saves:
            return
        if not self._mods_changed_from_original():
            return

        backup_root = self.inst.path / '_save_backups'
        saves_dir   = self.inst.saves_dir

        def _do_backup():
            try:
                backup_folder(saves_dir, backup_root, max_backups=3)
            except Exception:
                pass

        threading.Thread(target=_do_backup, daemon=True).start()

    def _save(self):
        active_ids = self.active.get_ids()
        if not any(m.lower() == 'ludeon.rimworld' for m in active_ids):
            active_ids.insert(0, 'ludeon.rimworld')

        issues   = analyze_modlist(
            active_ids, self.rw,
            self.inst.rimworld_version or '',
            ignored_deps=self._ignored_deps_set())
        critical = [i for i in issues if i.severity == 'error']

        if critical:
            msg     = f"Cannot save: {len(critical)} critical issue(s).\n\n"
            missing = [i for i in critical if i.issue_type == 'missing_dep']
            absent  = [i for i in critical if i.issue_type == 'not_found']
            if missing:
                msg += f"Missing deps ({len(missing)}):\n"
                for iss in missing[:5]:
                    msg += f"  - {iss.mod_name} needs '{iss.dep_name}'\n"
            if absent:
                msg += f"\nNot on disk ({len(absent)}):\n"
                for iss in absent[:5]:
                    msg += f"  - {iss.mod_name}\n"
            msg += "\nUse 'Fix Issues' to resolve."
            QMessageBox.critical(self, "Cannot Save", msg)
            return

        # Backup runs off-thread — never blocks the UI
        self._backup_saves_if_needed()

        inactive_ids = [mid for mid in self._avail_ids()
                        if mid not in VANILLA_AND_DLCS]
        exp          = [m for m in active_ids
                        if m in VANILLA_AND_DLCS
                        and m != 'ludeon.rimworld']

        write_mods_config(
            self.inst.config_dir, active_ids,
            self.inst.rimworld_version or '1.6.4630 rev467',
            exp or None)

        self.inst.mods            = active_ids
        self.inst.inactive_mods   = inactive_ids
        self.inst.mods_configured = True
        self.inst.save()

        # History recording — fast, keep on main thread
        try:
            ModHistory(self.inst.path).record(active_ids, 'Auto-save')
        except Exception:
            pass

        # Close the dialog immediately — don't make user wait for sync
        self.accept()

        # Sync runs off-thread AFTER dialog closes
        # Any sync errors are silent (non-critical — game will still work
        # with the correct ModsConfig.xml, sync just pre-links mod folders)
        self._sync_mods_async(active_ids)

    def _sync_mods_async(self, active_ids: list[str]):
        """
        Run sync_instance_mods on a daemon thread after the dialog closes.
        Errors are non-fatal — the game reads ModsConfig.xml directly.
        """
        from app.core.app_settings import AppSettings
        _s  = AppSettings.instance()
        dr  = _s.data_root
        exe = _s.rimworld_exe

        if not dr or not exe:
            return

        all_mods    = dict(self.all_mods)   # snapshot before dialog is GC'd
        game_mods   = Path(exe).parent / 'Mods'
        onyx_mods   = Path(dr) / 'mods'

        def _do_sync():
            try:
                sync_instance_mods(active_ids, all_mods,
                                   game_mods, onyx_mods)
            except Exception:
                pass   # sync failure is non-fatal

        threading.Thread(target=_do_sync, daemon=True).start()