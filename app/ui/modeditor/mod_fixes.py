"""Fix Issues / download flow for ModEditorDialog."""

from pathlib import Path
from PyQt6.QtWidgets import QMessageBox

from app.core.dep_resolver import (
    analyze_modlist, get_downloadable_deps, get_activatable_deps,
)
from app.core.steamcmd import DownloadQueue
from app.core.paths import settings_path
from app.utils.file_utils import load_json
from app.ui.modeditor.issue_checker import (
    get_issue_mod_ids, check_load_order,
)


class ModFixes:
    """
    Mixin for ModEditorDialog.
    Requires: self.active, self.avail, self.inst, self.rw,
              self.all_mods, self.names,
              self._ignored_deps_set(), self._avail_ids(),
              self._mk_active(), self._refresh_badges(),
              self._refresh_inner(), self._update(),
              self._filter_issues, self.active.filter_by_ids()
    """

    def _fix(self):
        ids    = self.active.get_ids()
        issues = analyze_modlist(ids, self.rw,
                                 self.inst.rimworld_version or '',
                                 ignored_deps=self._ignored_deps_set())
        if not issues:
            QMessageBox.information(self, "Fix Issues", "No issues found.")
            return

        activatable  = get_activatable_deps(issues)
        downloadable = get_downloadable_deps(issues)
        activated    = 0

        for dep in activatable:
            if dep in self.all_mods and dep not in set(self.active.get_ids()):
                for i in range(self.avail.count()):
                    if self.avail.item(i).data(0x0100) == dep:
                        self.avail.takeItem(i)
                        break
                self._mk_active(dep)
                activated += 1

        if downloadable:
            self._offer_download(downloadable, activated)
            return
        self._show_fix_report(issues, activated, [])

    def _offer_download(self, downloadable: list, already_activated: int):
        mod_list = "\n".join(
            f"  - {name} ({wid})" for wid, name in downloadable[:10])
        if len(downloadable) > 10:
            mod_list += f"\n  ... and {len(downloadable) - 10} more"
        msg = (f"{len(downloadable)} mod(s) need downloading:"
               f"\n\n{mod_list}\n\nDownload now?")
        if already_activated:
            msg = f"[FIXED] Activated {already_activated} dep(s).\n\n" + msg

        if QMessageBox.question(
                self, "Download Required", msg,
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self._start_download(downloadable)
        else:
            issues = analyze_modlist(
                self.active.get_ids(), self.rw,
                self.inst.rimworld_version or '',
                ignored_deps=self._ignored_deps_set())
            self._show_fix_report(issues, already_activated, [])

    def _start_download(self, mods_to_download: list):
        from app.ui.modeditor.download_dialog import DownloadProgressDialog
        s             = load_json(settings_path(), {})
        steamcmd_path = s.get('steamcmd_path', '')
        data_root     = s.get('data_root', '')

        if not steamcmd_path or not Path(steamcmd_path).exists():
            QMessageBox.warning(self, "SteamCMD Not Configured",
                                "Set the SteamCMD path in Settings.")
            return
        if not data_root:
            QMessageBox.warning(self, "Error", "Data root not configured.")
            return

        queue = DownloadQueue(
            steamcmd_path=steamcmd_path,
            destination=str(Path(data_root) / 'mods'),
            max_concurrent=2,
            username=s.get('steamcmd_username', ''))
        dlg = DownloadProgressDialog(self, queue, mods_to_download)
        dlg.downloads_complete.connect(self._on_downloads_complete)
        dlg.exec()

    def _on_downloads_complete(self, results: list):
        ok  = sum(1 for _, s, _ in results if s)
        bad = len(results) - ok

        if ok:
            self.all_mods = self.rw.get_installed_mods(force_rescan=True)
            self.names    = {pid: i.name for pid, i in self.all_mods.items()}
            issues        = analyze_modlist(
                self.active.get_ids(), self.rw,
                self.inst.rimworld_version or '')
            newly = 0
            for dep in get_activatable_deps(issues):
                if (dep in self.all_mods and
                        dep not in set(self.active.get_ids())):
                    self._mk_active(dep)
                    newly += 1
            msg = f"Downloaded {ok} mod(s)."
            if newly:
                msg += f"\nActivated {newly} dep(s)."
            if bad:
                msg += f"\n\n{bad} download(s) failed."
            QMessageBox.information(self, "Downloads Complete", msg)
        elif bad:
            QMessageBox.warning(self, "Downloads Failed",
                                f"All {bad} download(s) failed.")

        self.active.apply_item_widgets()
        self._refresh_inner()
        issues = analyze_modlist(
            self.active.get_ids(), self.rw,
            self.inst.rimworld_version or '',
            ignored_deps=self._ignored_deps_set())
        if issues:
            self._show_fix_report(issues, 0, results)

    def _show_fix_report(self, issues: list, activated: int,
                         dl_results: list):
        order       = self.active.get_ids()
        order_count = sum(
            len(check_load_order(mid, self.all_mods.get(mid),
                                 order, self.all_mods))
            for mid in order if self.all_mods.get(mid))

        unfixable    = [i for i in issues
                        if i.issue_type == 'missing_dep'
                        and i.severity == 'error' and not i.workshop_id]
        not_found    = [i for i in issues if i.issue_type == 'not_found']
        ver_issues   = [i for i in issues
                        if i.issue_type == 'version_mismatch']
        downloadable = [i for i in issues
                        if i.issue_type == 'missing_dep'
                        and i.severity == 'error' and i.workshop_id]

        report, has_errors = [], False

        if activated:
            report.append(f"[FIXED] Activated {activated} dep(s)")
        if dl_results:
            ok  = sum(1 for _, s, _ in dl_results if s)
            bad = len(dl_results) - ok
            if ok:
                report.append(f"[DOWNLOADED] {ok} mod(s)")
            if bad:
                report.append(f"[FAILED] {bad} mod(s)")
                has_errors = True
        if downloadable:
            report.append(f"\n[NEED DOWNLOAD] {len(downloadable)} mod(s)")
            has_errors = True
        if unfixable:
            report.append(
                f"\n[MISSING - NO WS ID] {len(unfixable)} mod(s):")
            for iss in unfixable[:5]:
                report.append(f"   - {iss.mod_name} needs '{iss.dep_name}'")
            report.append("Find and install these manually.")
            has_errors = True
        if not_found:
            report.append(f"\n[NOT INSTALLED] {len(not_found)} mod(s):")
            for iss in not_found[:5]:
                report.append(f"   - {iss.mod_name}")
            has_errors = True
        if ver_issues:
            report.append(
                f"\n[VERSION WARNING] "
                f"{len(ver_issues)} mod(s) may be incompatible")
        if order_count:
            report.append(
                f"\n[LOAD ORDER] {order_count} issue(s) "
                f"— click Auto-Sort to fix")

        if not report:
            QMessageBox.information(self, "Fix Issues", "All issues resolved.")
        elif not has_errors and not order_count:
            QMessageBox.information(self, "Fix Issues",
                                    "Fixed:\n\n" + '\n'.join(report))
        else:
            QMessageBox.warning(self, "Fix Issues — Action Required",
                                '\n'.join(report))

        self.active.apply_item_widgets()
        self._refresh_inner()

    def _refresh_inner(self):
        mods = self.active.get_ids()
        self.active.clear()
        self._batch_load_active(mods)
        if self._filter_issues:
            ids = get_issue_mod_ids(
                self.active.get_ids(), self.all_mods,
                self.inst.rimworld_version or '')
            self.active.filter_by_ids(ids)