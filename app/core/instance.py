"""
Instance data model — represents a single Onyx launcher instance.

Each instance is a directory containing:
  instance.json  — persisted metadata (this class)
  Config/        — RimWorld ModsConfig.xml and other config files
  Saves/         — RimWorld .rws save files
"""

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Instance:
    """
    All persistent state for one Onyx launcher instance.

    Fields are stored in instance.json via save() and restored via load().
    Mutation helpers (activate_mod, deactivate_mod, add_mod) keep the
    mods and inactive_mods lists consistent with each other.
    """

    name:                   str
    path:                   Path
    mods:                   list[str]       = field(default_factory=list)
    inactive_mods:          list[str]       = field(default_factory=list)
    created:                str             = ''
    last_played:            str             = ''
    rimworld_version:       str             = '1.6.4630 rev467'
    notes:                  str             = ''
    launch_args:            list[str]       = field(default_factory=list)
    icon_color:             str             = ''
    icon_key:               str             = ''
    group:                  str             = ''
    total_playtime_minutes: int             = 0
    mods_configured:        bool            = False
    ignored_deps:           list[str]       = field(default_factory=list)
    ignored_errors:         list[str]       = field(default_factory=list)
    mod_workshop_ids:       dict[str, str]  = field(default_factory=dict)
    rimworld_exe_override:  str             = ''

    # ── Persistence ───────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path) -> Optional['Instance']:
        """
        Load an Instance from path/instance.json.

        Returns None if the file is missing, unreadable, or malformed.
        The rimworld_version defaults to '1.6' (short form) when absent
        from the JSON, which is used for mod compatibility matching.
        """
        jp = path / 'instance.json'
        if not jp.exists():
            return None
        try:
            with open(jp, 'r', encoding='utf-8') as f:
                d = json.load(f)
            return cls(**_from_dict(d, path))
        except (json.JSONDecodeError, KeyError, OSError, TypeError):
            return None

    def save(self) -> None:
        """
        Atomically persist this instance to instance.json.

        Writes to a .tmp file first, then renames it over the target.
        This prevents corruption if the process is interrupted mid-write.

        Raises RuntimeError (wrapping the original exception) on failure.
        """
        self.path.mkdir(parents=True, exist_ok=True)
        tmp = self.path / 'instance.json.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(_to_dict(self), f, indent=2)
            tmp.replace(self.path / 'instance.json')
        except (OSError, TypeError) as exc:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(
                f"Failed to save instance '{self.name}': {exc}") from exc

    def duplicate(self, new_name: str,
                  new_path: Optional[Path] = None) -> 'Instance':
        """
        Copy this instance's directory to a new location and return the copy.

        The duplicate gets a new created timestamp and reset playtime/
        last_played fields. Raises RuntimeError if the copy cannot be loaded.
        """
        target = new_path or self.path.parent / new_name
        shutil.copytree(self.path, target)
        inst = Instance.load(target)
        if inst is None:
            raise RuntimeError(
                f"Failed to load duplicated instance at {target}")
        inst.name                   = new_name
        inst.created                = datetime.now().isoformat()
        inst.last_played            = ''
        inst.total_playtime_minutes = 0
        inst.save()
        return inst

    # ── Mod list helpers ──────────────────────────────────────────────────────

    def activate_mod(self, mod_id: str) -> None:
        """Move mod_id from inactive_mods to mods (no-op if already active)."""
        if mod_id in self.inactive_mods:
            self.inactive_mods.remove(mod_id)
        if mod_id not in self.mods:
            self.mods.append(mod_id)

    def deactivate_mod(self, mod_id: str) -> None:
        """Move mod_id from mods to inactive_mods (no-op if already inactive)."""
        if mod_id in self.mods:
            self.mods.remove(mod_id)
        if mod_id not in self.inactive_mods:
            self.inactive_mods.append(mod_id)

    def add_mod(self, mod_id: str, active: bool = True) -> None:
        """
        Add mod_id to either the active or inactive list.

        Ensures mod_id is not present in the other list — keeps both
        lists mutually exclusive.
        """
        if active:
            if mod_id not in self.mods:
                self.mods.append(mod_id)
            if mod_id in self.inactive_mods:
                self.inactive_mods.remove(mod_id)
        else:
            if mod_id not in self.inactive_mods:
                self.inactive_mods.append(mod_id)
            if mod_id in self.mods:
                self.mods.remove(mod_id)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def all_mods(self) -> list[str]:
        """Combined list of active and inactive mods."""
        return self.mods + self.inactive_mods

    @property
    def save_count(self) -> int:
        """Number of .rws save files in the Saves directory."""
        sd = self.saves_dir
        return sum(1 for _ in sd.glob('*.rws')) if sd.exists() else 0

    @property
    def mod_count(self) -> int:
        """Number of active mods."""
        return len(self.mods)

    @property
    def config_dir(self) -> Path:
        """Path to the Config subdirectory (contains ModsConfig.xml)."""
        return self.path / 'Config'

    @property
    def saves_dir(self) -> Path:
        """Path to the Saves subdirectory."""
        return self.path / 'Saves'

    @property
    def has_saves(self) -> bool:
        """True if at least one .rws save file exists."""
        return self.save_count > 0

    def get_save_files(self) -> list[dict]:
        """
        Return metadata for all save files, sorted newest-first.

        Each entry is a dict with keys:
            name     — filename stem (no extension)
            path     — absolute path string
            size     — file size in bytes
            modified — ISO-format local datetime string
        """
        sd = self.saves_dir
        if not sd.exists():
            return []
        saves = []
        for rws in sd.glob('*.rws'):
            st = rws.stat()
            saves.append({
                'name':     rws.stem,
                'path':     str(rws),
                'size':     st.st_size,
                'modified': datetime.fromtimestamp(st.st_mtime).isoformat(),
            })
        return sorted(saves, key=lambda s: s['modified'], reverse=True)


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _to_dict(inst: Instance) -> dict:
    """Serialise an Instance to a plain dict suitable for json.dump."""
    return {
        'name':                   inst.name,
        'mods':                   inst.mods,
        'inactive_mods':          inst.inactive_mods,
        'created':                inst.created,
        'last_played':            inst.last_played,
        'rimworld_version':       inst.rimworld_version,
        'notes':                  inst.notes,
        'launch_args':            inst.launch_args,
        'icon_color':             inst.icon_color,
        'icon_key':               inst.icon_key,
        'group':                  inst.group,
        'total_playtime_minutes': inst.total_playtime_minutes,
        'mods_configured':        inst.mods_configured,
        'ignored_deps':           inst.ignored_deps,
        'ignored_errors':         inst.ignored_errors,
        'mod_workshop_ids':       inst.mod_workshop_ids,
        'rimworld_exe_override':  inst.rimworld_exe_override,
    }


def _from_dict(d: dict, path: Path) -> dict:
    """
    Build the keyword-argument dict for Instance.__init__ from a JSON dict.

    Missing keys fall back to safe defaults so old instance.json files
    remain loadable after new fields are added.
    """
    return {
        'name':                   d.get('name', path.name),
        'path':                   path,
        'mods':                   d.get('mods', []),
        'inactive_mods':          d.get('inactive_mods', []),
        'created':                d.get('created', ''),
        'last_played':            d.get('last_played', ''),
        'rimworld_version':       d.get('rimworld_version', '1.6'),
        'notes':                  d.get('notes', ''),
        'launch_args':            d.get('launch_args', []),
        'icon_color':             d.get('icon_color', ''),
        'icon_key':               d.get('icon_key', ''),
        'group':                  d.get('group', ''),
        'total_playtime_minutes': d.get('total_playtime_minutes', 0),
        'mods_configured':        d.get('mods_configured', False),
        'ignored_deps':           d.get('ignored_deps', []),
        'ignored_errors':         d.get('ignored_errors', []),
        'mod_workshop_ids':       d.get('mod_workshop_ids', {}),
        'rimworld_exe_override':  d.get('rimworld_exe_override', ''),
    }
