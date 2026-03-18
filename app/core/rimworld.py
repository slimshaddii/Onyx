import time
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

    # Dependency priority (mutually exclusive by version):
    # forced_dependencies  → always required, regardless of version tags
    # dependencies         → base (no version tag) OR version-matched, never both
    forced_dependencies: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)

    load_after: list[str] = field(default_factory=list)
    load_before: list[str] = field(default_factory=list)
    incompatible_with: list[str] = field(default_factory=list)

    # Parsed directly from About.xml — no DB needed
    load_first: bool = False   # loadBefore: ludeon.rimworld → pre-patcher
    load_last: bool = False    # explicit marker (future-proofing)

    source: str = 'local'
    workshop_id: str = ''
    preview_image: str = ''

    @classmethod
    def from_path(cls, mod_path: Path, source: str = 'local',
                  game_version: str = '1.6') -> Optional['ModInfo']:
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

        package_id  = get_text(root, 'packageId', mod_path.name).lower().strip()
        name        = get_text(root, 'name', mod_path.name)
        author      = get_text(root, 'author', 'Unknown')
        description = get_text(root, 'description', '')
        versions    = get_list(root, 'supportedVersions')

        parts         = game_version.split('.')
        major_version = (f"{parts[0]}.{parts[1]}"
                         if len(parts) >= 2 else game_version)

        def _ids_from_li_block(parent_elem) -> set[str]:
            """Extract <packageId> text from <li> children."""
            result: set[str] = set()
            if parent_elem is None:
                return result
            for li in parent_elem.findall('li'):
                pid = get_text(li, 'packageId')
                if pid:
                    result.add(pid.lower().strip())
            return result

        def _ids_from_version_block(parent_elem,
                                    text_only: bool = False) -> set[str]:
            """
            Pick the best version-tagged child block.
            Priority: exact full version → major.minor → first major.* match.
            Returns IDs from that block only (mutually exclusive).
            """
            result: set[str] = set()
            if parent_elem is None:
                return result

            candidates = [f'v{game_version}', f'v{major_version}']
            for tag in candidates:
                ver_elem = parent_elem.find(tag)
                if ver_elem is not None:
                    for li in ver_elem.findall('li'):
                        val = (li.text if text_only
                               else get_text(li, 'packageId'))
                        if val:
                            result.add(val.lower().strip())
                    return result  # stop at first match

            # Fallback: first child whose tag starts with major number
            major_num = major_version.split('.')[0]
            for child in parent_elem:
                if child.tag.lstrip('v').startswith(major_num):
                    for li in child.findall('li'):
                        val = (li.text if text_only
                               else get_text(li, 'packageId'))
                        if val:
                            result.add(val.lower().strip())
                    break
            return result

        # ── Forced dependencies (always required, no version gating) ──────
        forced_deps: set[str] = set()
        forced_elem = root.find('modDependenciesForced')
        if forced_elem is not None:
            forced_deps = _ids_from_li_block(forced_elem)

        # ── Regular dependencies: ByVersion wins over base ─────────────────
        # "DependencyByVersion is mutually exclusive with base Dependencies"
        deps_by_version = _ids_from_version_block(
            root.find('modDependenciesByVersion'), text_only=False)

        if deps_by_version:
            # Version-specific block exists → ignore base modDependencies
            base_deps: set[str] = set()
        else:
            base_deps = _ids_from_li_block(root.find('modDependencies'))

        # Final deps = whichever won (forced is additive on top)
        resolved_deps = deps_by_version | base_deps

        # ── loadAfter: ByVersion wins over base ────────────────────────────
        load_after_by_ver = _ids_from_version_block(
            root.find('loadAfterByVersion'), text_only=True)
        if load_after_by_ver:
            load_after = load_after_by_ver
        else:
            load_after = {x.lower().strip()
                          for x in get_list(root, 'loadAfter')}

        # ── loadBefore: ByVersion wins over base ───────────────────────────
        load_before_by_ver = _ids_from_version_block(
            root.find('loadBeforeByVersion'), text_only=True)
        if load_before_by_ver:
            load_before = load_before_by_ver
        else:
            load_before = {x.lower().strip()
                           for x in get_list(root, 'loadBefore')}

        # ── incompatibleWith: ByVersion wins over base ─────────────────────
        incompat_by_ver = _ids_from_version_block(
            root.find('incompatibleWithByVersion'), text_only=True)
        if incompat_by_ver:
            incompatible = incompat_by_ver
        else:
            incompatible = {x.lower().strip()
                            for x in get_list(root, 'incompatibleWith')}

        # ── Tier flags derived purely from About.xml ───────────────────────
        # load_first: mod declares it must load before Core itself
        load_first = 'ludeon.rimworld' in load_before

        # load_last: mod declares it must load after everything
        # (no standard XML tag for this yet, kept for future-proofing)
        load_last = False

        # ── Preview image ──────────────────────────────────────────────────
        preview = ''
        for pname in ['Preview.png', 'preview.png',
                       'Preview.jpg', 'preview.jpg']:
            pp = about_xml.parent / pname
            if pp.exists():
                preview = str(pp)
                break

        # ── Workshop ID ────────────────────────────────────────────────────
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
            package_id=package_id,
            name=name,
            author=author,
            description=description,
            path=mod_path,
            supported_versions=versions,
            forced_dependencies=sorted(forced_deps),
            dependencies=sorted(resolved_deps),
            load_after=sorted(load_after),
            load_before=sorted(load_before),
            incompatible_with=sorted(incompatible),
            load_first=load_first,
            load_last=load_last,
            source=source,
            workshop_id=workshop_id,
            preview_image=preview,
        )


# ── RimWorldDetector (unchanged except version surfacing) ─────────────────────

class RimWorldDetector:
    def __init__(self, game_path: Optional[str] = None):
        self.game_path    = Path(game_path) if game_path else None
        self.exe_path: Optional[Path] = None
        self.version: str = ''
        self._mods_cache: dict[str, ModInfo] = {}
        self._extra_paths: list[str] = []
        self._cache_time: float = 0.0

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
        self._cache_time = 0.0

    def get_game_version_short(self) -> str:
        if self.version:
            parts = self.version.split('.')
            if len(parts) >= 2:
                return f"{parts[0]}.{parts[1]}"
        return '1.6'

    def get_installed_mods(self, extra_mod_paths: Optional[list[str]] = None,
                           force_rescan: bool = False,
                           max_age_seconds: float = 30.0) -> dict[str, ModInfo]:
        if extra_mod_paths is not None:
            self._extra_paths = list(extra_mod_paths)

        now       = time.monotonic()
        cache_age = now - self._cache_time

        if self._mods_cache and not force_rescan:
            return self._mods_cache

        if (self._mods_cache and force_rescan
                and max_age_seconds > 0
                and cache_age < max_age_seconds):
            return self._mods_cache

        mods: dict[str, ModInfo] = {}
        scanned: set[str] = set()
        game_ver = self.get_game_version_short()

        def scan(dirpath: Path, source: str):
            resolved = str(dirpath.resolve())
            if not dirpath.exists() or resolved in scanned:
                return
            scanned.add(resolved)
            try:
                for mod_dir in dirpath.iterdir():
                    if not mod_dir.is_dir():
                        continue
                    info = ModInfo.from_path(
                        mod_dir, source=source, game_version=game_ver)
                    if info and info.package_id not in mods:
                        mods[info.package_id] = info
            except PermissionError:
                pass

        if self.game_path:
            scan(self.game_path / 'Data', 'dlc')
            scan(self.game_path / 'Mods', 'local')

        for ep in self._extra_paths:
            p = Path(ep)
            if p.exists():
                ep_lower = str(p).lower()
                source   = ('workshop'
                            if ('workshop' in ep_lower or 'onyx' in ep_lower)
                            else 'local')
                scan(p, source)

        self._mods_cache = mods
        self._cache_time = time.monotonic()
        return mods

    def get_detected_dlcs(self) -> list[str]:
        mods = self.get_installed_mods()
        dlcs = [
            'ludeon.rimworld.royalty',
            'ludeon.rimworld.ideology',
            'ludeon.rimworld.biotech',
            'ludeon.rimworld.anomaly',
            'ludeon.rimworld.odyssey',
        ]
        return [d for d in dlcs if d in mods]

    def find_missing_mods(self, mod_ids: list[str]) -> list[str]:
        installed = self.get_installed_mods()
        return [m for m in mod_ids if m not in installed]