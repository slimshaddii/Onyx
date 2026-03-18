"""
Topological sort for RimWorld mod load order.
Tiered approach inspired by RimSort:
  Tier 0: Mods that load BEFORE Core (auto-detected via loadBefore)
  Tier 1a: Core
  Tier 1b: Mods that load after Core but before DLCs (auto-detected)
  Tier 1c: DLCs
  Tier 2: All regular mods (topologically sorted)
  Tier 3: Mods that should load last
"""

from collections import defaultdict, deque
from app.core.rimworld import RimWorldDetector, ModInfo

KNOWN_TIER_ZERO = {
    'zetrith.prepatcher',
    'brrainz.harmony',
    'me.samboycoding.csl2',
}

CORE = 'ludeon.rimworld'

DLCS = [
    'ludeon.rimworld.royalty',
    'ludeon.rimworld.ideology',
    'ludeon.rimworld.biotech',
    'ludeon.rimworld.anomaly',
    'ludeon.rimworld.odyssey',
]

DLCS_SET = set(DLCS)
CORE_AND_DLCS_SET = {CORE} | DLCS_SET

KNOWN_TIER_THREE = {
    'krkr.rocketman',
    'brrainz.autopatcher',
}


def auto_sort_mods(mod_ids: list[str], rw: RimWorldDetector) -> list[str]:
    installed = rw.get_installed_mods()
    id_set = set(mod_ids)

    # ═══════════════════════════════════════════════════════
    # STEP 1: Auto-detect tier 0 (loadBefore Core)
    # ═══════════════════════════════════════════════════════
    tier_zero_ids = set(KNOWN_TIER_ZERO)

    for mid in mod_ids:
        info = installed.get(mid)
        if not info:
            continue
        for dep in info.load_before:
            if dep.lower() == CORE:
                tier_zero_ids.add(mid)
                break

    # Expand: deps of tier 0 join tier 0
    tier_zero_ids = _expand_deps_into_tier(tier_zero_ids, installed, id_set, CORE_AND_DLCS_SET)

    # ═══════════════════════════════════════════════════════
    # STEP 2: Auto-detect tier 1b (after Core, before DLCs)
    # ═══════════════════════════════════════════════════════
    tier_1b_ids = set()

    for mid in mod_ids:
        if mid in tier_zero_ids or mid in CORE_AND_DLCS_SET:
            continue
        info = installed.get(mid)
        if not info:
            continue

        loads_after_core = CORE in {d.lower() for d in info.load_after}
        loads_before_dlc = any(d.lower() in DLCS_SET for d in info.load_before)

        if loads_after_core and loads_before_dlc:
            tier_1b_ids.add(mid)

    # Expand deps of tier 1b into tier 1b
    tier_1b_ids = _expand_deps_into_tier(
        tier_1b_ids, installed, id_set, 
        CORE_AND_DLCS_SET | tier_zero_ids
    )

    # ═══════════════════════════════════════════════════════
    # STEP 3: Separate all mods into tiers
    # ═══════════════════════════════════════════════════════
    t0, t1a, t1b, t1c, t2, t3 = [], [], [], [], [], []

    for mid in mod_ids:
        if mid in tier_zero_ids and mid not in CORE_AND_DLCS_SET:
            t0.append(mid)
        elif mid == CORE:
            t1a.append(mid)
        elif mid in tier_1b_ids:
            t1b.append(mid)
        elif mid in DLCS_SET:
            t1c.append(mid)
        elif mid in KNOWN_TIER_THREE:
            t3.append(mid)
        else:
            t2.append(mid)

    # ═══════════════════════════════════════════════════════
    # STEP 4: Sort each tier
    # ═══════════════════════════════════════════════════════
    s0 = _topo_sort_tier(t0, installed, id_set)
    s1a = t1a  # Just Core
    s1b = _topo_sort_tier(t1b, installed, id_set)
    s1c = [d for d in DLCS if d in set(t1c)]  # Fixed DLC order
    s2 = _topo_sort_tier(t2, installed, id_set)
    s3 = _topo_sort_tier(t3, installed, id_set)

    # ═══════════════════════════════════════════════════════
    # STEP 5: Combine
    # ═══════════════════════════════════════════════════════
    result = s0 + s1a + s1b + s1c + s2 + s3

    violations = _count_violations(result, installed)
    print(f"[Sort] Sorted {len(result)} mods: "
          f"t0={len(s0)}, core={len(s1a)}, t1b={len(s1b)}, "
          f"dlcs={len(s1c)}, t2={len(s2)}, t3={len(s3)}")
    if violations:
        print(f"[Sort] {violations} violations remain (circular deps)")

    return result


def _expand_deps_into_tier(tier_ids: set[str], installed: dict[str, ModInfo],
                           active_set: set[str], exclude: set[str]) -> set[str]:
    expanded = set(tier_ids)
    queue = list(tier_ids)
    processed = set()

    while queue:
        mid = queue.pop()
        if mid in processed:
            continue
        processed.add(mid)

        info = installed.get(mid)
        if not info:
            continue

        for dep in info.dependencies:
            dep_l = dep.lower()
            if dep_l in active_set and dep_l not in exclude and dep_l not in expanded:
                expanded.add(dep_l)
                queue.append(dep_l)

    return expanded


def _topo_sort_tier(tier_mods: list[str], installed: dict[str, ModInfo],
                    all_active: set[str]) -> list[str]:
    if len(tier_mods) <= 1:
        return list(tier_mods)

    tier_set = set(tier_mods)
    graph: dict[str, set[str]] = defaultdict(set)

    for mid in tier_mods:
        info = installed.get(mid)
        if not info:
            continue

        must_load_after = set()
        for dep in info.load_after:
            dep_l = dep.lower()
            if dep_l in tier_set:
                must_load_after.add(dep_l)
        for dep in info.dependencies:
            dep_l = dep.lower()
            if dep_l in tier_set:
                must_load_after.add(dep_l)

        for dep_l in must_load_after:
            graph[dep_l].add(mid)

        for dep in info.load_before:
            dep_l = dep.lower()
            if dep_l in tier_set:
                graph[mid].add(dep_l)

    in_degree = {mid: 0 for mid in tier_mods}
    for node, neighbors in graph.items():
        for neighbor in neighbors:
            if neighbor in in_degree:
                in_degree[neighbor] += 1

    queue = sorted(
        [mid for mid in tier_mods if in_degree.get(mid, 0) == 0],
        key=lambda x: _mod_name(x, installed)
    )
    queue = deque(queue)

    result = []
    while queue:
        node = queue.popleft()
        result.append(node)

        for neighbor in sorted(graph.get(node, set()), key=lambda x: _mod_name(x, installed)):
            if neighbor in in_degree:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    _insort(queue, neighbor, installed)

    result_set = set(result)
    remaining = [m for m in tier_mods if m not in result_set]
    if remaining:
        remaining.sort(key=lambda x: _mod_name(x, installed))
        result.extend(remaining)

    return result


def _insort(queue: deque, item: str, installed: dict):
    name = _mod_name(item, installed)
    for i, existing in enumerate(queue):
        if _mod_name(existing, installed) > name:
            queue.insert(i, item)
            return
    queue.append(item)


def _mod_name(mid: str, installed: dict) -> str:
    info = installed.get(mid)
    return info.name.lower() if info else mid


def _count_violations(order: list[str], installed: dict) -> int:
    pos = {mid: i for i, mid in enumerate(order)}
    violations = 0
    seen = set()

    for mid in order:
        info = installed.get(mid)
        if not info:
            continue
        my_pos = pos[mid]

        check = set()
        for dep in info.load_after:
            check.add(('after', dep.lower()))
        for dep in info.dependencies:
            check.add(('after', dep.lower()))
        for dep in info.load_before:
            check.add(('before', dep.lower()))

        for direction, dep_l in check:
            key = (mid, dep_l, direction)
            if key in seen:
                continue
            seen.add(key)

            if dep_l not in pos:
                continue
            if direction == 'after' and pos[dep_l] > my_pos:
                violations += 1
            elif direction == 'before' and pos[dep_l] < my_pos:
                violations += 1

    return violations