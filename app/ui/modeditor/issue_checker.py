"""Issue analysis: missing deps, version mismatch, load order violations."""

from app.core.rimworld import RimWorldDetector, ModInfo
from app.core.dep_resolver import analyze_modlist, get_downloadable_deps, get_activatable_deps


# ── Color palette ─────────────────────────────────────────────────────────────
COLOR_ERROR      = '#ff4444'   # Red    — not on disk / hard missing dep
COLOR_DEPENDENCY = '#ff8800'   # Orange — dep not active (on disk), version mismatch
COLOR_WARNING    = '#ff8800'   # Orange — alias kept so imports don't break
COLOR_ORDER      = '#ffaa00'   # Yellow — load-order violation
COLOR_VERSION    = '#ff8800'   # Orange — version mismatch


def get_badges(mid: str, all_mods: dict[str, ModInfo], active_ids: set[str],
               game_version: str, active_order: list[str] = None,
               _pos_cache: dict | None = None
               ) -> list[tuple[str, str, str, str]]:
    """
    Return (icon, color, severity, message) list for one mod.

    Severity tags
    -------------
    'error'   — red:    not on disk, hard missing dep (not installed anywhere)
    'dep'     — orange: dependency exists on disk but is not active
    'warning' — orange: version mismatch
    'order'   — yellow: load-order violation
    """
    badges = []
    info = all_mods.get(mid)

    # ── Not on disk ───────────────────────────────────────────────────────────
    if not info:
        badges.append(('❌', COLOR_ERROR, 'error', 'Not found on disk'))
        return badges

    # ── Missing dependencies ──────────────────────────────────────────────────
    for dep in info.dependencies:
        if dep not in active_ids:
            on_disk  = dep in all_mods
            dep_name = all_mods[dep].name if on_disk else dep
            if on_disk:
                # Dep exists locally but isn't in the active list → orange, 'dep'
                badges.append((
                    '⚠', COLOR_DEPENDENCY, 'dep',
                    f"Needs '{dep_name}' (not active)",
                ))
            else:
                # Dep is completely absent from disk → red, 'error'
                badges.append((
                    '❌', COLOR_ERROR, 'error',
                    f"Needs '{dep_name}' (NOT INSTALLED)",
                ))

    # ── Version mismatch ──────────────────────────────────────────────────────
    if not check_version(info, game_version):
        badges.append((
            '🔶', COLOR_VERSION, 'warning',
            f"Version: {', '.join(info.supported_versions)}",
        ))

    # ── Load-order violations ─────────────────────────────────────────────────
    if active_order:
        _pos        = _pos_cache or {m: i for i, m in enumerate(active_order)}
        order_issues = check_load_order(mid, info, active_order, all_mods, _pos)
        badges.extend(order_issues or [])

    return badges


def check_load_order(mid: str, info: ModInfo, order: list[str],
                     all_mods: dict[str, ModInfo],
                     _pos_cache: dict | None = None) -> list[tuple[str, str, str, str]]:
    """
    Check loadAfter / loadBefore rules.
    Returns (icon, color, 'order', message) tuples — yellow.
    """
    badges  = []
    pos     = _pos_cache if _pos_cache is not None else {m: i for i, m in enumerate(order)}

    if mid not in pos:
        return badges

    my_idx     = pos[mid]
    active_set = set(pos.keys())

    # loadAfter: this mod must come AFTER dep → violation if dep is below us
    for dep in info.load_after:
        dep_l = dep.lower()
        if dep_l in active_set and pos[dep_l] > my_idx:
            dep_name = all_mods[dep_l].name if dep_l in all_mods else dep_l
            badges.append((
                '🔃', COLOR_ORDER, 'order',
                f"Should load after '{dep_name}'",
            ))

    # loadBefore: this mod must come BEFORE dep → violation if dep is above us
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
    """Return True when the mod declares support for the running game version."""
    if not info.supported_versions or not game_version:
        return True
    parts = game_version.split('.')[:2]
    gv    = '.'.join(parts) if len(parts) >= 2 else game_version
    return gv in info.supported_versions


def count_issues(mod_ids: list[str], all_mods: dict[str, ModInfo],
                 game_version: str) -> tuple[int, int, int]:
    """
    Return (errors, warnings, order_issues).

    - errors:       'error'   severity  (red)
    - warnings:     'dep' OR 'warning'  (orange)
    - order_issues: 'order'   severity  (yellow)
    """
    active      = set(mod_ids)
    errors      = warnings = order_issues = 0
    _pos        = {m: i for i, m in enumerate(mod_ids)}

    for mid in mod_ids:
        for badge in get_badges(mid, all_mods, active, game_version, mod_ids, _pos):
            sev = badge[2]
            if sev == 'error':
                errors += 1
            elif sev in ('dep', 'warning'):   # both map to orange warnings bucket
                warnings += 1
            elif sev == 'order':
                order_issues += 1

    return errors, warnings, order_issues


def get_issue_mod_ids(mod_ids: list[str], all_mods: dict[str, ModInfo],
                      game_version: str) -> set[str]:
    """Return the set of mod IDs that have at least one badge."""
    result = set()
    active = set(mod_ids)
    for mid in mod_ids:
        if get_badges(mid, all_mods, active, game_version, mod_ids):
            result.add(mid)
    return result


def format_issue_text(errors: int, warnings: int, order: int,
                      filtering: bool) -> str:
    """Build the status-bar label text."""
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
    """
    Return the header-button color reflecting the worst active issue.

    Priority: red > orange > yellow > green
    """
    if errors:
        return COLOR_ERROR       # '#ff4444' red
    if warnings:
        return COLOR_DEPENDENCY  # '#ff8800' orange
    if order:
        return COLOR_ORDER       # '#ffaa00' yellow
    return '#4CAF50'             # green — all clear