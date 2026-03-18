"""
Topological sort for RimWorld mod load order.
Tiered approach:
  Tier 0:  Mods that load BEFORE Core (auto-detected via loadBefore)
  Tier 1a: Core
  Tier 1b: Mods that load after Core but before DLCs (auto-detected)
  Tier 1c: DLCs (fixed canonical order)
  Tier 2:  All regular mods (topologically sorted)
  Tier 3:  Mods that should load last
"""

from collections import defaultdict, deque
from app.core.rimworld import RimWorldDetector, ModInfo

# Seed set — auto-detection will catch anything with loadBefore: Core,
# but seeding known patchers avoids a first-open edge case where the mod
# hasn't been scanned yet.
KNOWN_TIER_ZERO = {
    'zetrith.prepatcher',
    'brrainz.harmony',
}

CORE = 'ludeon.rimworld'

DLCS = [
    'ludeon.rimworld.royalty',
    'ludeon.rimworld.ideology',
    'ludeon.rimworld.biotech',
    'ludeon.rimworld.anomaly',
    'ludeon.rimworld.odyssey',
]

DLCS_SET          = set(DLCS)
CORE_AND_DLCS_SET = {CORE} | DLCS_SET

KNOWN_TIER_THREE = {
    'krkr.rocketman',
    'brrainz.autopatcher',
}


def auto_sort_mods(mod_ids: list[str], rw: RimWorldDetector) -> list[str]:
    installed = rw.get_installed_mods()
    id_set    = set(mod_ids)

    # ── Tier 0: anything with loadBefore Core ────────────────────────────
    tier_zero_ids = set(KNOWN_TIER_ZERO)
    for mid in mod_ids:
        info = installed.get(mid)
        if info and any(d.lower() == CORE for d in info.load_before):
            tier_zero_ids.add(mid)

    tier_zero_ids = _expand_deps_into_tier(
        tier_zero_ids, installed, id_set, CORE_AND_DLCS_SET)

    # ── Tier 1b: after Core AND before any DLC ───────────────────────────
    tier_1b_ids: set[str] = set()
    for mid in mod_ids:
        if mid in tier_zero_ids or mid in CORE_AND_DLCS_SET:
            continue
        info = installed.get(mid)
        if not info:
            continue
        if (CORE in {d.lower() for d in info.load_after} and
                any(d.lower() in DLCS_SET for d in info.load_before)):
            tier_1b_ids.add(mid)

    tier_1b_ids = _expand_deps_into_tier(
        tier_1b_ids, installed, id_set,
        CORE_AND_DLCS_SET | tier_zero_ids)

    # ── Bucket every mod ─────────────────────────────────────────────────
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

    # ── Sort each tier ────────────────────────────────────────────────────
    s0  = _topo_sort_tier(t0,  installed, id_set)
    s1a = t1a                                           # just Core
    s1b = _topo_sort_tier(t1b, installed, id_set)
    s1c = [d for d in DLCS if d in set(t1c)]           # canonical DLC order
    s2  = _topo_sort_tier(t2,  installed, id_set)
    s3  = _topo_sort_tier(t3,  installed, id_set)

    result = s0 + s1a + s1b + s1c + s2 + s3

    violations = _count_violations(result, installed)

    return result


def _expand_deps_into_tier(tier_ids: set[str], installed: dict[str, ModInfo],
                            active_set: set[str],
                            exclude: set[str]) -> set[str]:
    """Pull direct dependencies of tier members into the same tier."""
    expanded  = set(tier_ids)
    queue     = list(tier_ids)
    processed: set[str] = set()

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

    # Build directed graph: edge A→B means B must come after A
    graph: dict[str, set[str]] = defaultdict(set)
    for mid in tier_mods:
        info = installed.get(mid)
        if not info:
            continue

        # Combine loadAfter + dependencies (both say "I need X before me")
        must_after: set[str] = set()
        for dep in (*info.load_after, *info.dependencies):
            dep_l = dep.lower()
            if dep_l in tier_set:
                must_after.add(dep_l)
        for dep_l in must_after:
            graph[dep_l].add(mid)          # dep_l → mid

        # loadBefore: I must come before X
        for dep in info.load_before:
            dep_l = dep.lower()
            if dep_l in tier_set:
                graph[mid].add(dep_l)      # mid → dep_l

    # Kahn's algorithm with alphabetical tie-breaking
    in_degree = {mid: 0 for mid in tier_mods}
    for neighbors in graph.values():
        for nb in neighbors:
            if nb in in_degree:
                in_degree[nb] += 1

    ready: deque[str] = deque(
        sorted([m for m in tier_mods if in_degree[m] == 0],
               key=lambda x: _mod_name(x, installed))
    )

    result: list[str] = []
    while ready:
        node = ready.popleft()
        result.append(node)
        for nb in sorted(graph.get(node, set()),
                         key=lambda x: _mod_name(x, installed)):
            if nb in in_degree:
                in_degree[nb] -= 1
                if in_degree[nb] == 0:
                    _insort_deque(ready, nb, installed)

    # Remaining = circular deps — append alphabetically
    placed = set(result)
    remaining = sorted([m for m in tier_mods if m not in placed],
                       key=lambda x: _mod_name(x, installed))
    result.extend(remaining)

    return result


def _insort_deque(queue: deque, item: str, installed: dict) -> None:
    """Insert item into queue maintaining alphabetical order by mod name."""
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
    pos        = {mid: i for i, mid in enumerate(order)}
    violations = 0
    seen: set[tuple] = set()

    for mid in order:
        info = installed.get(mid)
        if not info:
            continue
        my_pos = pos[mid]

        checks: set[tuple[str, str]] = set()
        for dep in (*info.load_after, *info.dependencies):
            checks.add(('after', dep.lower()))
        for dep in info.load_before:
            checks.add(('before', dep.lower()))

        for direction, dep_l in checks:
            key = (mid, dep_l, direction)
            if key in seen or dep_l not in pos:
                continue
            seen.add(key)
            if direction == 'after'  and pos[dep_l] > my_pos:
                violations += 1
            elif direction == 'before' and pos[dep_l] < my_pos:
                violations += 1

    return violations