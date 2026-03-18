"""
Def collision scanner — finds duplicate defName values across active mods.

Scans each active mod's Defs/ folder (and version-specific Defs/ if present),
extracts all non-abstract defNames, and reports collisions where two or more
mods define the same defType + defName combination.

Runs on a QThread to avoid blocking the UI.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal


# Def types worth scanning — these are the ones most likely to cause
# gameplay-visible conflicts. Patch XML files are excluded (they live
# in Patches/, not Defs/).
_SCANNABLE_TYPES = {
    'ThingDef', 'HediffDef', 'RecipeDef', 'TraitDef',
    'ResearchProjectDef', 'BiomeDef', 'FactionDef',
    'PawnKindDef', 'JobDef', 'WorkGiverDef', 'ThoughtDef',
    'AbilityDef', 'GeneDef', 'RitualPatternDef', 'PreceptDef',
    'MemeDef', 'StatDef', 'DamageDef', 'WeatherDef',
    'IncidentDef', 'QuestScriptDef',
}


@dataclass
class DefEntry:
    def_type:  str    # e.g. 'ThingDef'
    def_name:  str    # e.g. 'Rimatomics_PipeSection'
    mod_id:    str    # package id of the owning mod
    mod_name:  str    # display name of the owning mod
    file_path: str    # relative path for debugging


@dataclass
class DefCollision:
    def_type:  str
    def_name:  str
    mods:      list[DefEntry]   # all mods that define this defName


def scan_defs(active_mods: dict,      # {mid: ModInfo}
              game_version: str        # e.g. '1.6'
              ) -> list[DefCollision]:
    """
    Synchronous scan — use DefScannerThread for threaded operation.

    Parameters
    ----------
    active_mods    : dict mapping package_id → ModInfo for active mods only
    game_version   : short version string e.g. '1.6'

    Returns
    -------
    List of DefCollision — one per (defType, defName) pair found in ≥2 mods.
    """
    # Map (def_type, def_name) → list[DefEntry]
    registry: dict[tuple[str, str], list[DefEntry]] = {}

    for mid, info in active_mods.items():
        if not info or not info.path or not info.path.exists():
            continue

        defs_dirs = _get_defs_dirs(info.path, game_version)
        for defs_dir in defs_dirs:
            _scan_defs_dir(defs_dir, mid, info.name, registry)

    # Return only entries with ≥2 mods (actual collisions)
    return [
        DefCollision(def_type=k[0], def_name=k[1], mods=v)
        for k, v in registry.items()
        if len(v) >= 2
    ]


def _get_defs_dirs(mod_path: Path, game_version: str) -> list[Path]:
    """
    Return Defs directories to scan for a mod, in priority order.
    Includes both the version-specific folder and the root Defs folder.
    Deduplicates in case they resolve to the same path.
    """
    dirs: list[Path] = []
    seen: set[str]   = set()

    candidates = [
        mod_path / game_version / 'Defs',
        mod_path / 'Defs',
    ]
    for d in candidates:
        resolved = str(d.resolve())
        if d.exists() and d.is_dir() and resolved not in seen:
            dirs.append(d)
            seen.add(resolved)

    return dirs


def _scan_defs_dir(defs_dir: Path, mod_id: str, mod_name: str,
                   registry: dict) -> None:
    """Walk a Defs directory, parse all XML, extract defNames."""
    try:
        xml_files = list(defs_dir.rglob('*.xml'))
    except (OSError, PermissionError):
        return

    for xml_file in xml_files:
        # Skip Patches directories that accidentally end up under Defs
        if 'Patches' in xml_file.parts:
            continue
        _parse_def_file(xml_file, mod_id, mod_name, defs_dir, registry)


def _parse_def_file(xml_file: Path, mod_id: str, mod_name: str,
                    defs_dir: Path, registry: dict) -> None:
    try:
        tree = ET.parse(str(xml_file))
        root = tree.getroot()
    except (ET.ParseError, OSError, UnicodeDecodeError):
        return

    if root.tag != 'Defs':
        return

    rel_path = str(xml_file.relative_to(defs_dir.parent))

    for def_elem in root:
        def_type = def_elem.tag

        # Skip unknown def types and XML comments
        if not isinstance(def_type, str):
            continue
        if def_type not in _SCANNABLE_TYPES:
            continue

        # Skip abstract defs — they are base classes, not real game objects.
        # Abstract="True" or Abstract="true" — case-insensitive.
        if def_elem.get('Abstract', '').lower() == 'true':
            continue

        def_name_elem = def_elem.find('defName')
        if def_name_elem is None or not def_name_elem.text:
            continue

        def_name = def_name_elem.text.strip()
        if not def_name:
            continue

        key   = (def_type, def_name)
        entry = DefEntry(
            def_type=def_type,
            def_name=def_name,
            mod_id=mod_id,
            mod_name=mod_name,
            file_path=rel_path,
        )

        if key not in registry:
            registry[key] = []

        # Deduplicate: same mod declaring same defName in both root Defs/
        # and version-specific Defs/ is not a collision.
        if not any(e.mod_id == mod_id for e in registry[key]):
            registry[key].append(entry)


# ── Threaded scanner (8.4) ────────────────────────────────────────────────────

class DefScannerThread(QThread):
    """
    Runs def_scanner.scan_defs() on a background thread.

    Signals
    -------
    progress(current, total, mod_name)  — emitted per mod scanned
    finished(list[DefCollision])        — emitted when scan completes
    error(str)                          — emitted if scan fails
    """
    progress = pyqtSignal(int, int, str)   # current, total, mod_name
    finished = pyqtSignal(list)            # list[DefCollision]
    error    = pyqtSignal(str)

    def __init__(self, active_mods: dict, game_version: str,
                 parent=None):
        super().__init__(parent)
        self._active_mods   = active_mods
        self._game_version  = game_version

    def run(self):
        try:
            registry: dict[tuple[str, str], list[DefEntry]] = {}
            items    = list(self._active_mods.items())
            total    = len(items)

            for i, (mid, info) in enumerate(items):
                mod_name = info.name if info else mid
                self.progress.emit(i + 1, total, mod_name)

                if not info or not info.path or not info.path.exists():
                    continue

                defs_dirs = _get_defs_dirs(info.path, self._game_version)
                for defs_dir in defs_dirs:
                    _scan_defs_dir(defs_dir, mid, mod_name, registry)

            collisions = [
                DefCollision(def_type=k[0], def_name=k[1], mods=v)
                for k, v in registry.items()
                if len(v) >= 2
            ]
            self.finished.emit(collisions)

        except Exception as e:
            self.error.emit(str(e))