"""
Dependency resolution: detect missing deps, find workshop IDs,
offer downloads.
"""

from dataclasses import dataclass

from app.core.rimworld import RimWorldDetector


# ── ModIssue ──────────────────────────────────────────────────────────────────

@dataclass
class ModIssue:
    """
    Represents a single issue found in an active mod list.

    issue_type values : 'missing_dep' | 'version_mismatch'
                        | 'not_found'
    severity values   : 'error' | 'warning' | 'info'
    """

    mod_id:      str
    mod_name:    str
    issue_type:  str
    severity:    str
    message:     str
    dep_id:      str = ''
    dep_name:    str = ''
    workshop_id: str = ''
    fixable:     bool = False


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_modlist(
        mod_ids:            list[str],
        rw:                 RimWorldDetector,
        game_version:       str = '',
        ignored_deps:       set[str] | None = None,
        extra_mod_paths:    list[str] | None = None,
        known_workshop_ids: dict[str, str] | None = None,
) -> list[ModIssue]:
    """
    Analyze an active mod list and return all detected issues.

    Parameters
    ----------
    mod_ids            : Ordered list of active package IDs.
    rw                 : RimWorldDetector for installed mods.
    game_version       : Full or short version string.
    ignored_deps       : 'mod_id:dep_id' pairs to suppress.
    extra_mod_paths    : Additional mod directories to scan.
    known_workshop_ids : Fallback package_id to workshop_id map.
    """
    installed    = rw.get_installed_mods(
        extra_mod_paths=extra_mod_paths)
    active_set   = set(mod_ids)
    ignored_deps = ignored_deps or set()
    known_ws     = known_workshop_ids or {}
    gv_short     = _short_version(game_version)
    issues: list[ModIssue] = []

    for mid in mod_ids:
        info = installed.get(mid)
        if not info:
            issues.extend(_check_not_found(mid, known_ws))
            continue
        issues.extend(_check_missing_deps(
            mid, info, active_set,
            installed, ignored_deps, known_ws))
        issues.extend(_check_version(
            mid, info, game_version, gv_short))

    return issues


def get_downloadable_deps(
        issues: list[ModIssue],
) -> list[tuple[str, str]]:
    """
    Return (workshop_id, name) pairs for downloadable mods.

    Covers missing deps and not-found mods that have a known
    workshop ID.  Deduplicates by dep_id / mod_id.
    """
    seen:   set[str]              = set()
    result: list[tuple[str, str]] = []

    for issue in issues:
        if (issue.issue_type == 'missing_dep'
                and issue.severity == 'error'
                and issue.workshop_id
                and issue.dep_id not in seen):
            seen.add(issue.dep_id)
            result.append(
                (issue.workshop_id, issue.dep_name))

        elif (issue.issue_type == 'not_found'
              and issue.workshop_id
              and issue.mod_id not in seen):
            seen.add(issue.mod_id)
            result.append(
                (issue.workshop_id, issue.mod_name))

    return result


def get_activatable_deps(
        issues: list[ModIssue],
) -> list[str]:
    """
    Return dep_ids for missing deps that are installed but
    not active.  Deduplicates so each dep_id appears once.
    """
    seen:   set[str]  = set()
    result: list[str] = []

    for issue in issues:
        if (issue.issue_type == 'missing_dep'
                and issue.severity == 'warning'
                and issue.dep_id not in seen):
            seen.add(issue.dep_id)
            result.append(issue.dep_id)

    return result


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _short_version(game_version: str) -> str:
    """
    Convert a full version string to 'major.minor' format.

    '1.6.4630 rev467' -> '1.6'
    '1.6'             -> '1.6'
    ''                -> ''
    """
    if not game_version:
        return ''
    parts = game_version.split('.')[:2]
    return ('.'.join(parts)
            if len(parts) >= 2 else game_version)


def _check_not_found(
        mid: str,
        known_ws: dict[str, str],
) -> list[ModIssue]:
    """Return a not_found issue for a mod with no disk entry."""
    ws_id = known_ws.get(mid, '')
    return [ModIssue(
        mod_id=mid, mod_name=mid,
        issue_type='not_found', severity='error',
        message='Not found on disk',
        workshop_id=ws_id,
        fixable=bool(ws_id),
    )]


def _check_missing_deps(
        mid:          str,
        info:         object,
        active_set:   set[str],
        installed:    dict,
        ignored_deps: set[str],
        known_ws:     dict[str, str],
) -> list[ModIssue]:
    """
    Check all declared dependencies and return issues for any
    that are missing.

    Skips deps that are active, satisfied by an alternative,
    or ignored.
    """
    issues:   list[ModIssue] = []
    dep_alts: dict           = getattr(
        info, 'dep_alternatives', {})

    for dep in getattr(info, 'dependencies', []):
        if dep in active_set:
            continue
        if any(alt in active_set
               for alt in dep_alts.get(dep, [])):
            continue
        if f"{mid}:{dep}" in ignored_deps:
            continue

        dep_info = installed.get(dep)
        dep_name = dep_info.name if dep_info else dep
        on_disk  = dep in installed

        if on_disk:
            issues.append(ModIssue(
                mod_id=mid, mod_name=info.name,
                issue_type='missing_dep',
                severity='warning',
                message=(f"Requires '{dep_name}' "
                         f"(available, not active)"),
                dep_id=dep, dep_name=dep_name,
                fixable=True,
            ))
        else:
            ws_id = known_ws.get(dep, '')
            issues.append(ModIssue(
                mod_id=mid, mod_name=info.name,
                issue_type='missing_dep',
                severity='error',
                message=(f"Requires '{dep_name}' "
                         f"(NOT INSTALLED)"),
                dep_id=dep, dep_name=dep_name,
                workshop_id=ws_id,
                fixable=bool(ws_id),
            ))

    return issues


def _check_version(
        mid:          str,
        info:         object,
        game_version: str,
        gv_short:     str,
) -> list[ModIssue]:
    """
    Return a version_mismatch issue if the mod does not
    support the game version.

    Severity is 'warning' if the mod supports any version
    with the same major number, 'error' otherwise.
    """
    if (not game_version
            or not getattr(info, 'supported_versions', [])):
        return []
    if gv_short in info.supported_versions:
        return []

    major = gv_short.split('.')[0] + '.'
    partial_match = any(
        v.startswith(major)
        for v in info.supported_versions)

    return [ModIssue(
        mod_id=mid, mod_name=info.name,
        issue_type='version_mismatch',
        severity='warning' if partial_match else 'error',
        message=(
            f"Supports "
            f"{', '.join(info.supported_versions)} "
            f"(game is {gv_short})"),
        workshop_id=getattr(info, 'workshop_id', ''),
    )]
