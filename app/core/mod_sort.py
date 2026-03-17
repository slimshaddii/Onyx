"""
Topological sort for RimWorld mod load order.
Uses loadAfter/loadBefore metadata from About.xml.
Falls back to a known-good ordering for common mods.
"""

from collections import defaultdict, deque
from app.core.rimworld import RimWorldDetector, ModInfo

# Mods that should always be at the very top
FORCE_TOP = [
    'zetrith.prepatcher',
    'brrainz.harmony',
    'me.samboycoding.csl2',  # UnityExplorer
]

# Mods that should be right after Harmony/framework
EARLY_FRAMEWORK = [
    'ludeon.rimworld',
    'ludeon.rimworld.royalty',
    'ludeon.rimworld.ideology',
    'ludeon.rimworld.biotech',
    'ludeon.rimworld.anomaly',
    'unlimitedhugs.hugslib',
]


def auto_sort_mods(mod_ids: list[str], rw: RimWorldDetector) -> list[str]:
    """
    Sort mod_ids into a valid load order based on:
    1. Force-top mods (Harmony, Prepatcher)
    2. Core + DLCs
    3. Topological sort using loadAfter/loadBefore
    4. Alphabetical as tiebreaker
    """
    installed = rw.get_installed_mods()
    id_set = set(mod_ids)

    # Build dependency graph
    # edges[A] = set of B means "A must load before B"
    graph: dict[str, set[str]] = defaultdict(set)
    in_degree: dict[str, int] = {mid: 0 for mid in mod_ids}

    for mid in mod_ids:
        info = installed.get(mid)
        if not info:
            continue

        # loadAfter: this mod loads after those mods
        for dep in info.load_after:
            dep_l = dep.lower()
            if dep_l in id_set:
                graph[dep_l].add(mid)
                in_degree[mid] = in_degree.get(mid, 0) + 1

        # loadBefore: this mod loads before those mods
        for dep in info.load_before:
            dep_l = dep.lower()
            if dep_l in id_set:
                graph[mid].add(dep_l)
                in_degree[dep_l] = in_degree.get(dep_l, 0) + 1

        # Dependencies: must load after deps
        for dep in info.dependencies:
            dep_l = dep.lower()
            if dep_l in id_set:
                graph[dep_l].add(mid)
                in_degree[mid] = in_degree.get(mid, 0) + 1

    # Kahn's algorithm (topological sort)
    queue = deque()
    for mid in mod_ids:
        if in_degree.get(mid, 0) == 0:
            queue.append(mid)

    # Sort queue entries alphabetically for stable output
    queue = deque(sorted(queue, key=lambda x: _sort_key(x, installed)))

    sorted_list = []
    while queue:
        node = queue.popleft()
        sorted_list.append(node)
        for neighbor in sorted(graph[node], key=lambda x: _sort_key(x, installed)):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Add any remaining (cyclic deps — just append)
    remaining = [m for m in mod_ids if m not in set(sorted_list)]
    sorted_list.extend(remaining)

    # Now enforce force-top ordering
    result = _enforce_top_order(sorted_list)
    return result


def _sort_key(mid: str, installed: dict) -> tuple:
    """Sorting key: force-top first, then early framework, then alphabetical."""
    if mid in FORCE_TOP:
        return (0, FORCE_TOP.index(mid), '')
    if mid in EARLY_FRAMEWORK:
        return (1, EARLY_FRAMEWORK.index(mid), '')
    name = installed[mid].name.lower() if mid in installed else mid
    return (2, 0, name)


def _enforce_top_order(mods: list[str]) -> list[str]:
    """Move force-top and early-framework mods to the front."""
    top = []
    early = []
    rest = []

    for mid in mods:
        if mid in FORCE_TOP:
            top.append(mid)
        elif mid in EARLY_FRAMEWORK:
            early.append(mid)
        else:
            rest.append(mid)

    # Sort top by known order
    top.sort(key=lambda x: FORCE_TOP.index(x) if x in FORCE_TOP else 999)
    early.sort(key=lambda x: EARLY_FRAMEWORK.index(x) if x in EARLY_FRAMEWORK else 999)

    return top + early + rest