"""Save and backup logic for ModEditorDialog."""

import threading
from pathlib import Path

from PyQt6.QtWidgets import QMessageBox  # pylint: disable=no-name-in-module

from app.core.app_settings import AppSettings
from app.core.mod_history import ModHistory
from app.core.mod_linker import sync_instance_mods
from app.core.modlist import write_mods_config, VANILLA_AND_DLCS
from app.ui.modeditor.issue_checker import get_badges
from app.utils.file_utils import backup_folder


# ── ModIO Mixin ───────────────────────────────────────────────────────────────

class ModIO:
    """
    Mixin for ModEditorDialog.

    Requires: self.active, self.inst, self.rw, self.all_mods,
              self._avail_ids(), self._ignored_deps_set(),
              self._ignored_errors_set(),
              self._mods_changed_from_original()
    """

    # pylint: disable=no-member

    def _mods_changed_from_original(self) -> bool:
        return (set(self.active.get_ids())
                != self._original_mods)

    def _backup_saves_if_needed(self):
        if not self.inst.has_saves:
            return
        if not self._mods_changed_from_original():
            return
        backup_root = self.inst.path / '_save_backups'
        saves_dir   = self.inst.saves_dir

        def _do_backup():
            try:
                backup_folder(
                    saves_dir, backup_root,
                    max_backups=3)
            except Exception:  # pylint: disable=broad-exception-caught
                # Background backup must never
                # crash the UI thread.
                pass

        threading.Thread(
            target=_do_backup, daemon=True
        ).start()

    def _save(self):
        active_ids = self.active.get_ids()
        if not any(m.lower() == 'ludeon.rimworld'
                   for m in active_ids):
            active_ids.insert(0, 'ludeon.rimworld')

        active_set     = set(active_ids)
        _pos           = {
            m: i for i, m in enumerate(active_ids)
        }
        ignored_deps   = self._ignored_deps_set()
        ignored_errors = self._ignored_errors_set()

        incompat_errors: list[str] = []
        for mid in active_ids:
            for badge in get_badges(
                    mid, self.all_mods, active_set,
                    self.inst.rimworld_version or '',
                    active_ids, _pos,
                    ignored_deps, ignored_errors):
                if (badge[2] == 'error'
                        and 'ncompatible'
                        in badge[3]):
                    name = (
                        self.all_mods[mid].name
                        if mid in self.all_mods
                        else mid)
                    incompat_errors.append(
                        f"  - {name}: {badge[3]}")

        if incompat_errors:
            msg = (
                f"Cannot save: "
                f"{len(incompat_errors)} "
                f"incompatible mod(s).\n\n"
                + "\n".join(
                    incompat_errors[:5]))
            if len(incompat_errors) > 5:
                msg += (
                    f"\n  ... and "
                    f"{len(incompat_errors) - 5}"
                    f" more")
            msg += (
                "\n\nRemove incompatible mods or "
                "add them to the ignore list.")
            QMessageBox.critical(
                self, "Cannot Save", msg)
            return

        self._backup_saves_if_needed()

        inactive_ids = [
            mid for mid in self._avail_ids()
            if mid not in VANILLA_AND_DLCS
        ]
        exp = [
            m for m in active_ids
            if m in VANILLA_AND_DLCS
            and m != 'ludeon.rimworld'
        ]

        write_mods_config(
            self.inst.config_dir, active_ids,
            self.inst.rimworld_version
            or '1.6.4630 rev467',
            exp or None)

        self.inst.mods            = active_ids
        self.inst.inactive_mods   = inactive_ids
        self.inst.mods_configured = True
        self.inst.save()

        try:
            ModHistory(self.inst.path).record(
                active_ids, 'Auto-save')
        except Exception:  # pylint: disable=broad-exception-caught
            # Non-critical history tracking must
            # not block saving.
            pass

        self.accept()
        self._sync_mods_async(active_ids)

    def _sync_mods_async(
            self, active_ids: list[str]):
        _s  = AppSettings.instance()
        dr  = _s.data_root
        exe = _s.rimworld_exe

        if not dr or not exe:
            return

        all_mods  = dict(self.all_mods)
        game_mods = Path(exe).parent / 'Mods'
        onyx_mods = Path(dr) / 'mods'

        def _do_sync():
            try:
                sync_instance_mods(
                    active_ids, all_mods,
                    game_mods, onyx_mods)
            except Exception:  # pylint: disable=broad-exception-caught
                # Background sync must never
                # crash the UI thread.
                pass

        threading.Thread(
            target=_do_sync, daemon=True
        ).start()

    # pylint: enable=no-member
