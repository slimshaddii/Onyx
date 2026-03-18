"""Issue analysis: missing deps, version mismatch, load order violations."""

from app.core.rimworld import RimWorldDetector, ModInfo
from app.core.dep_resolver import analyze_modlist, get_downloadable_deps, get_activatable_deps


# Color palette for badges
COLOR_ERROR = '#ff4444'      # Red for critical errors
COLOR_WARNING = '#ffaa00'    # Yellow for warnings
COLOR_DEPENDENCY = '#ff8800' # Orange for dependency issues
COLOR_ORDER = '#74d4cc'      # Teal for load order issues
COLOR_VERSION = '#ffaa00'    # Yellow for version mismatch


def get_badges(mid: str, all_mods: dict[str, ModInfo], active_ids: set[str],
               game_version: str, active_order: list[str] = None,
               _pos_cache: dict | None = None
               ) -> list[tuple[str, str, str, str]]:
    """
    Return (icon, color, severity, message) list for one mod.
    active_order: ordered list of active mod IDs for load order checking.
    """
    badges = []
    info = all_mods.get(mid)

    if not info:
        badges.append(('❌', COLOR_ERROR, 'error', 'Not found on disk'))
        return badges

    # Missing dependencies
    for dep in info.dependencies:
        if dep not in active_ids:
            on_disk = dep in all_mods
            dep_name = all_mods[dep].name if dep in all_mods else dep
            if on_disk:
                badges.append(('⚠', COLOR_DEPENDENCY, 'warning', f"Needs '{dep_name}' (not active)"))
            else:
                badges.append(('❌', COLOR_ERROR, 'error', f"Needs '{dep_name}' (NOT INSTALLED)"))

    # Version mismatch
    if not check_version(info, game_version):
        badges.append(('🔶', COLOR_VERSION, 'warning',
                       f"Version: {', '.join(info.supported_versions)}"))

    # Load order violations
    if active_order:
        _pos = {m: i for i, m in enumerate(active_order)}
        order_issues = check_load_order(mid, info, active_order, all_mods, _pos_cache or _pos)
        badges.extend(order_issues or [])

    return badges


def check_load_order(mid: str, info: ModInfo, order: list[str],
                     all_mods: dict[str, ModInfo],
                     _pos_cache: dict | None = None) -> list[tuple[str, str, str, str]]:
    """Check if mod is in correct position relative to loadAfter/loadBefore rules."""
    badges = []
    pos = _pos_cache if _pos_cache is not None else {m: i for i, m in enumerate(order)}

    if mid not in pos:
        return badges

    my_idx = pos[mid]
    active_set = set(pos.keys())

    # loadAfter: dep should appear BEFORE us (dep_idx < my_idx is correct)
    # Violation = dep appears AFTER us (dep_idx > my_idx)
    for dep in info.load_after:
        dep_l = dep.lower()
        if dep_l in active_set:
            dep_idx = pos[dep_l]
            if dep_idx > my_idx:
                dep_name = all_mods[dep_l].name if dep_l in all_mods else dep_l
                badges.append(('🔃', COLOR_ORDER, 'order',
                               f"Should load after '{dep_name}'"))

    # loadBefore: dep should appear AFTER us (dep_idx > my_idx is correct)
    # Violation = dep appears BEFORE us (dep_idx < my_idx)
    for dep in info.load_before:
        dep_l = dep.lower()
        if dep_l in active_set:
            dep_idx = pos[dep_l]
            if dep_idx < my_idx:
                dep_name = all_mods[dep_l].name if dep_l in all_mods else dep_l
                badges.append(('🔃', COLOR_ORDER, 'order',
                               f"Should load before '{dep_name}'"))

    return badges  # ← THIS WAS MISSING


def check_version(info: ModInfo, game_version: str) -> bool:
    if not info.supported_versions or not game_version:
        return True
    parts = game_version.split('.')[:2]
    gv = '.'.join(parts) if len(parts) >= 2 else game_version
    return gv in info.supported_versions


def count_issues(mod_ids: list[str], all_mods: dict[str, ModInfo],
                 game_version: str) -> tuple[int, int, int]:
    """Return (errors, warnings, order_issues)."""
    active = set(mod_ids)
    errors = warnings = order_issues = 0
    _pos = {m: i for i, m in enumerate(mod_ids)}
    for mid in mod_ids:
        for badge in get_badges(mid, all_mods, active, game_version, mod_ids, _pos):
            if badge[2] == 'order':
                order_issues += 1
            elif badge[2] == 'error':
                errors += 1
            elif badge[2] == 'warning':
                warnings += 1
    return errors, warnings, order_issues


def get_issue_mod_ids(mod_ids: list[str], all_mods: dict[str, ModInfo],
                      game_version: str) -> set[str]:
    result = set()
    active = set(mod_ids)
    for mid in mod_ids:
        if get_badges(mid, all_mods, active, game_version, mod_ids):
            result.add(mid)
    return result


def format_issue_text(errors: int, warnings: int, order: int, filtering: bool) -> str:
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
        return COLOR_WARNING
    if order:
        return COLOR_ORDER
    return '#4CAF50'