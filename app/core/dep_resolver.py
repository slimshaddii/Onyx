"""
Dependency resolution: detect missing deps, find workshop IDs, offer downloads.
"""

from dataclasses import dataclass
from typing import Optional
from app.core.rimworld import RimWorldDetector, ModInfo


@dataclass
class ModIssue:
    mod_id: str
    mod_name: str
    issue_type: str  # 'missing_dep', 'version_mismatch', 'not_found', 'outdated'
    severity: str    # 'error', 'warning', 'info'
    message: str
    dep_id: str = ''
    dep_name: str = ''
    workshop_id: str = ''
    fixable: bool = False


def analyze_modlist(mod_ids: list[str], rw: RimWorldDetector,
                    game_version: str = '',
                    ignored_deps: set[str] | None = None,
                    extra_mod_paths: list[str] | None = None,
                    known_workshop_ids: dict[str, str] | None = None,
                    ) -> list[ModIssue]:
    """
    Analyze a mod list for issues.

    Parameters
    ----------
    ignored_deps : set of "mod_id:dep_id" strings.
        Matching dependency pairs are skipped — same format as
        Instance.ignored_deps.
    """
    installed          = rw.get_installed_mods(
        extra_mod_paths=extra_mod_paths or [])
    active_set         = set(mod_ids)
    ignored_deps       = ignored_deps or set()
    known_ws           = known_workshop_ids or {}
    issues: list[ModIssue] = []

    for mid in mod_ids:
        info = installed.get(mid)

        # Not found on disk
        if not info:
            ws_id = known_ws.get(mid, '')
            issues.append(ModIssue(
                mod_id=mid, mod_name=mid,
                issue_type='not_found', severity='error',
                message='Not found on disk',
                workshop_id=ws_id,
                fixable=bool(ws_id)))
            continue

        # Missing dependencies
        dep_alts = getattr(info, 'dep_alternatives', {})
        for dep in getattr(info, 'dependencies', []):
            if dep in active_set:
                continue
            # Check if any alternative package satisfies this dependency
            alternatives = dep_alts.get(dep, [])
            if any(alt in active_set for alt in alternatives):
                continue  # satisfied by an alternative
            dep_key = f"{mid}:{dep}"
            if dep_key in ignored_deps:
                continue  # user suppressed this warning

                dep_info = installed.get(dep)
                dep_name = dep_info.name if dep_info else dep
                on_disk  = dep in installed

                if on_disk:
                    issues.append(ModIssue(
                        mod_id=mid, mod_name=info.name,
                        issue_type='missing_dep', severity='warning',
                        message=f"Requires '{dep_name}' (available, not active)",
                        dep_id=dep, dep_name=dep_name, fixable=True))
                else:
                    ws_id = known_ws.get(dep, '')
                    if not ws_id and dep_info:
                        ws_id = dep_info.workshop_id
                    issues.append(ModIssue(
                        mod_id=mid, mod_name=info.name,
                        issue_type='missing_dep', severity='error',
                        message=f"Requires '{dep_name}' (NOT INSTALLED)",
                        dep_id=dep, dep_name=dep_name,
                        workshop_id=ws_id, fixable=bool(ws_id)))

        # Version mismatch
        if game_version and info.supported_versions:
            major_minor = game_version.split('.')[:2]
            gv_short    = '.'.join(major_minor) if len(major_minor) >= 2 \
                          else game_version
            if gv_short not in info.supported_versions:
                partial = any(v.startswith(gv_short.split('.')[0] + '.')
                              for v in info.supported_versions)
                issues.append(ModIssue(
                    mod_id=mid, mod_name=info.name,
                    issue_type='version_mismatch',
                    severity='warning' if partial else 'error',
                    message=f"Supports {', '.join(info.supported_versions)} "
                            f"(game is {gv_short})",
                    workshop_id=info.workshop_id))

    return issues


def get_downloadable_deps(issues: list[ModIssue]) -> list[tuple[str, str]]:
    seen, result = set(), []
    for issue in issues:
        # Download missing deps that aren't installed
        if (issue.issue_type == 'missing_dep' and
                issue.workshop_id and issue.severity == 'error'):
            if issue.dep_id not in seen:
                seen.add(issue.dep_id)
                result.append((issue.workshop_id, issue.dep_name))
        # Also download mods that aren't found on disk at all
        elif (issue.issue_type == 'not_found' and
              issue.workshop_id):
            if issue.mod_id not in seen:
                seen.add(issue.mod_id)
                result.append((issue.workshop_id, issue.mod_name))
    return result

def get_activatable_deps(issues: list[ModIssue]) -> list[str]:
    seen, result = set(), []
    for issue in issues:
        if (issue.issue_type == 'missing_dep' and
                issue.severity == 'warning' and issue.dep_id not in seen):
            seen.add(issue.dep_id)
            result.append(issue.dep_id)
    return result