"""Save and backup logic for ModEditorDialog."""

from pathlib import Path
from PyQt6.QtWidgets import QMessageBox

from app.core.modlist import (
    write_mods_config, read_mods_config, VANILLA_AND_DLCS,
)
from app.core.mod_linker import sync_instance_mods
from app.core.dep_resolver import analyze_modlist
from app.core.mod_history import ModHistory
from app.core.paths import settings_path
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
        if not self.inst.has_saves:
            return
        if not self._mods_changed_from_original():
            return
        backup_root = self.inst.path / '_save_backups'
        try:
            backup_folder(self.inst.saves_dir, backup_root, max_backups=3)
        except Exception:
            pass

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

        # Phase 7.2 — record history snapshot on every successful save
        try:
            ModHistory(self.inst.path).record(active_ids, 'Auto-save')
        except Exception:
            pass   # history failure must never block a save

        s   = load_json(settings_path(), {})
        dr  = s.get('data_root', '')
        exe = s.get('rimworld_exe', '')
        if dr and exe:
            r = sync_instance_mods(
                active_ids, self.all_mods,
                Path(exe).parent / 'Mods',
                Path(dr) / 'mods')
            if r['failed']:
                QMessageBox.warning(
                    self, "Sync",
                    f"Failed: {', '.join(r['errors'][:3])}")

        self.accept()