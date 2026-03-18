"""Issue analysis: missing deps, version mismatch, load order violations,
incompatible mods, and JuMLi community conflict/performance notices."""

from app.core.rimworld import ModInfo

# ── Color palette ─────────────────────────────────────────────────────────────
COLOR_ERROR       = '#ff4444'
COLOR_DEPENDENCY  = '#ff8800'
COLOR_WARNING     = '#ff8800'
COLOR_ORDER       = '#ffaa00'
COLOR_VERSION     = '#ff8800'
COLOR_INFO        = '#888888'

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


def get_badges(mid: str, all_mods: dict[str, ModInfo], active_ids: set[str],
               game_version: str, active_order: list[str] = None,
               _pos_cache: dict | None = None,
               ignored_deps: set[str] | None = None,
               ) -> list[tuple[str, str, str, str]]:
    badges       = []
    info         = all_mods.get(mid)
    ignored_deps = ignored_deps or set()

    if not info:
        badges.append(('❌', COLOR_ERROR, 'error', 'Not found on disk'))
        return badges

    for dep in info.dependencies:
        if dep not in active_ids:
            dep_key = f"{mid}:{dep}"
            if dep_key in ignored_deps:
                continue
            on_disk  = dep in all_mods
            dep_name = all_mods[dep].name if on_disk else dep
            if on_disk:
                badges.append((
                    '⚠', COLOR_DEPENDENCY, 'dep',
                    f"Needs '{dep_name}' (declared in About.xml, not active)",
                ))
            else:
                badges.append((
                    '❌', COLOR_ERROR, 'error',
                    f"Needs '{dep_name}' (declared in About.xml, NOT INSTALLED)",
                ))

    for incompat in info.incompatible_with:
        incompat_l = incompat.lower()
        if incompat_l in active_ids:
            incompat_name = (all_mods[incompat_l].name
                             if incompat_l in all_mods else incompat_l)
            badges.append((
                '🚫', COLOR_ERROR, 'error',
                f"Incompatible with '{incompat_name}' (declared in About.xml)",
            ))

    if not check_version(info, game_version):
        badges.append((
            '🔶', COLOR_VERSION, 'warning',
            f"Version: {', '.join(info.supported_versions)}",
        ))

    if active_order:
        _pos         = _pos_cache or {m: i for i, m in enumerate(active_order)}
        order_issues = check_load_order(mid, info, active_order, all_mods, _pos)
        badges.extend(order_issues or [])

    try:
        from app.core.conflict_db import ConflictDB
        db      = ConflictDB.instance()
        notices = db.get_notices(mid, info.workshop_id or '')
        for notice in notices:
            color, sev = _NOTICE_MAP.get(
                notice.notice_type, (COLOR_INFO, 'info'))
            icon = {
                'unstable':    '⚠',
                'performance': '🐢',
                'alternative': '💡',
                'info':        'ℹ',
            }.get(notice.notice_type, 'ℹ')
            badges.append((icon, color, sev, notice.message))
    except Exception:
        pass

    return badges


def check_load_order(mid: str, info: ModInfo, order: list[str],
                     all_mods: dict[str, ModInfo],
                     _pos_cache: dict | None = None,
                     ) -> list[tuple[str, str, str, str]]:
    badges     = []
    pos        = _pos_cache if _pos_cache is not None else {
        m: i for i, m in enumerate(order)}

    if mid not in pos:
        return badges

    my_idx     = pos[mid]
    active_set = set(pos.keys())

    for dep in info.load_after:
        dep_l = dep.lower()
        if dep_l in active_set and pos[dep_l] > my_idx:
            dep_name = all_mods[dep_l].name if dep_l in all_mods else dep_l
            badges.append((
                '🔃', COLOR_ORDER, 'order',
                f"Should load after '{dep_name}'",
            ))

    for dep in info.load_before:
        dep_l = dep.lower()
        if dep_l in active_set and pos[dep_l] < my_idx:
            dep_name = all_mods[dep_l].name if dep_l in all_mods else dep_l
            badges.append((
                '🔃', COLOR_ORDER, 'order',
                f"Should load before '{dep_name}'",
            ))

    return badges


def check_version(info: ModInfo, game_version: str) -> bool:
    if not info.supported_versions or not game_version:
        return True
    parts = game_version.split('.')[:2]
    gv    = '.'.join(parts) if len(parts) >= 2 else game_version
    return gv in info.supported_versions


def count_issues(mod_ids: list[str], all_mods: dict[str, ModInfo],
                 game_version: str,
                 ignored_deps: set[str] | None = None,
                 ) -> dict[str, int]:
    active       = set(mod_ids)
    counts       = {k: 0 for k in SEVERITY_CONFIG}
    _pos         = {m: i for i, m in enumerate(mod_ids)}
    ignored_deps = ignored_deps or set()

    for mid in mod_ids:
        for badge in get_badges(mid, all_mods, active, game_version,
                                mod_ids, _pos, ignored_deps):
            sev = badge[2]
            if sev in counts:
                counts[sev] += 1

    return counts


def get_issue_mod_ids(mod_ids: list[str], all_mods: dict[str, ModInfo],
                      game_version: str,
                      ignored_deps: set[str] | None = None,
                      active_cats: set[str] | None = None,
                      ) -> set[str]:
    result       = set()
    active       = set(mod_ids)
    ignored_deps = ignored_deps or set()

    for mid in mod_ids:
        badges = get_badges(mid, all_mods, active, game_version,
                            mod_ids, ignored_deps=ignored_deps)
        if active_cats is None:
            if badges:
                result.add(mid)
        else:
            if any(b[2] in active_cats for b in badges):
                result.add(mid)
    return result


def format_issue_color(counts: dict[str, int]) -> str:
    if counts.get('error', 0):
        return COLOR_ERROR
    if counts.get('dep', 0) or counts.get('warning', 0):
        return COLOR_DEPENDENCY
    if counts.get('order', 0) or counts.get('performance', 0):
        return COLOR_ORDER
    if counts.get('info', 0):
        return COLOR_INFO
    return '#4CAF50'