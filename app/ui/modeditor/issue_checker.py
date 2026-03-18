"""Issue analysis: missing deps, version mismatch, load order violations,
incompatible mods, and JuMLi community conflict/performance notices."""

from app.core.rimworld import RimWorldDetector, ModInfo
from app.core.dep_resolver import analyze_modlist, get_downloadable_deps, get_activatable_deps


# ── Color palette ─────────────────────────────────────────────────────────────
COLOR_ERROR       = '#ff4444'   # Red    — not on disk, hard missing dep, incompatible
COLOR_DEPENDENCY  = '#ff8800'   # Orange — dep not active, version mismatch, alternative
COLOR_WARNING     = '#ff8800'   # Orange — alias
COLOR_ORDER       = '#ffaa00'   # Yellow — load-order violation, performance notice
COLOR_VERSION     = '#ff8800'   # Orange — version mismatch
COLOR_INFO        = '#888888'   # Grey   — info/settings advice


# ── Notice type → (color, severity_tag) ──────────────────────────────────────
_NOTICE_MAP = {
    'incompatible': (COLOR_ERROR,      'error'),
    'unstable':     (COLOR_DEPENDENCY, 'warning'),
    'alternative':  (COLOR_DEPENDENCY, 'warning'),
    'performance':  (COLOR_ORDER,      'order'),
    'info':         (COLOR_INFO,       'info'),
}


def get_badges(mid: str, all_mods: dict[str, ModInfo], active_ids: set[str],
               game_version: str, active_order: list[str] = None,
               _pos_cache: dict | None = None,
               ignored_deps: set[str] | None = None,
               ) -> list[tuple[str, str, str, str]]:
    """
    Return (icon, color, severity, message) list for one mod.

    Severity tags
    -------------
    'error'   — red:    not on disk, hard missing dep, incompatibleWith
    'dep'     — orange: dep on disk but not active
    'warning' — orange: version mismatch, unstable, alternative
    'order'   — yellow: load-order violation, performance notice
    'info'    — grey:   settings advice
    """
    badges       = []
    info         = all_mods.get(mid)
    ignored_deps = ignored_deps or set()

    # ── Not on disk ───────────────────────────────────────────────────────────
    if not info:
        badges.append(('❌', COLOR_ERROR, 'error', 'Not found on disk'))
        return badges

    # ── Missing dependencies ──────────────────────────────────────────────────
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

    # ── Task 8.2 — incompatibleWith from About.xml ───────────────────────────
    for incompat in info.incompatible_with:
        incompat_l = incompat.lower()
        if incompat_l in active_ids:
            incompat_name = (all_mods[incompat_l].name
                             if incompat_l in all_mods else incompat_l)
            badges.append((
                '🚫', COLOR_ERROR, 'error',
                f"Incompatible with '{incompat_name}' (declared in About.xml)",
            ))

    # ── Version mismatch ──────────────────────────────────────────────────────
    if not check_version(info, game_version):
        badges.append((
            '🔶', COLOR_VERSION, 'warning',
            f"Version: {', '.join(info.supported_versions)}",
        ))

    # ── Load-order violations ─────────────────────────────────────────────────
    if active_order:
        _pos         = _pos_cache or {m: i for i, m in enumerate(active_order)}
        order_issues = check_load_order(mid, info, active_order, all_mods, _pos)
        badges.extend(order_issues or [])

    # ── Task 8.6 — JuMLi community notices ───────────────────────────────────
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
        pass   # DB load failure must never break badge rendering

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
                 ) -> tuple[int, int, int]:
    """Return (errors, warnings, order_issues)."""
    active       = set(mod_ids)
    errors       = warnings = order_issues = 0
    _pos         = {m: i for i, m in enumerate(mod_ids)}
    ignored_deps = ignored_deps or set()

    for mid in mod_ids:
        for badge in get_badges(mid, all_mods, active, game_version,
                                mod_ids, _pos, ignored_deps):
            sev = badge[2]
            if sev == 'error':
                errors += 1
            elif sev in ('dep', 'warning'):
                warnings += 1
            elif sev in ('order', 'info'):
                order_issues += 1

    return errors, warnings, order_issues


def get_issue_mod_ids(mod_ids: list[str], all_mods: dict[str, ModInfo],
                      game_version: str,
                      ignored_deps: set[str] | None = None,
                      ) -> set[str]:
    result       = set()
    active       = set(mod_ids)
    ignored_deps = ignored_deps or set()
    for mid in mod_ids:
        if get_badges(mid, all_mods, active, game_version,
                      mod_ids, ignored_deps=ignored_deps):
            result.add(mid)
    return result


def format_issue_text(errors: int, warnings: int, order: int,
                      filtering: bool) -> str:
    parts = []
    if errors:
        parts.append(f"❌ {errors}")
    if warnings:
        parts.append(f"⚠ {warnings}")
    if order:
        parts.append(f"🔃 {order}")
    if not parts:
        parts.append("✔ OK")
    text = "  ".join(parts)
    if filtering:
        text += "  [filtered]"
    return text


def format_issue_color(errors: int, warnings: int, order: int) -> str:
    if errors:
        return COLOR_ERROR
    if warnings:
        return COLOR_DEPENDENCY
    if order:
        return COLOR_ORDER
    return '#4CAF50'