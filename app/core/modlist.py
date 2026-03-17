import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

VANILLA_MODS = ['ludeon.rimworld']

ALL_DLCS = [
    'ludeon.rimworld.royalty',
    'ludeon.rimworld.ideology',
    'ludeon.rimworld.biotech',
    'ludeon.rimworld.anomaly',
    'ludeon.rimworld.odyssey',
]

VANILLA_AND_DLCS = VANILLA_MODS + ALL_DLCS

# Tier 0 mods MUST load before Core (Harmony, Prepatcher, etc.)
TIER_ZERO_MODS = {
    'brrainz.harmony',
    'zetrith.prepatcher',
    'ludeon.rimworld.prepatcher',
}


def read_mods_config(config_path: Path) -> tuple[list[str], str, list[str]]:
    """Returns (active_mods, version, known_expansions)."""
    xml_path = config_path / 'ModsConfig.xml'
    if not xml_path.exists():
        return [], '', []
    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
    except ET.ParseError:
        return [], '', []

    version = ''
    ver_elem = root.find('version')
    if ver_elem is not None and ver_elem.text:
        version = ver_elem.text.strip()

    active_mods = []
    active_elem = root.find('activeMods')
    if active_elem is not None:
        for li in active_elem.findall('li'):
            if li.text:
                active_mods.append(li.text.strip())

    known_exp = []
    exp_elem = root.find('knownExpansions')
    if exp_elem is not None:
        for li in exp_elem.findall('li'):
            if li.text:
                known_exp.append(li.text.strip())

    return active_mods, version, known_exp


def write_mods_config(config_path: Path, mod_ids: list[str],
                      version: str = '1.5.4104 rev961',
                      known_expansions: Optional[list[str]] = None):
    """
    Write ModsConfig.xml PRESERVING user order.
    
    Only ensures CRITICAL mods are in correct positions:
    - Tier 0 mods (Harmony, Prepatcher) BEFORE Core
    - Core exists
    - DLCs after Core
    
    Everything else keeps user's exact order.
    """
    config_path.mkdir(parents=True, exist_ok=True)

    # Separate mods into tiers
    tier_zero = []  # Harmony, Prepatcher - MUST be before Core
    core_mod = None
    dlc_mods = []
    other_mods = []
    
    for mod_id in mod_ids:
        mod_lower = mod_id.lower()
        
        if mod_lower in TIER_ZERO_MODS:
            tier_zero.append(mod_id)
        elif mod_lower == 'ludeon.rimworld':
            core_mod = mod_id
        elif mod_lower in [d.lower() for d in ALL_DLCS]:
            dlc_mods.append(mod_id)
        else:
            other_mods.append(mod_id)
    
    # Ensure Core exists
    if core_mod is None:
        core_mod = 'ludeon.rimworld'
        print("[ModsConfig] WARNING: Core was missing, adding")
    
    # Build final order:
    # 1. Tier 0 (Harmony, etc.) - in user's order
    # 2. Core
    # 3. DLCs - in user's order
    # 4. Everything else - in user's exact order
    ordered_mods = tier_zero + [core_mod] + dlc_mods + other_mods
    
    # === Build XML ===
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<ModsConfigData>',
        f'  <version>{version}</version>',
        '  <activeMods>',
    ]
    
    for mod_id in ordered_mods:
        safe_id = (mod_id
                   .replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;'))
        lines.append(f'    <li>{safe_id}</li>')
    
    lines.append('  </activeMods>')

    # Auto-detect DLCs for knownExpansions
    if known_expansions is None:
        known_expansions = []
        for mod in ordered_mods:
            mod_lower = mod.lower()
            if mod_lower.startswith('ludeon.rimworld.') and mod_lower != 'ludeon.rimworld':
                known_expansions.append(mod)
    
    if known_expansions:
        lines.append('  <knownExpansions>')
        for exp in known_expansions:
            safe_exp = (exp
                        .replace('&', '&amp;')
                        .replace('<', '&lt;')
                        .replace('>', '&gt;')
                        .replace('"', '&quot;'))
            lines.append(f'    <li>{safe_exp}</li>')
        lines.append('  </knownExpansions>')

    lines.append('</ModsConfigData>')
    
    xml_path = config_path / 'ModsConfig.xml'
    xml_path.write_text('\n'.join(lines), encoding='utf-8')
    
    print(f"[ModsConfig] Wrote {len(ordered_mods)} mods")
    print(f"[ModsConfig] First 10: {ordered_mods[:10]}")
    
    # Verify critical order
    if tier_zero:
        print(f"[ModsConfig] ✓ Tier 0 mods before Core: {tier_zero}")
    if ordered_mods[len(tier_zero)] == core_mod:
        print(f"[ModsConfig] ✓ Core at position {len(tier_zero)}")
    else:
        print(f"[ModsConfig] ⚠ WARNING: Core not in expected position!")
    
    return xml_path


def parse_rimsort_modlist(filepath: str) -> list[str]:
    mod_ids = []
    pattern = re.compile(r'\[([a-zA-Z0-9_.]+)\]\[http')
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                match = pattern.search(line)
                if match:
                    mod_ids.append(match.group(1))
    except (FileNotFoundError, PermissionError):
        pass
    return mod_ids


def export_rimsort_modlist(filepath: str, mod_ids: list[str],
                           mod_names: Optional[dict[str, str]] = None,
                           version: str = '1.5.4104 rev961'):
    lines = [
        'Created with RimWorld Instance Manager',
        f'RimWorld game version this list was created for: {version}',
        f'Total # of mods: {len(mod_ids)}',
        '',
    ]
    for mod_id in mod_ids:
        name = mod_names.get(mod_id, mod_id) if mod_names else mod_id
        lines.append(f'{name} [{mod_id}][https://example.com/]')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def get_vanilla_modlist(owned_dlcs: Optional[list[str]] = None) -> list[str]:
    mods = list(VANILLA_MODS)
    if owned_dlcs:
        for dlc in owned_dlcs:
            if dlc in ALL_DLCS:
                mods.append(dlc)
    return mods