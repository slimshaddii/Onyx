import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
from app.core.instance import Instance
from app.core.modlist import write_mods_config, read_mods_config, VANILLA_MODS, ALL_DLCS
from app.core.paths import get_default_rw_data
from app.utils.file_utils import ensure_dir, safe_delete_tree


class InstanceManager:
    def __init__(self, instances_root: Path):
        self.instances_root = instances_root
        ensure_dir(self.instances_root)

    def scan_instances(self) -> list[Instance]:
        instances = []
        if not self.instances_root.exists():
            return instances
        for folder in sorted(self.instances_root.iterdir()):
            if folder.is_dir() and (folder / 'instance.json').exists():
                inst = Instance.load(folder)
                if inst:
                    instances.append(inst)
        return instances

    def create_instance(self, name: str, path: Optional[Path] = None,
                        mods: Optional[list[str]] = None,
                        version: str = '1.6.4630 rev467',
                        notes: str = '') -> Instance:
        inst_path = path or self.instances_root / name
        if inst_path.exists():
            raise FileExistsError(f"Already exists: {inst_path}")
        ensure_dir(inst_path / 'Config')
        ensure_dir(inst_path / 'Saves')
        mod_list = mods if mods is not None else list(VANILLA_MODS)
        write_mods_config(inst_path / 'Config', mod_list, version)
        inst = Instance(
            name=name, path=inst_path, mods=mod_list,
            created=datetime.now().isoformat(),
            rimworld_version=version, notes=notes)
        inst.save()
        return inst

    def create_vanilla_instance(self, name: str, owned_dlcs: Optional[list[str]] = None,
                                version: str = '1.6.4630 rev467') -> Instance:
        mods = list(VANILLA_MODS)
        if owned_dlcs:
            for d in owned_dlcs:
                if d in ALL_DLCS and d not in mods:
                    mods.append(d)
        return self.create_instance(name, mods=mods, version=version)

    def delete_instance(self, inst: Instance):
        safe_delete_tree(inst.path)

    def duplicate_instance(self, inst: Instance, new_name: str,
                           new_path: Optional[Path] = None) -> Instance:
        return inst.duplicate(new_name, new_path)

    def rename_instance(self, inst: Instance, new_name: str):
        inst.name = new_name
        inst.save()

    def detect_existing_rw_data(self) -> Optional[dict]:
        default = get_default_rw_data().resolve()
        if not default.exists():
            return None
        config = default / 'Config'
        saves = default / 'Saves'
        has_config = config.exists() and (config / 'ModsConfig.xml').exists()
        has_saves = saves.exists() and any(saves.glob('*.rws'))
        if not (has_config or has_saves):
            return None

        mods, version, _ = read_mods_config(config) if has_config else ([], '', [])
        save_count = len(list(saves.glob('*.rws'))) if has_saves else 0

        return {
            'path': str(default),
            'mod_count': len(mods),
            'save_count': save_count,
            'version': version,
            'mods': mods,
        }

    def import_existing_data(self, name: str, source_path: Path) -> Instance:
        target = self.instances_root / name
        if target.exists():
            raise FileExistsError(f"Already exists: {target}")

        ensure_dir(target)
        src_config = source_path / 'Config'
        src_saves = source_path / 'Saves'
        if src_config.exists():
            shutil.copytree(str(src_config), str(target / 'Config'))
        else:
            ensure_dir(target / 'Config')
        if src_saves.exists():
            shutil.copytree(str(src_saves), str(target / 'Saves'))
        else:
            ensure_dir(target / 'Saves')

        mods, version, _ = read_mods_config(target / 'Config')
        inst = Instance(
            name=name, path=target, mods=mods,
            created=datetime.now().isoformat(),
            rimworld_version=version or '1.6',
            notes='Imported from existing RimWorld data')
        inst.save()
        return inst

    def instance_exists(self, name: str) -> bool:
        return (self.instances_root / name).exists()