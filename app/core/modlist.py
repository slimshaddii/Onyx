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


def read_mods_config(config_path: Path) -> tuple[list[str], str, list[str]]:
    """Return (active_mods, version, known_expansions)."""
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

    active_mods: list[str] = []
    active_elem = root.find('activeMods')
    if active_elem is not None:
        for li in active_elem.findall('li'):
            if li.text:
                active_mods.append(li.text.strip())

    known_exp: list[str] = []
    exp_elem = root.find('knownExpansions')
    if exp_elem is not None:
        for li in exp_elem.findall('li'):
            if li.text:
                known_exp.append(li.text.strip())

    return active_mods, version, known_exp


def write_mods_config(config_path: Path, mod_ids: list[str],
                      version: str = '1.6.4630 rev467',
                      known_expansions: Optional[list[str]] = None):
    """
    Write ModsConfig.xml preserving the exact order provided.
    Only inserts Core if it is entirely absent — does NOT reorder.
    """
    config_path.mkdir(parents=True, exist_ok=True)

    ordered_mods = list(mod_ids)

    # Guard: ensure Core is present somewhere
    if not any(m.lower() == 'ludeon.rimworld' for m in ordered_mods):
        # Insert before the first DLC, or at position 0
        insert_pos = 0
        for i, m in enumerate(ordered_mods):
            if m.lower().startswith('ludeon.rimworld.'):
                insert_pos = i
                break
        ordered_mods.insert(insert_pos, 'ludeon.rimworld')
        print("[ModsConfig] WARNING: Core was missing, inserted at position", insert_pos)

    def _esc(s: str) -> str:
        return (s.replace('&', '&amp;')
                 .replace('<', '&lt;')
                 .replace('>', '&gt;')
                 .replace('"', '&quot;'))

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<ModsConfigData>',
        f'  <version>{version}</version>',
        '  <activeMods>',
        *[f'    <li>{_esc(mid)}</li>' for mid in ordered_mods],
        '  </activeMods>',
    ]

    # Auto-populate knownExpansions from the mod list if not provided
    if known_expansions is None:
        known_expansions = [
            m for m in ordered_mods
            if m.lower().startswith('ludeon.rimworld.')
            and m.lower() != 'ludeon.rimworld'
        ]

    if known_expansions:
        lines += [
            '  <knownExpansions>',
            *[f'    <li>{_esc(exp)}</li>' for exp in known_expansions],
            '  </knownExpansions>',
        ]

    lines.append('</ModsConfigData>')

    xml_path = config_path / 'ModsConfig.xml'
    xml_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"[ModsConfig] Wrote {len(ordered_mods)} mods to {xml_path}")
    return xml_path


def parse_rimsort_modlist(filepath: str) -> list[str]:
    mod_ids: list[str] = []
    pattern = re.compile(r'\[([a-zA-Z0-9_.]+)\]\[http')
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                m = pattern.search(line)
                if m:
                    mod_ids.append(m.group(1))
    except (FileNotFoundError, PermissionError):
        pass
    return mod_ids


def export_rimsort_modlist(filepath: str, mod_ids: list[str],
                           mod_names: Optional[dict[str, str]] = None,
                           version: str = '1.6.4630 rev467'):
    lines = [
        'Created with Onyx Launcher',
        f'RimWorld game version: {version}',
        f'Total mods: {len(mod_ids)}',
        '',
        *[f"{mod_names.get(mid, mid) if mod_names else mid} [{mid}][https://example.com/]"
          for mid in mod_ids],
    ]
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def get_vanilla_modlist(owned_dlcs: Optional[list[str]] = None) -> list[str]:
    mods = list(VANILLA_MODS)
    if owned_dlcs:
        mods.extend(d for d in owned_dlcs if d in ALL_DLCS)
    return mods