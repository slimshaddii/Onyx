from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Optional
import json
import shutil


@dataclass
class Instance:
    name: str
    path: Path
    mods: list[str] = field(default_factory=list)
    inactive_mods: list[str] = field(default_factory=list)
    created: str = ''
    last_played: str = ''
    rimworld_version: str = '1.6'
    notes: str = ''
    launch_args: list[str] = field(default_factory=list)
    icon_color: str = ''
    icon_key: str = ''
    group: str = ''
    total_playtime_minutes: int = 0

    @classmethod
    def load(cls, path: Path) -> Optional['Instance']:
        jp = path / 'instance.json'
        if not jp.exists():
            return None
        try:
            with open(jp, 'r', encoding='utf-8') as f:
                d = json.load(f)
            return cls(
                name=d.get('name', path.name), path=path,
                mods=d.get('mods', []),
                inactive_mods=d.get('inactive_mods', []),
                created=d.get('created', ''),
                last_played=d.get('last_played', ''),
                rimworld_version=d.get('rimworld_version', '1.6'),
                notes=d.get('notes', ''),
                launch_args=d.get('launch_args', []),
                icon_color=d.get('icon_color', ''),
                icon_key=d.get('icon_key', ''),
                group=d.get('group', ''),
                total_playtime_minutes=d.get('total_playtime_minutes', 0),
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def save(self):
        self.path.mkdir(parents=True, exist_ok=True)
        d = {
            'name': self.name,
            'mods': self.mods,
            'inactive_mods': self.inactive_mods,
            'created': self.created,
            'last_played': self.last_played,
            'rimworld_version': self.rimworld_version,
            'notes': self.notes,
            'launch_args': self.launch_args,
            'icon_color': self.icon_color,
            'icon_key': self.icon_key,
            'group': self.group,
            'total_playtime_minutes': self.total_playtime_minutes,
        }
        with open(self.path / 'instance.json', 'w', encoding='utf-8') as f:
            json.dump(d, f, indent=2)

    def duplicate(self, new_name: str, new_path: Optional[Path] = None) -> 'Instance':
        target = new_path or self.path.parent / new_name
        shutil.copytree(str(self.path), str(target))
        inst = Instance.load(target)
        if inst:
            inst.name = new_name
            inst.created = datetime.now().isoformat()
            inst.last_played = ''
            inst.total_playtime_minutes = 0
            inst.save()
            return inst
        raise RuntimeError(f"Failed to load duplicated instance at {target}")

    def activate_mod(self, mod_id: str):
        if mod_id in self.inactive_mods:
            self.inactive_mods.remove(mod_id)
        if mod_id not in self.mods:
            self.mods.append(mod_id)

    def deactivate_mod(self, mod_id: str):
        if mod_id in self.mods:
            self.mods.remove(mod_id)
        if mod_id not in self.inactive_mods:
            self.inactive_mods.append(mod_id)

    def add_mod(self, mod_id: str, active: bool = True):
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

    @property
    def all_mods(self) -> list[str]:
        return self.mods + self.inactive_mods

    @property
    def save_count(self) -> int:
        sd = self.path / 'Saves'
        return len(list(sd.glob('*.rws'))) if sd.exists() else 0

    @property
    def mod_count(self) -> int:
        return len(self.mods)

    @property
    def config_dir(self) -> Path:
        return self.path / 'Config'

    @property
    def saves_dir(self) -> Path:
        return self.path / 'Saves'

    @property
    def has_saves(self) -> bool:
        return self.save_count > 0

    def get_save_files(self) -> list[dict]:
        saves = []
        sd = self.path / 'Saves'
        if sd.exists():
            for rws in sd.glob('*.rws'):
                st = rws.stat()
                saves.append({
                    'name': rws.stem, 'path': str(rws),
                    'size': st.st_size,
                    'modified': datetime.fromtimestamp(st.st_mtime).isoformat()
                })
        return sorted(saves, key=lambda s: s['modified'], reverse=True)