"""Add/remove/sort/vanilla/import/export actions for ModEditorDialog."""

from pathlib import Path
from PyQt6.QtWidgets import QMessageBox, QFileDialog

from app.core.modlist import (
    read_mods_config, parse_rimsort_modlist,
    export_rimsort_modlist, get_vanilla_modlist, VANILLA_AND_DLCS,
)
from app.core.mod_sort import auto_sort_mods


class ModActions:
    """
    Mixin for ModEditorDialog.
    Requires: self.active, self.avail, self.inst, self.rw,
              self.all_mods, self.names,
              self._defer_updates, self._filter_on,
              self._mk_active(), self._mk_avail(),
              self._refresh_badges(), self._update(),
              self._update_empty_hint(), self._avail_ids(),
              self._apply_filter()
    """

    def _add_sel(self):
        selected = self.avail.selectedItems()
        if not selected:
            return
        self._defer_updates = True
        self.active.setUpdatesEnabled(False)
        self.avail.setUpdatesEnabled(False)

        # Collect mids then remove in reverse row order
        rows = sorted([self.avail.row(it) for it in selected], reverse=True)
        mids = [it.mid for it in selected]
        for row in rows:
            self.avail.takeItem(row)
        for mid in mids:
            self._mk_active(mid, skip_badges=True)

        self.avail.setUpdatesEnabled(True)
        self.active.setUpdatesEnabled(True)
        self._defer_updates = False

        self._refresh_badges()
        self.active.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _rem_sel(self):
        selected = self.active.selectedItems()
        if not selected:
            return

        to_remove = []
        has_core  = False
        for it in selected:
            if it.mid.lower() == 'ludeon.rimworld':
                has_core = True
            else:
                to_remove.append(it)

        if has_core and not to_remove:
            QMessageBox.warning(self, "Cannot Remove",
                                "Core (ludeon.rimworld) is required.")
            return

        self._defer_updates = True
        self.active.setUpdatesEnabled(False)
        self.avail.setUpdatesEnabled(False)

        rows    = sorted([self.active.row(it) for it in to_remove],
                         reverse=True)
        removed = []
        for row in rows:
            it = self.active.takeItem(row)
            if it:
                removed.append(it.mid)
        for mid in removed:
            if mid in self.all_mods:
                self._mk_avail(mid, self.all_mods[mid])

        self.avail.setUpdatesEnabled(True)
        self.active.setUpdatesEnabled(True)
        self._defer_updates = False

        if has_core:
            QMessageBox.information(
                self, "Note",
                f"Deactivated {len(removed)} mod(s). "
                f"Core was kept (required).")

        self.avail.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _add_all(self):
        self._defer_updates = True
        self.active.setUpdatesEnabled(False)
        self.avail.setUpdatesEnabled(False)

        items = self.avail.popAllItems()
        mids  = [it.mid for it in items if it.mid]
        for mid in mids:
            self._mk_active(mid, skip_badges=True)

        self.avail.setUpdatesEnabled(True)
        self.active.setUpdatesEnabled(True)
        self._defer_updates = False

        self._refresh_badges()
        self.active.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _rem_all(self):
        self._defer_updates = True
        self.active.setUpdatesEnabled(False)
        self.avail.setUpdatesEnabled(False)

        all_items = self.active._model.allItems()
        to_remove = [it for it in all_items
                    if it.mid.lower() != 'ludeon.rimworld']
        keep      = [it for it in all_items
                    if it.mid.lower() == 'ludeon.rimworld']

        self.active._model.beginResetModel()
        self.active._model._items = keep
        self.active._model.endResetModel()

        for it in to_remove:
            if it.mid in self.all_mods:
                self._mk_avail(it.mid, self.all_mods[it.mid])

        self.avail.setUpdatesEnabled(True)
        self.active.setUpdatesEnabled(True)
        self._defer_updates = False

        self.avail.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _on_active_double_click(self, item):
        """Receives a ModItem from DragDropList.itemDoubleClicked."""
        if not item:
            return
        if item.mid.lower() == 'ludeon.rimworld':
            QMessageBox.warning(self, "Cannot Remove",
                                "Core (ludeon.rimworld) is required.")
            return
        row = self.active.row(item)
        if row >= 0:
            self.active.takeItem(row)
        if item.mid in self.all_mods:
            self._mk_avail(item.mid, self.all_mods[item.mid])
        self.avail.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _remove_from_instance_batch(self, items: list):
        """items is list[ModItem]"""
        if not items:
            return
        names = []
        for it in items:
            info = self.all_mods.get(it.mid)
            names.append(info.name if info else it.mid)

        msg  = f"Remove {len(items)} mod(s) from this instance?\n\n"
        msg += "\n".join(f"  - {n}" for n in names[:10])
        if len(names) > 10:
            msg += f"\n  ... and {len(names) - 10} more"
        msg += "\n\nThey will still be available in the Library."

        if QMessageBox.question(self, "Remove from Instance",
                                msg) != QMessageBox.StandardButton.Yes:
            return

        self.avail.setUpdatesEnabled(False)
        rows = sorted([self.avail.row(it) for it in items], reverse=True)
        for row in rows:
            self.avail.takeItem(row)
        self.avail.setUpdatesEnabled(True)
        self.avail.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _sort(self):
        ids = self.active.get_ids()
        if not ids:
            return
        self.all_mods = self.rw.get_installed_mods(force_rescan=True,
                                                    max_age_seconds=0)
        sorted_ids    = auto_sort_mods(ids, self.rw)
        self.active.clear()
        self._batch_load_active(sorted_ids)
        self._update()

    def _vanilla(self):
        if QMessageBox.question(self, "Vanilla",
                                "Reset to Core + DLCs only?"
                                ) != QMessageBox.StandardButton.Yes:
            return
        self._rem_all()
        for mid in get_vanilla_modlist(self.rw.get_detected_dlcs()):
            if mid in set(self.active.get_ids()):
                continue
            self._mk_active(mid)
            # Remove from avail if present
            idx = self.avail._model.indexOfMid(mid)
            if idx >= 0:
                self.avail.takeItem(idx)
        self.active.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _import_file(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Import", "", "Text (*.txt);;XML (*.xml)")
        if not p:
            return
        mods = (read_mods_config(Path(p).parent)[0]
                if p.endswith('.xml')
                else parse_rimsort_modlist(p))
        if not mods:
            return
        self._rem_all()
        active_set = set(self.active.get_ids())
        for mid in mods:
            if mid in active_set:
                continue
            self._mk_active(mid)
            idx = self.avail._model.indexOfMid(mid)
            if idx >= 0:
                self.avail.takeItem(idx)
        self.active.apply_item_widgets()
        self._update_empty_hint()
        self._update()

    def _export(self):
        p, _ = QFileDialog.getSaveFileName(
            self, "Export", "modlist.txt", "Text (*.txt)")
        if p:
            export_rimsort_modlist(p, self.active.get_ids(), self.names)