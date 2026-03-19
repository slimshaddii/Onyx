"""
Topological sort for RimWorld mod load order.

Tier detection is FULLY DYNAMIC — nothing is hardcoded.

  Tier 0  : Pre-patchers + Core + DLCs
             Detected by: mod.load_first == True  (loadBefore ludeon.rimworld)
             Core and DLCs are always tier 0 by package-id identity only.

  Tier 1  : Framework / library mods
             Detected by: a mod is a dependency of 2+ other active mods
             AND has no dependencies of its own in tier 2
             (i.e. it is a "root" that many things depend on).

  Tier 2  : All regular mods (default bucket)

  Tier 3  : Load-last mods
             Detected by: mod.load_last == True
             (set when a mod declares loadBefore on nothing but has
             many others declaring loadBefore on IT — future XML tag support)

Dependency priority (from community feedback):
  forced_dependencies  → always required, additive
  modDependenciesByVersion > modDependencies  (mutually exclusive per version)
"""

from toposort import toposort, CircularDependencyError

from app.core.rimworld import RimWorldDetector, ModInfo

# ── Only these are identity-based (they have no About.xml loadBefore rule) ───
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

# Minimum number of active mods that must depend on X for X to be tier 1
_FRAMEWORK_THRESHOLD = 2


# ═════════════════════════════════════════════════════════════════════════════
# Public entry point
# ═════════════════════════════════════════════════════════════════════════════

def auto_sort_mods(mod_ids: list[str], rw: RimWorldDetector) -> list[str]:
    """Return a sorted copy of *mod_ids* respecting RimWorld load order."""
    installed  = rw.get_installed_mods()
    active_set = set(mod_ids)

    # ── Build graphs ──────────────────────────────────────────────────────
    dep_graph  = _build_dep_graph(active_set, installed)
    rdep_graph = _build_rdep_graph(dep_graph, active_set)

    # ── Classify tiers ────────────────────────────────────────────────────
    tier_zero_ids  = _collect_tier_zero(active_set, installed, dep_graph)
    tier_three_ids = _collect_tier_three(active_set, installed,
                                         rdep_graph, tier_zero_ids)
    tier_one_ids   = _collect_tier_one(active_set, dep_graph, rdep_graph,
                                        tier_zero_ids, tier_three_ids)

    # ── Bucket ────────────────────────────────────────────────────────────
    t0, t1, t2, t3 = _bucket(mod_ids,
                               tier_zero_ids, tier_one_ids, tier_three_ids)

    # ── Sort each tier ────────────────────────────────────────────────────
    s0 = _reorder_tier_zero(_sort_tier_list(t0, dep_graph, installed))
    s1 = _sort_tier_list(t1, dep_graph, installed)
    s2 = _sort_tier_list(t2, dep_graph, installed)
    s3 = _sort_tier_list(t3, _trim_graph(dep_graph, set(t3)), installed)

    # ── Deduplicate (safety net) ──────────────────────────────────────────
    seen:   set[str]  = set()
    result: list[str] = []
    for mid in s0 + s1 + s2 + s3:
        if mid not in seen:
            seen.add(mid)
            result.append(mid)
    return result


# ═════════════════════════════════════════════════════════════════════════════
# Graph builders
# ═════════════════════════════════════════════════════════════════════════════

def _all_deps(info: ModInfo) -> list[str]:
    seen:   set[str]  = set()
    result: list[str] = []
    for pid in (*getattr(info, 'forced_dependencies', []),
                *getattr(info, 'dependencies', []),
                *getattr(info, 'load_after', [])):
        pl = pid.lower()
        if pl not in seen:
            seen.add(pl)
            result.append(pl)
    return result


def _build_dep_graph(
    active_set: set[str],
    installed:  dict[str, ModInfo],
) -> dict[str, set[str]]:
    """
    Forward graph: { mid: {must_load_before_mid} }

    Rules applied:
      • forced_deps + deps + loadAfter  → mid loads AFTER them
      • loadBefore X                    → X loads AFTER mid
                                          (add mid to X's dep set)
    """
    graph: dict[str, set[str]] = {mid: set() for mid in active_set}

    for mid in active_set:
        info = installed.get(mid)
        if not info:
            continue

        for dep in _all_deps(info):
            if dep in active_set and dep != mid:
                graph[mid].add(dep)

        for before in info.load_before:
            bl = before.lower()
            if bl in active_set and bl != mid:
                graph[bl].add(mid)   # bl must load after mid

    return graph


def _build_rdep_graph(
    dep_graph:  dict[str, set[str]],
    active_set: set[str],
) -> dict[str, set[str]]:
    """
    Reverse graph derived from dep_graph.
    { mid: {mods_that_load_after_mid} }
    """
    rgraph: dict[str, set[str]] = {mid: set() for mid in active_set}
    for mid, deps in dep_graph.items():
        for dep in deps:
            if dep in rgraph:
                rgraph[dep].add(mid)
    return rgraph


# ═════════════════════════════════════════════════════════════════════════════
# Tier classifiers — all dynamic
# ═════════════════════════════════════════════════════════════════════════════

def _collect_tier_zero(
    active_set: set[str],
    installed:  dict[str, ModInfo],
    dep_graph:  dict[str, set[str]],
) -> set[str]:
    """
    Tier 0 = Core + DLCs (by identity) + any mod whose About.xml sets
    load_first=True (loadBefore ludeon.rimworld) + their recursive deps.
    """
    seeds: set[str] = set()

    for mid in active_set:
        if mid in CORE_AND_DLCS_SET:
            seeds.add(mid)
            continue
        info = installed.get(mid)
        if info and info.load_first:
            seeds.add(mid)

    return _expand_forward(seeds, dep_graph, active_set)


def _collect_tier_three(
    active_set:    set[str],
    installed:     dict[str, ModInfo],
    rdep_graph:    dict[str, set[str]],
    tier_zero_ids: set[str],
) -> set[str]:
    """
    Tier 3 = mods whose About.xml sets load_last=True + their
    reverse-dependents (mods that must load before them pull them last too).
    Excludes anything already in tier 0.
    """
    seeds: set[str] = set()
    for mid in active_set:
        if mid in tier_zero_ids:
            continue
        info = installed.get(mid)
        if info and info.load_last:
            seeds.add(mid)

    expanded = _expand_reverse(seeds, rdep_graph, active_set)
    return expanded - tier_zero_ids


def _collect_tier_one(
    active_set:     set[str],
    dep_graph:      dict[str, set[str]],
    rdep_graph:     dict[str, set[str]],
    tier_zero_ids:  set[str],
    tier_three_ids: set[str],
) -> set[str]:
    """
    Tier 1 = mods that behave as frameworks/libraries, detected dynamically:

      A mod is tier 1 when ALL of:
        1. Not already in tier 0 or tier 3
        2. At least _FRAMEWORK_THRESHOLD other active mods depend on it
        3. It has no tier-2 dependencies of its own
           (i.e. all its own deps are already tier 0)

    Rule 3 prevents pulling in large dependency chains into tier 1 and
    keeps only true "root library" mods here.
    """
    exclude = tier_zero_ids | tier_three_ids
    tier_one: set[str] = set()

    for mid in active_set:
        if mid in exclude:
            continue

        # How many active mods load after this one?
        dependent_count = len(rdep_graph.get(mid, set()) - exclude)
        if dependent_count < _FRAMEWORK_THRESHOLD:
            continue

        # Does this mod have any non-tier-0 deps itself?
        own_deps = dep_graph.get(mid, set()) - tier_zero_ids
        if own_deps:
            continue

        tier_one.add(mid)

    # Pull in their deps (which must also be frameworks, or already tier 0)
    return _expand_forward(tier_one, dep_graph, active_set) - exclude


# ═════════════════════════════════════════════════════════════════════════════
# Graph helpers
# ═════════════════════════════════════════════════════════════════════════════

def _expand_forward(
    seeds:      set[str],
    dep_graph:  dict[str, set[str]],
    active_set: set[str],
) -> set[str]:
    """BFS: expand seeds by following forward dependency edges."""
    result:    set[str]  = set(seeds)
    queue:     list[str] = list(seeds)
    processed: set[str]  = set()

    while queue:
        mid = queue.pop()
        if mid in processed:
            continue
        processed.add(mid)
        for dep in dep_graph.get(mid, set()):
            if dep in active_set and dep not in result:
                result.add(dep)
                queue.append(dep)
    return result


def _expand_reverse(
    seeds:      set[str],
    rdep_graph: dict[str, set[str]],
    active_set: set[str],
) -> set[str]:
    """BFS: expand seeds by following reverse dependency edges."""
    result:    set[str]  = set(seeds)
    queue:     list[str] = list(seeds)
    processed: set[str]  = set()

    while queue:
        mid = queue.pop()
        if mid in processed:
            continue
        processed.add(mid)
        for rdep in rdep_graph.get(mid, set()):
            if rdep in active_set and rdep not in result:
                result.add(rdep)
                queue.append(rdep)
    return result


def _trim_graph(
    dep_graph: dict[str, set[str]],
    keep:      set[str],
) -> dict[str, set[str]]:
    """Sub-graph containing only nodes in *keep*."""
    return {
        mid: {d for d in deps if d in keep}
        for mid, deps in dep_graph.items()
        if mid in keep
    }


# ═════════════════════════════════════════════════════════════════════════════
# Bucketing
# ═════════════════════════════════════════════════════════════════════════════

def _bucket(
    mod_ids:        list[str],
    tier_zero_ids:  set[str],
    tier_one_ids:   set[str],
    tier_three_ids: set[str],
) -> tuple[list[str], list[str], list[str], list[str]]:
    t0, t1, t2, t3 = [], [], [], []
    for mid in mod_ids:
        if mid in tier_zero_ids:
            t0.append(mid)
        elif mid in tier_one_ids:
            t1.append(mid)
        elif mid in tier_three_ids:
            t3.append(mid)
        else:
            t2.append(mid)
    return t0, t1, t2, t3


# ═════════════════════════════════════════════════════════════════════════════
# Topological sort (per tier)
# ═════════════════════════════════════════════════════════════════════════════

def _sort_tier_list(
    tier_mods: list[str],
    dep_graph: dict[str, set[str]],
    installed: dict[str, ModInfo],
) -> list[str]:
    if not tier_mods:
        return []
    tier_set  = set(tier_mods)
    sub_graph = _trim_graph(dep_graph, tier_set)
    return _run_toposort(sub_graph, tier_set, installed,
                         label=f"tier({len(tier_mods)})")

def _run_toposort(
    sub_graph: dict[str, set[str]],
    tier_set:  set[str],
    installed: dict[str, ModInfo],
    label:     str = "",
) -> list[str]:
    try:
        levels = list(toposort(sub_graph))
    except CircularDependencyError:
        # Fall back: alphabetical for the whole tier
        return sorted(tier_set, key=lambda m: _mod_name(m, installed))

    result: list[str] = []
    placed: set[str]  = set()

    for level in levels:
        level_mods = sorted(
            [m for m in level if m in tier_set],
            key=lambda m: _mod_name(m, installed),
        )
        result.extend(level_mods)
        placed.update(level_mods)

    # Safety net for any node toposort didn't surface
    remaining = sorted(
        [m for m in tier_set if m not in placed],
        key=lambda m: _mod_name(m, installed),
    )
    result.extend(remaining)
    return result


# ═════════════════════════════════════════════════════════════════════════════
# Tier 0 canonical reorder
# ═════════════════════════════════════════════════════════════════════════════

def _reorder_tier_zero(sorted_t0: list[str]) -> list[str]:
    """
    Within tier 0:
      1. Pre-patchers (non-Core/DLC) in their toposorted order
      2. Core
      3. DLCs in canonical release order
    """
    pre  = [m for m in sorted_t0 if m not in CORE_AND_DLCS_SET]
    core = [m for m in sorted_t0 if m == CORE]
    dlcs = [d for d in DLCS if d in set(sorted_t0)]
    return pre + core + dlcs


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _mod_name(mid: str, installed: dict[str, ModInfo]) -> str:
    info = installed.get(mid)
    return info.name.lower() if (info and info.name) else mid