import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from app.utils.xml_utils import parse_xml_safe, get_text, get_list


@dataclass
class ModInfo:
    package_id: str
    name: str
    author: str
    description: str = ''
    path: Path = Path()
    supported_versions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    load_after: list[str] = field(default_factory=list)
    load_before: list[str] = field(default_factory=list)
    source: str = 'local'
    workshop_id: str = ''
    preview_image: str = ''

    @classmethod
    def from_path(cls, mod_path: Path, source: str = 'local') -> Optional['ModInfo']:
        about_xml = None
        for candidate in [
            mod_path / 'About' / 'About.xml',
            mod_path / 'About' / 'about.xml',
            mod_path / 'about' / 'About.xml',
            mod_path / 'about' / 'about.xml',
            mod_path / 'About.xml',
        ]:
            if candidate.exists():
                about_xml = candidate
                break

        if about_xml is None:
            return None

        root = parse_xml_safe(about_xml)
        if root is None:
            return None

        package_id = get_text(root, 'packageId', mod_path.name).lower().strip()
        name = get_text(root, 'name', mod_path.name)
        author = get_text(root, 'author', 'Unknown')
        description = get_text(root, 'description', '')
        versions = get_list(root, 'supportedVersions')

        deps = []
        deps_elem = root.find('modDependencies')
        if deps_elem is not None:
            for dep in deps_elem.findall('li'):
                dep_id = get_text(dep, 'packageId')
                if dep_id:
                    deps.append(dep_id.lower().strip())

        load_after = [x.lower().strip() for x in get_list(root, 'loadAfter')]
        load_before = [x.lower().strip() for x in get_list(root, 'loadBefore')]

        preview = ''
        for pname in ['Preview.png', 'preview.png', 'Preview.jpg', 'preview.jpg']:
            pp = about_xml.parent / pname
            if pp.exists():
                preview = str(pp)
                break

        workshop_id = ''
        for pid_name in ['PublishedFileId.txt', 'publishedfileid.txt']:
            pid_file = about_xml.parent / pid_name
            if pid_file.exists():
                try:
                    workshop_id = pid_file.read_text().strip()
                except Exception:
                    pass
                break

        if not workshop_id and mod_path.name.isdigit():
            workshop_id = mod_path.name

        return cls(
            package_id=package_id, name=name, author=author,
            description=description, path=mod_path,
            supported_versions=versions, dependencies=deps,
            load_after=load_after, load_before=load_before,
            source=source, workshop_id=workshop_id,
            preview_image=preview,
        )


class RimWorldDetector:
    def __init__(self, game_path: Optional[str] = None):
        self.game_path = Path(game_path) if game_path else None
        self.exe_path: Optional[Path] = None
        self.version: str = ''
        self._mods_cache: dict[str, ModInfo] = {}
        self._extra_paths: list[str] = []

        if self.game_path:
            self._detect_exe()
            self._detect_version()

    def _detect_exe(self):
        if not self.game_path:
            return
        for name in ['RimWorldWin64.exe', 'RimWorldWin.exe', 'RimWorld.exe']:
            c = self.game_path / name
            if c.exists():
                self.exe_path = c
                return

    def _detect_version(self):
        if not self.game_path:
            return
        vf = self.game_path / 'Version.txt'
        if vf.exists():
            try:
                self.version = vf.read_text().strip()
            except Exception:
                pass

    def set_game_path(self, path: str):
        self.game_path = Path(path)
        self._detect_exe()
        self._detect_version()
        self._mods_cache.clear()

    def get_installed_mods(self, extra_mod_paths: Optional[list[str]] = None,
                           force_rescan: bool = False) -> dict[str, ModInfo]:
        # Store extra paths so they persist across calls
        if extra_mod_paths is not None:
            self._extra_paths = list(extra_mod_paths)

        if self._mods_cache and not force_rescan:
            return self._mods_cache

        mods = {}
        scanned = set()

        def scan(dirpath: Path, source: str):
            resolved = str(dirpath.resolve())
            if not dirpath.exists() or resolved in scanned:
                return
            scanned.add(resolved)
            found = 0
            try:
                for mod_dir in dirpath.iterdir():
                    if not mod_dir.is_dir():
                        continue
                    info = ModInfo.from_path(mod_dir, source=source)
                    if info and info.package_id not in mods:
                        mods[info.package_id] = info
                        found += 1
            except PermissionError:
                pass
            print(f"[ModScan] {dirpath} -> {found} mods (source={source})")

        # Game data
        if self.game_path:
            scan(self.game_path / 'Data', 'dlc')
            scan(self.game_path / 'Mods', 'local')

        # All extra paths
        for ep in self._extra_paths:
            p = Path(ep)
            if p.exists():
                ep_lower = str(p).lower()
                source = 'local'
                if 'workshop' in ep_lower or 'onyx' in ep_lower:
                    source = 'workshop'
                scan(p, source)

        self._mods_cache = mods
        print(f"[ModScan] TOTAL: {len(mods)} mods from {len(scanned)} directories")
        return mods

    def get_detected_dlcs(self) -> list[str]:
        mods = self.get_installed_mods()
        dlcs = [
            'ludeon.rimworld.royalty', 'ludeon.rimworld.ideology',
            'ludeon.rimworld.biotech', 'ludeon.rimworld.anomaly',
        ]
        return [d for d in dlcs if d in mods]

    def find_missing_mods(self, mod_ids: list[str]) -> list[str]:
        installed = self.get_installed_mods()
        return [m for m in mod_ids if m not in installed]