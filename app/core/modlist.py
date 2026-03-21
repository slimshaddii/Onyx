"""
ModsConfig.xml reader/writer and modlist import/export utilities.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


# ── Module-Level Constants ────────────────────────────────────────────────────

VANILLA_MODS = ['ludeon.rimworld']

ALL_DLCS = [
    'ludeon.rimworld.royalty',
    'ludeon.rimworld.ideology',
    'ludeon.rimworld.biotech',
    'ludeon.rimworld.anomaly',
    'ludeon.rimworld.odyssey',
]

VANILLA_AND_DLCS = VANILLA_MODS + ALL_DLCS

_RIMSORT_PATTERN = re.compile(r'\[([a-zA-Z0-9_.]+)\]\[http')


# ── ModsConfig.xml I/O ───────────────────────────────────────────────────────

def read_mods_config(
        config_path: Path,
) -> tuple[list[str], str, list[str]]:
    """Return (active_mods, version, known_expansions) from ModsConfig.xml."""
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


def write_mods_config(
        config_path: Path,
        mod_ids: list[str],
        version: str = '1.6.4630 rev467',
        known_expansions: Optional[list[str]] = None,
) -> Path:
    """
    Write ModsConfig.xml preserving the exact order provided.

    Only inserts Core if it is entirely absent — does NOT reorder.
    Uses atomic temp-file-then-rename to prevent corruption on
    interrupted writes.
    """
    config_path.mkdir(parents=True, exist_ok=True)

    ordered_mods = list(mod_ids)

    if not any(m.lower() == 'ludeon.rimworld'
               for m in ordered_mods):
        insert_pos = 0
        for i, m in enumerate(ordered_mods):
            if m.lower().startswith('ludeon.rimworld.'):
                insert_pos = i
                break
        ordered_mods.insert(insert_pos, 'ludeon.rimworld')

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<ModsConfigData>',
        f'  <version>{version}</version>',
        '  <activeMods>',
        *[f'    <li>{_xml_escape(mid)}</li>'
          for mid in ordered_mods],
        '  </activeMods>',
    ]

    if known_expansions is None:
        known_expansions = [
            m for m in ordered_mods
            if m.lower().startswith('ludeon.rimworld.')
            and m.lower() != 'ludeon.rimworld'
        ]

    if known_expansions:
        lines += [
            '  <knownExpansions>',
            *[f'    <li>{_xml_escape(exp)}</li>'
              for exp in known_expansions],
            '  </knownExpansions>',
        ]

    lines.append('</ModsConfigData>')

    xml_path = config_path / 'ModsConfig.xml'
    tmp_path = xml_path.with_suffix('.xml.tmp')
    try:
        tmp_path.write_text(
            '\n'.join(lines), encoding='utf-8')
        tmp_path.replace(xml_path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise

    return xml_path


# ── RimSort Import/Export ─────────────────────────────────────────────────────

def parse_rimsort_modlist(filepath: str) -> list[str]:
    """Parse a RimSort-format modlist text file and return package IDs."""
    mod_ids: list[str] = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                m = _RIMSORT_PATTERN.search(line)
                if m:
                    mod_ids.append(m.group(1))
    except (FileNotFoundError, PermissionError):
        pass
    return mod_ids


def export_rimsort_modlist(
        filepath: str,
        mod_ids: list[str],
        mod_names: Optional[dict[str, str]] = None,
        version: str = '1.6.4630 rev467',
) -> None:
    """Write mod_ids to a RimSort-compatible modlist text file."""
    lines = [
        'Created with Onyx Launcher',
        f'RimWorld game version: {version}',
        f'Total mods: {len(mod_ids)}',
        '',
        *[
            f"{mod_names.get(mid, mid) if mod_names else mid}"
            f" [{mid}][https://example.com/]"
            for mid in mod_ids
        ],
    ]
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


# ── Utility ───────────────────────────────────────────────────────────────────

def get_vanilla_modlist(
        owned_dlcs: Optional[list[str]] = None,
) -> list[str]:
    """Return Core plus any owned DLCs that are in ALL_DLCS."""
    mods = list(VANILLA_MODS)
    if owned_dlcs:
        mods.extend(d for d in owned_dlcs if d in ALL_DLCS)
    return mods


def _xml_escape(s: str) -> str:
    return (s.replace('&', '&amp;')
             .replace('<', '&lt;')
             .replace('>', '&gt;')
             .replace('"', '&quot;'))
