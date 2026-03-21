"""Issue analysis: missing deps, version mismatch, load order
violations, incompatible mods, and JuMLi community
conflict/performance notices."""

from app.core.rimworld import ModInfo


# ── Severity Constants ────────────────────────────────────────────────────────

COLOR_ERROR      = '#ff4444'
COLOR_DEPENDENCY = '#ff8800'
COLOR_WARNING    = '#ff8800'
COLOR_ORDER      = '#ffaa00'
COLOR_VERSION    = '#ff8800'
COLOR_INFO       = '#888888'

SEVERITY_CONFIG: dict[str, tuple[str, str]] = {
    'error':       ('❌', COLOR_ERROR),
    'dep':         ('📦', COLOR_DEPENDENCY),
    'warning':     ('⚠',  COLOR_WARNING),
    'order':       ('🔃', COLOR_ORDER),
    'performance': ('🐢', COLOR_ORDER),
    'info':        ('ℹ',  COLOR_INFO),
}

_NOTICE_MAP: dict[str, tuple[str, str]] = {
    'incompatible': (COLOR_ERROR,      'error'),
    'unstable':     (COLOR_DEPENDENCY, 'warning'),
    'alternative':  (COLOR_DEPENDENCY, 'warning'),
    'performance':  (COLOR_ORDER,      'performance'),
    'info':         (COLOR_INFO,       'info'),
}


# ── Error Key ─────────────────────────────────────────────────────────────────

def make_error_key(mid: str, sev: str, msg: str) -> str:
    """Build the storage key used in Instance.ignored_errors.

    Format: "mod_id:severity:first_40_chars_of_message",
    lowercased.
    """
    return f"{mid}:{sev}:{msg[:40].strip()}".lower()


# ── Badge Generation ──────────────────────────────────────────────────────────

def get_badges(
        mid: str,
        all_mods: dict[str, ModInfo],
        active_ids: set[str],
        game_version: str,
        active_order: list[str] = None,
        _pos_cache: dict | None = None,
        ignored_deps: set[str] | None = None,
        ignored_errors: set[str] | None = None,
) -> list[tuple[str, str, str, str]]:
    """Return all issue badges for a single active mod."""
    badges         = []
    info           = all_mods.get(mid)
    ignored_deps   = ignored_deps   or set()
    ignored_errors = ignored_errors or set()

    if not info:
        msg = 'Not found on disk'
        key = make_error_key(mid, 'error', msg)
        if key not in ignored_errors:
            badges.append(
                ('❌', COLOR_ERROR, 'error', msg))
        return badges

    _check_missing_deps(
        mid, info, all_mods, active_ids,
        ignored_deps, ignored_errors, badges)
    _check_incompatible(
        mid, info, all_mods, active_ids,
        ignored_errors, badges)
    _check_version(
        mid, info, game_version,
        ignored_errors, badges)
    _check_order(
        mid, info, all_mods, active_order,
        _pos_cache, ignored_errors, badges)
    _check_juml_notices(
        mid, info, ignored_errors, badges)

    return badges


# ── Private Badge Checks ──────────────────────────────────────────────────────

def _check_missing_deps(
        mid: str, info: ModInfo,
        all_mods: dict[str, ModInfo],
        active_ids: set[str],
        ignored_deps: set[str],
        ignored_errors: set[str],
        badges: list,
) -> None:
    """Append missing-dependency badges for *mid*."""
    dep_alts = getattr(info, 'dep_alternatives', {})
    for dep in getattr(info, 'dependencies', []):
        if dep in active_ids:
            continue
        if any(alt in active_ids
               for alt in dep_alts.get(dep, [])):
            continue
        if f"{mid}:{dep}" in ignored_deps:
            continue
        on_disk  = dep in all_mods
        dep_name = all_mods[dep].name if on_disk else dep
        if on_disk:
            msg = (f"Needs '{dep_name}' "
                   f"(declared in About.xml, not active)")
            key = make_error_key(mid, 'dep', msg)
            if key not in ignored_errors:
                badges.append(
                    ('⚠', COLOR_DEPENDENCY, 'dep', msg))
        else:
            msg = (f"Needs '{dep_name}' "
                   f"(declared in About.xml, "
                   f"NOT INSTALLED)")
            key = make_error_key(mid, 'error', msg)
            if key not in ignored_errors:
                badges.append(
                    ('❌', COLOR_ERROR, 'error', msg))


def _check_incompatible(
        mid: str, info: ModInfo,
        all_mods: dict[str, ModInfo],
        active_ids: set[str],
        ignored_errors: set[str],
        badges: list,
) -> None:
    """Append incompatibility badges for *mid*."""
    for incompat in getattr(
            info, 'incompatible_with', []):
        incompat_l = incompat.lower()
        if incompat_l in active_ids:
            incompat_name = (
                all_mods[incompat_l].name
                if incompat_l in all_mods
                else incompat_l)
            msg = (f"Incompatible with "
                   f"'{incompat_name}' "
                   f"(declared in About.xml)")
            key = make_error_key(mid, 'error', msg)
            if key not in ignored_errors:
                badges.append(
                    ('🚫', COLOR_ERROR, 'error', msg))


def _check_version(
        mid: str, info: ModInfo,
        game_version: str,
        ignored_errors: set[str],
        badges: list,
) -> None:
    """Append version-mismatch badge for *mid* if needed.

    Severity matches dep_resolver: 'warning' when the mod
    supports the same major version, 'error' otherwise.
    """
    if not check_version(info, game_version):
        parts = game_version.split('.')[:2]
        gv = ('.'.join(parts)
              if len(parts) >= 2 else game_version)
        major = gv.split('.')[0] + '.'
        partial = any(
            v.startswith(major)
            for v in info.supported_versions)
        sev  = 'warning' if partial else 'error'
        icon = '🔶' if partial else '❌'
        msg = (f"Version: "
               f"{', '.join(info.supported_versions)}")
        key = make_error_key(mid, sev, msg)
        if key not in ignored_errors:
            badges.append(
                (icon, COLOR_VERSION, sev, msg))


def _check_order(
        mid: str, info: ModInfo,
        all_mods: dict[str, ModInfo],
        active_order: list[str] | None,
        _pos_cache: dict | None,
        ignored_errors: set[str],
        badges: list,
) -> None:
    """Append load-order badges for *mid* if needed."""
    if not active_order:
        return
    _pos = _pos_cache or {
        m: i for i, m in enumerate(active_order)
    }
    order_issues = check_load_order(
        mid, info, active_order, all_mods, _pos)
    for badge in (order_issues or []):
        key = make_error_key(mid, badge[2], badge[3])
        if key not in ignored_errors:
            badges.append(badge)


def _check_juml_notices(
        mid: str, info: ModInfo,
        ignored_errors: set[str],
        badges: list,
) -> None:
    """Append JuMLi community-notice badges for *mid*."""
    try:
        from app.core.conflict_db import ConflictDB  # pylint: disable=import-outside-toplevel
        db      = ConflictDB.instance()
        notices = db.get_notices(
            mid, info.workshop_id or '')
        for notice in notices:
            color, sev = _NOTICE_MAP.get(
                notice.notice_type,
                (COLOR_INFO, 'info'))
            icon = {
                'unstable':    '⚠',
                'performance': '🐢',
                'alternative': '💡',
                'info':        'ℹ',
            }.get(notice.notice_type, 'ℹ')
            msg = notice.message
            key = make_error_key(mid, sev, msg)
            if key not in ignored_errors:
                badges.append(
                    (icon, color, sev, msg))
    except Exception:  # pylint: disable=broad-exception-caught
        # ConflictDB may be unavailable or corrupt
        pass


# ── Public Utilities ──────────────────────────────────────────────────────────

def check_load_order(
        mid: str, info: ModInfo,
        order: list[str],
        all_mods: dict[str, ModInfo],
        _pos_cache: dict | None = None,
) -> list[tuple[str, str, str, str]]:
    """Return load-order violation badges for *mid*."""
    badges = []
    pos = (_pos_cache if _pos_cache is not None
           else {m: i for i, m in enumerate(order)})

    if mid not in pos:
        return badges

    my_idx     = pos[mid]
    active_set = set(pos.keys())

    for dep in getattr(info, 'load_after', []):
        dep_l = dep.lower()
        if dep_l in active_set and pos[dep_l] > my_idx:
            dep_name = (all_mods[dep_l].name
                        if dep_l in all_mods
                        else dep_l)
            badges.append((
                '🔃', COLOR_ORDER, 'order',
                f"Should load after '{dep_name}'",
            ))

    for dep in getattr(info, 'load_before', []):
        dep_l = dep.lower()
        if dep_l in active_set and pos[dep_l] < my_idx:
            dep_name = (all_mods[dep_l].name
                        if dep_l in all_mods
                        else dep_l)
            badges.append((
                '🔃', COLOR_ORDER, 'order',
                f"Should load before '{dep_name}'",
            ))

    return badges


def check_version(
        info: ModInfo,
        game_version: str,
) -> bool:
    """Return True if *info* supports *game_version*."""
    if not info.supported_versions or not game_version:
        return True
    parts = game_version.split('.')[:2]
    gv = ('.'.join(parts)
          if len(parts) >= 2 else game_version)
    return gv in info.supported_versions


def count_issues(
        mod_ids: list[str],
        all_mods: dict[str, ModInfo],
        game_version: str,
        ignored_deps: set[str] | None = None,
        ignored_errors: set[str] | None = None,
) -> dict[str, int]:
    """Return a severity -> count mapping across all mods."""
    active         = set(mod_ids)
    counts         = {k: 0 for k in SEVERITY_CONFIG}
    _pos           = {
        m: i for i, m in enumerate(mod_ids)
    }
    ignored_deps   = ignored_deps   or set()
    ignored_errors = ignored_errors or set()

    for mid in mod_ids:
        for badge in get_badges(
                mid, all_mods, active, game_version,
                mod_ids, _pos,
                ignored_deps, ignored_errors):
            sev = badge[2]
            if sev in counts:
                counts[sev] += 1

    return counts


def get_issue_mod_ids(
        mod_ids: list[str],
        all_mods: dict[str, ModInfo],
        game_version: str,
        ignored_deps: set[str] | None = None,
        active_cats: set[str] | None = None,
        ignored_errors: set[str] | None = None,
) -> set[str]:
    """Return mod IDs that have at least one matching badge."""
    result         = set()
    active         = set(mod_ids)
    ignored_deps   = ignored_deps   or set()
    ignored_errors = ignored_errors or set()

    for mid in mod_ids:
        badges = get_badges(
            mid, all_mods, active, game_version,
            mod_ids,
            ignored_deps=ignored_deps,
            ignored_errors=ignored_errors)
        if active_cats is None:
            if badges:
                result.add(mid)
        else:
            if any(b[2] in active_cats
                   for b in badges):
                result.add(mid)
    return result


def format_issue_color(counts: dict[str, int]) -> str:
    """Return the highest-severity color for counts dict."""
    if counts.get('error', 0):
        return COLOR_ERROR
    if counts.get('dep', 0) or counts.get('warning', 0):
        return COLOR_DEPENDENCY
    if (counts.get('order', 0)
            or counts.get('performance', 0)):
        return COLOR_ORDER
    if counts.get('info', 0):
        return COLOR_INFO
    return '#4CAF50'
