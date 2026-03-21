"""Fix Issues / download flow for ModEditorDialog."""

from pathlib import Path

from PyQt6.QtWidgets import QMessageBox  # pylint: disable=no-name-in-module

from app.core.app_settings import AppSettings
from app.core.dep_resolver import (
    analyze_modlist, get_downloadable_deps,
    get_activatable_deps,
)
from app.core.paths import mods_dir
from app.core.steamcmd import DownloadQueue
from app.ui.modeditor.issue_checker import (
    check_load_order,
)


# ── ModFixes Mixin ───────────────────────────────────────────

class ModFixes:
    """Mixin for ModEditorDialog.

    Requires: self.active, self.avail, self.inst,
              self.rw, self.all_mods, self.names,
              self._ignored_deps_set(),
              self._avail_ids(),
              self._mk_active(),
              self._refresh_badges(),
              self._refresh_inner(),
              self._update(),
              self._update_empty_hint(),
              self._filter_on,
              self._apply_filter(),
              self.active.filter_by_ids()
    """

    # pylint: disable=no-member,attribute-defined-outside-init

    def _fix(self):
        ids    = self.active.get_ids()
        issues = analyze_modlist(
            ids, self.rw,
            self.inst.rimworld_version or '',
            ignored_deps=(
                self._ignored_deps_set()),
            extra_mod_paths=(
                self._extra_mod_paths()),
            known_workshop_ids=(
                self._known_workshop_ids()))

        if not issues:
            QMessageBox.information(
                self, "Fix Issues",
                "No issues found.")
            return

        activatable  = get_activatable_deps(issues)
        downloadable = get_downloadable_deps(issues)
        activated    = 0

        current_active = set(self.active.get_ids())
        for dep in activatable:
            if (dep in self.all_mods
                    and dep not in current_active):
                for i in range(
                        self.avail.count()):
                    it = self.avail.item(i)
                    if it and it.mid == dep:
                        self.avail.takeItem(i)
                        break
                self._mk_active(dep)
                activated += 1

        self._show_fix_report(
            issues, activated, [])
        if downloadable:
            self._offer_download(
                downloadable, activated)

    def _offer_download(
            self, downloadable: list,
            already_activated: int):
        mod_list = "\n".join(
            f"  - {name} ({wid})"
            for wid, name in downloadable[:10])
        if len(downloadable) > 10:
            mod_list += (
                f"\n  ... and "
                f"{len(downloadable) - 10} more")

        msg = (
            f"{len(downloadable)} mod(s) can be "
            f"downloaded:\n\n{mod_list}\n\n"
            f"Open Download Manager?")
        if already_activated:
            msg = (
                f"Activated {already_activated}"
                f" dep(s).\n\n" + msg)

        if QMessageBox.question(
                self, "Download Mods", msg,
                (QMessageBox.StandardButton.Yes
                 | QMessageBox.StandardButton.No)
        ) == QMessageBox.StandardButton.Yes:
            self._start_download(downloadable)

    def _start_download(
            self, mods_to_download: list):
        _s            = AppSettings.instance()
        steamcmd_path = _s.steamcmd_path
        data_root     = _s.data_root
        username      = _s.steamcmd_username

        if (not steamcmd_path
                or not Path(
                    steamcmd_path).exists()):
            QMessageBox.warning(
                self,
                "SteamCMD Not Configured",
                "Set the SteamCMD path "
                "in Settings.")
            return
        if not data_root:
            QMessageBox.warning(
                self, "Error",
                "Data root not configured.")
            return

        from app.ui.modeditor.download_manager import DownloadManagerWindow  # pylint: disable=import-outside-toplevel
        _queue = DownloadQueue(
            steamcmd_path=steamcmd_path,
            destination=str(
                Path(data_root) / 'mods'),
            max_concurrent=2,
            username=username)

        _mgr = DownloadManagerWindow(
            _queue, self)
        _mgr.queue_and_show(mods_to_download)

        _queue.queue_empty.connect(
            lambda:
                self._on_fix_downloads_complete(
                    _queue=_queue, _mgr=_mgr))

    def _on_fix_downloads_complete(
            self, _queue, _mgr):
        self.all_mods = self.rw.get_installed_mods(
            extra_mod_paths=(
                self._extra_mod_paths()),
            force_rescan=True,
            max_age_seconds=0)
        self.names = {
            pid: i.name
            for pid, i in self.all_mods.items()
        }

        issues = analyze_modlist(
            self.active.get_ids(), self.rw,
            self.inst.rimworld_version or '',
            ignored_deps=(
                self._ignored_deps_set()),
            extra_mod_paths=(
                self._extra_mod_paths()),
            known_workshop_ids=(
                self._known_workshop_ids()))

        newly = 0
        for dep in get_activatable_deps(issues):
            if (dep in self.all_mods
                    and dep not in set(
                        self.active.get_ids())):
                for i in range(
                        self.avail.count()):
                    it = self.avail.item(i)
                    if it and it.mid == dep:
                        self.avail.takeItem(i)
                        break
                self._mk_active(dep)
                newly += 1

        if newly:
            self.avail.apply_item_widgets()
            self._update_empty_hint()
            self.active.apply_item_widgets()
            self._refresh_inner()

        if issues:
            self._show_fix_report(
                issues, newly, [])

    def _show_fix_report(
            self, issues: list,
            activated: int,
            dl_results: list):
        order = self.active.get_ids()
        _pos  = {
            m: i for i, m in enumerate(order)
        }

        order_count = sum(
            len(check_load_order(
                mid, self.all_mods.get(mid),
                order, self.all_mods, _pos))
            for mid in order
            if self.all_mods.get(mid))

        unfixable = [
            i for i in issues
            if i.issue_type == 'missing_dep'
            and i.severity == 'error'
            and not i.workshop_id
        ]
        not_found = [
            i for i in issues
            if i.issue_type == 'not_found'
        ]
        ver_issues = [
            i for i in issues
            if i.issue_type == 'version_mismatch'
        ]
        downloadable = [
            i for i in issues
            if i.issue_type == 'missing_dep'
            and i.severity == 'error'
            and i.workshop_id
        ]

        report: list[str] = []
        has_errors = False

        if activated:
            report.append(
                f"[FIXED] Activated "
                f"{activated} dep(s)")
        if dl_results:
            ok  = sum(
                1 for _, s, _ in dl_results if s)
            bad = len(dl_results) - ok
            if ok:
                report.append(
                    f"[DOWNLOADED] {ok} mod(s)")
            if bad:
                report.append(
                    f"[FAILED] {bad} mod(s)")
                has_errors = True
        if downloadable:
            report.append(
                f"\n[NEED DOWNLOAD] "
                f"{len(downloadable)} mod(s)")
            has_errors = True
        if unfixable:
            report.append(
                f"\n[MISSING - NO WS ID] "
                f"{len(unfixable)} mod(s):")
            for iss in unfixable[:5]:
                report.append(
                    f"   - {iss.mod_name} needs "
                    f"'{iss.dep_name}'")
            report.append(
                "Find and install these "
                "manually.")
            has_errors = True
        if not_found:
            report.append(
                f"\n[NOT INSTALLED] "
                f"{len(not_found)} mod(s):")
            for iss in not_found[:5]:
                report.append(
                    f"   - {iss.mod_name}")
            has_errors = True
        if ver_issues:
            report.append(
                f"\n[VERSION WARNING] "
                f"{len(ver_issues)} mod(s) "
                f"may be incompatible")
        if order_count:
            report.append(
                f"\n[LOAD ORDER] "
                f"{order_count} issue(s) "
                f"— click Auto-Sort to fix")

        if not report:
            QMessageBox.information(
                self, "Fix Issues",
                "All issues resolved.")
        elif not has_errors and not order_count:
            QMessageBox.information(
                self, "Fix Issues",
                "Fixed:\n\n"
                + '\n'.join(report))
        else:
            QMessageBox.warning(
                self,
                "Fix Issues — Action Required",
                '\n'.join(report))

        self.active.apply_item_widgets()
        self._refresh_inner()

    def _refresh_inner(self):
        mods = self.active.get_ids()
        self.active.clear()
        self._batch_load_active(mods)
        if self._filter_on:
            self._apply_filter()

    def _extra_mod_paths(self) -> list[str]:
        """Return extra mod scan paths from settings."""
        _s    = AppSettings.instance()
        paths: list[str] = []
        if _s.data_root:
            paths.append(
                str(mods_dir(Path(_s.data_root))))
        if _s.steam_workshop_path:
            paths.append(_s.steam_workshop_path)
        return paths

    def _known_workshop_ids(
            self) -> dict[str, str]:
        """Build workshop ID map from installed
        mod metadata and instance store."""
        result: dict[str, str] = {}
        for mid, info in self.all_mods.items():
            if info.workshop_id:
                result[mid] = info.workshop_id
        result.update(self.inst.mod_workshop_ids)
        return result

    # pylint: enable=no-member,attribute-defined-outside-init
