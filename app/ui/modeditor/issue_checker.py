"""Issue analysis: missing deps, version mismatch, load order violations."""

from app.core.rimworld import RimWorldDetector, ModInfo
from app.core.dep_resolver import analyze_modlist, get_downloadable_deps, get_activatable_deps


def get_badges(mid: str, all_mods: dict[str, ModInfo], active_ids: set[str],
               game_version: str, active_order: list[str] = None
               ) -> list[tuple[str, str, str, str]]:
    """
    Return (icon, color, severity, message) list for one mod.
    active_order: ordered list of active mod IDs for load order checking.
    """
    badges = []
    info = all_mods.get(mid)

    if not info:
        badges.append(('❌', '#ff6b6b', 'error', 'Not found on disk'))
        return badges

    # Missing dependencies
    for dep in info.dependencies:
        if dep not in active_ids:
            on_disk = dep in all_mods
            dep_name = all_mods[dep].name if dep in all_mods else dep
            if on_disk:
                badges.append(('⚠', '#ffb74d', 'warning', f"Needs '{dep_name}' (not active)"))
            else:
                badges.append(('❌', '#ff6b6b', 'error', f"Needs '{dep_name}' (NOT INSTALLED)"))

    # Version mismatch
    if not check_version(info, game_version):
        badges.append(('🔶', '#ffd54f', 'warning',
                       f"Version: {', '.join(info.supported_versions)}"))

    # Load order violations
    if active_order:
        order_issues = check_load_order(mid, info, active_order, all_mods)
        badges.extend(order_issues)

    return badges


def check_load_order(mid: str, info: ModInfo, order: list[str],
                     all_mods: dict[str, ModInfo]) -> list[tuple[str, str, str, str]]:
    """Check if mod is in correct position relative to loadAfter/loadBefore rules."""
    badges = []
    try:
        my_idx = order.index(mid)
    except ValueError:
        return badges

    active_set = set(order)

    # loadAfter: these mods should appear BEFORE us
    for dep in info.load_after:
        dep_l = dep.lower()
        if dep_l in active_set:
            try:
                dep_idx = order.index(dep_l)
                if dep_idx > my_idx:
                    dep_name = all_mods[dep_l].name if dep_l in all_mods else dep_l
                    badges.append(('🔃', '#ce93d8', 'warning',
                                   f"Should load after '{dep_name}'"))
            except ValueError:
                pass

    # loadBefore: these mods should appear AFTER us
    for dep in info.load_before:
        dep_l = dep.lower()
        if dep_l in active_set:
            try:
                dep_idx = order.index(dep_l)
                if dep_idx < my_idx:
                    dep_name = all_mods[dep_l].name if dep_l in all_mods else dep_l
                    badges.append(('🔃', '#ce93d8', 'warning',
                                   f"Should load before '{dep_name}'"))
            except ValueError:
                pass

    # Dependencies: should load after all deps
    for dep in info.dependencies:
        dep_l = dep.lower()
        if dep_l in active_set:
            try:
                dep_idx = order.index(dep_l)
                if dep_idx > my_idx:
                    dep_name = all_mods[dep_l].name if dep_l in all_mods else dep_l
                    badges.append(('🔃', '#ce93d8', 'warning',
                                   f"Dependency '{dep_name}' should be loaded first"))
            except ValueError:
                pass

    return badges


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
    for mid in mod_ids:
        for badge in get_badges(mid, all_mods, active, game_version, mod_ids):
            if badge[0] == '🔃':
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
        return '#ff6b6b'
    if warnings:
        return '#ffb74d'
    if order:
        return '#ce93d8'
    return '#4CAF50'