"""
Instance lifecycle management — create, scan, duplicate, import, and delete
Onyx launcher instances.
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.instance import Instance
from app.core.modlist import (
    write_mods_config,
    read_mods_config,
    VANILLA_MODS,
    ALL_DLCS,
)
from app.core.paths import get_default_rw_data
from app.utils.file_utils import ensure_dir, safe_delete_tree


# ── Module-Level Constants ────────────────────────────────────────────────────

DEFAULT_VERSION = '1.6.4630 rev467'


# ── InstanceManager ───────────────────────────────────────────────────────────

class InstanceManager:
    """
    Manages the collection of Onyx launcher instances stored under
    a root directory. Each instance is a subdirectory containing
    instance.json, Config/, and Saves/.
    """

    def __init__(self, instances_root: Path):
        self.instances_root = instances_root
        ensure_dir(self.instances_root)

    # ── Scanning ──────────────────────────────────────────────────────────────

    def scan_instances(self) -> list[Instance]:
        """
        Return all valid instances found under instances_root,
        sorted by name.

        A valid instance is a directory containing instance.json
        that Instance.load() can parse without error.
        """
        if not self.instances_root.exists():
            return []
        instances: list[Instance] = []
        for folder in sorted(self.instances_root.iterdir()):
            if folder.is_dir() and (folder / 'instance.json').exists():
                inst = Instance.load(folder)
                if inst:
                    instances.append(inst)
        return instances

    # ── Creation ──────────────────────────────────────────────────────────────

    def create_instance(
            self,
            name: str,
            path: Optional[Path] = None,
            mods: Optional[list[str]] = None,
            version: str = DEFAULT_VERSION,
            notes: str = '',
    ) -> Instance:
        """
        Create a new instance at the given path (or instances_root/name).

        Raises FileExistsError if the target directory already exists.
        Uses VANILLA_MODS as the default mod list when mods is None.
        """
        inst_path = path or self.instances_root / name
        if inst_path.exists():
            raise FileExistsError(f"Already exists: {inst_path}")

        ensure_dir(inst_path / 'Config')
        ensure_dir(inst_path / 'Saves')

        mod_list = list(mods) if mods is not None else list(VANILLA_MODS)
        write_mods_config(inst_path / 'Config', mod_list, version)

        inst = Instance(
            name=name,
            path=inst_path,
            mods=mod_list,
            created=datetime.now().isoformat(),
            rimworld_version=version,
            notes=notes,
        )
        inst.save()
        return inst

    def create_vanilla_instance(
            self,
            name: str,
            owned_dlcs: Optional[list[str]] = None,
            version: str = DEFAULT_VERSION,
    ) -> Instance:
        """
        Create an instance pre-populated with Core and any owned DLCs.

        owned_dlcs should be a list of package IDs such as
        ['ludeon.rimworld.royalty', 'ludeon.rimworld.ideology'].
        Only IDs present in ALL_DLCS are included.
        """
        mod_list = list(VANILLA_MODS)
        if owned_dlcs:
            for dlc in owned_dlcs:
                if dlc in ALL_DLCS and dlc not in mod_list:
                    mod_list.append(dlc)
        return self.create_instance(name, mods=mod_list, version=version)

    # ── Mutation ──────────────────────────────────────────────────────────────

    def delete_instance(self, inst: Instance) -> None:
        """Permanently delete an instance directory and all its contents."""
        safe_delete_tree(inst.path)

    def duplicate_instance(
            self,
            inst: Instance,
            new_name: str,
            new_path: Optional[Path] = None,
    ) -> Instance:
        """
        Create a full copy of inst under new_name (or new_path).

        Delegates to Instance.duplicate() which copies the directory tree
        and resets created/last_played/playtime fields.
        """
        return inst.duplicate(new_name, new_path)

    def rename_instance(self, inst: Instance, new_name: str) -> None:
        """Update the display name of an instance and persist the change."""
        inst.name = new_name
        inst.save()

    # ── Import / Detection ────────────────────────────────────────────────────

    def detect_existing_rw_data(self) -> Optional[dict]:
        """
        Check whether the default RimWorld data directory contains usable data.

        Returns a summary dict with keys:
            path, mod_count, save_count, version, mods
        or None if no usable config or saves are found.
        """
        default = get_default_rw_data().resolve()
        if not default.exists():
            return None

        config_dir = default / 'Config'
        saves_dir  = default / 'Saves'

        has_config = (
            config_dir.exists()
            and (config_dir / 'ModsConfig.xml').exists()
        )
        has_saves = saves_dir.exists() and any(saves_dir.glob('*.rws'))

        if not has_config and not has_saves:
            return None

        mods, version = (
            _read_existing_config(config_dir)
            if has_config else ([], '')
        )
        save_count = _count_saves(saves_dir) if has_saves else 0

        return {
            'path':       str(default),
            'mod_count':  len(mods),
            'save_count': save_count,
            'version':    version,
            'mods':       mods,
        }

    def import_existing_data(self, name: str, source_path: Path) -> Instance:
        """
        Import a RimWorld Config and Saves directory as a new instance.

        Copies Config/ and Saves/ from source_path into a new instance
        directory, then reads the mod list and version from the copied
        ModsConfig.xml.

        Raises FileExistsError if an instance with this name already exists.
        """
        target = self.instances_root / name
        if target.exists():
            raise FileExistsError(f"Already exists: {target}")

        ensure_dir(target)
        _copy_dir_or_create(source_path / 'Config', target / 'Config')
        _copy_dir_or_create(source_path / 'Saves',  target / 'Saves')

        mods, version = _read_existing_config(target / 'Config')
        inst = Instance(
            name=name,
            path=target,
            mods=mods,
            created=datetime.now().isoformat(),
            rimworld_version=version or DEFAULT_VERSION,
            notes='Imported from existing RimWorld data',
        )
        inst.save()
        return inst

    # ── Query ──────────────────────────────────────────────────────────────

    def instance_exists(self, name: str) -> bool:
        """Return True if name directory exists under instances_root."""
        return (self.instances_root / name).exists()


# ── Module-Level Helpers ──────────────────────────────────────────────────────

def _read_existing_config(config_dir: Path) -> tuple[list[str], str]:
    """
    Read mods and version from a Config directory's ModsConfig.xml.

    Returns ([], '') if the file is missing or unreadable.
    """
    try:
        mods, version, _ = read_mods_config(config_dir)
        return mods, version
    except (OSError, ValueError):
        return [], ''


def _count_saves(saves_dir: Path) -> int:
    """Count .rws save files in saves_dir without loading them into memory."""
    return sum(1 for _ in saves_dir.glob('*.rws'))


def _copy_dir_or_create(src: Path, dst: Path) -> None:
    """
    Copy src to dst if src exists, otherwise create an empty dst directory.

    Used during instance import to handle missing Config or Saves folders
    in the source gracefully.
    """
    if src.exists():
        shutil.copytree(src, dst)
    else:
        ensure_dir(dst)
