"""
RimWorld mod metadata parser and installation scanner.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.utils.xml_utils import parse_xml_safe, get_text, get_list

_ABOUT_XML_CANDIDATES = [
    'About/About.xml',
    'About/about.xml',
    'about/About.xml',
    'about/about.xml',
    'About.xml',
]

_PREVIEW_NAMES = ['Preview.png', 'preview.png', 'Preview.jpg', 'preview.jpg']
_WORKSHOP_ID_NAMES = ['PublishedFileId.txt', 'publishedfileid.txt']

_KNOWN_DLCS = [
    'ludeon.rimworld.royalty',
    'ludeon.rimworld.ideology',
    'ludeon.rimworld.biotech',
    'ludeon.rimworld.anomaly',
    'ludeon.rimworld.odyssey',
]


@dataclass
class ModInfo:
    """
    All parsed metadata for a single RimWorld mod.

    Populated by ModInfo.from_path() which reads About.xml directly.
    Dependency fields use the priority system described in the module doc.
    """

    package_id:          str
    name:                str
    author:              str
    description:         str            = ''
    path:                Path           = Path()
    supported_versions:  list[str]      = field(default_factory=list)
    forced_dependencies: list[str]      = field(default_factory=list)
    dependencies:        list[str]      = field(default_factory=list)
    dep_alternatives:    dict[str, list[str]] = field(default_factory=dict)
    load_after:          list[str]      = field(default_factory=list)
    load_before:         list[str]      = field(default_factory=list)
    incompatible_with:   list[str]      = field(default_factory=list)
    load_first:          bool           = False
    load_last:           bool           = False
    source:              str            = 'local'
    workshop_id:         str            = ''
    preview_image:       str            = ''

    @classmethod
    def from_path(cls, mod_path: Path, source: str = 'local',
                  game_version: str = '1.6') -> Optional['ModInfo']:
        """
        Parse About.xml from mod_path and return a ModInfo, or None if absent/invalid.
        """
        about_xml = _find_about_xml(mod_path)
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
        major_version = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else game_version

        dep_alternatives: dict[str, set[str]] = {}

        forced_deps = _parse_li_block(
            root.find('modDependenciesForced'), dep_alternatives)

        deps_by_version = _pick_version_block(
            root.find('modDependenciesByVersion'), game_version, major_version,
            text_only=False)
        base_deps = (set() if deps_by_version
                     else _parse_li_block(
                         root.find('modDependencies'), dep_alternatives))
        resolved_deps = deps_by_version | base_deps

        load_after_by_ver = _pick_version_block(
            root.find('loadAfterByVersion'), game_version, major_version,
            text_only=True)
        load_after = (load_after_by_ver if load_after_by_ver
                      else {x.lower().strip() for x in get_list(root, 'loadAfter')})

        load_before_by_ver = _pick_version_block(
            root.find('loadBeforeByVersion'), game_version, major_version,
            text_only=True)
        load_before = (load_before_by_ver if load_before_by_ver
                       else {x.lower().strip() for x in get_list(root, 'loadBefore')})

        incompat_by_ver = _pick_version_block(
            root.find('incompatibleWithByVersion'), game_version, major_version,
            text_only=True)
        incompatible = (incompat_by_ver if incompat_by_ver
                        else {x.lower().strip()
                              for x in get_list(root, 'incompatibleWith')})

        return cls(
            package_id=package_id,
            name=name,
            author=author,
            description=description,
            path=mod_path,
            supported_versions=versions,
            forced_dependencies=sorted(forced_deps),
            dependencies=sorted(resolved_deps),
            dep_alternatives={k: sorted(v) for k, v in dep_alternatives.items()},
            load_after=sorted(load_after),
            load_before=sorted(load_before),
            incompatible_with=sorted(incompatible),
            load_first='ludeon.rimworld' in load_before,
            load_last=False,
            source=source,
            workshop_id=_read_workshop_id(about_xml, mod_path),
            preview_image=_find_preview(about_xml),
        )


class RimWorldDetector:
    """
    Locates and scans a RimWorld installation.

    Finds the executable, reads the version string, and scans all mod
    directories (game Data/, game Mods/, and extra paths) to build a
    cache of ModInfo objects.
    """

    def __init__(self, game_path: Optional[str] = None):
        self.game_path    = Path(game_path) if game_path else None
        self.exe_path:    Optional[Path] = None
        self.version:     str            = ''
        self._mods_cache: dict[str, ModInfo] = {}
        self._extra_paths: list[str]     = []
        self._cache_time: float          = 0.0

        if self.game_path:
            self._detect_exe()
            self._detect_version()

    def _detect_exe(self) -> None:
        """Find the RimWorld executable inside game_path."""
        if not self.game_path:
            return
        for name in ('RimWorldWin64.exe', 'RimWorldWin.exe', 'RimWorld.exe'):
            c = self.game_path / name
            if c.exists():
                self.exe_path = c
                return

    def _detect_version(self) -> None:
        """Read Version.txt from game_path."""
        if not self.game_path:
            return
        vf = self.game_path / 'Version.txt'
        if vf.exists():
            try:
                self.version = vf.read_text().strip()
            except OSError:
                pass

    def set_game_path(self, path: str) -> None:
        """Update the game path, re-detect exe and version, and clear the mod cache."""
        self.game_path = Path(path)
        self._detect_exe()
        self._detect_version()
        self._mods_cache.clear()
        self._cache_time = 0.0

    def get_game_version_short(self) -> str:
        """Return the game version as 'major.minor', defaulting to '1.6'."""
        if self.version:
            parts = self.version.split('.')
            if len(parts) >= 2:
                return f"{parts[0]}.{parts[1]}"
        return '1.6'

    def get_installed_mods(self, extra_mod_paths: Optional[list[str]] = None,
                           force_rescan: bool = False,
                           max_age_seconds: float = 30.0) -> dict[str, ModInfo]:
        """
        Return all installed mods, using the cache where valid.

        extra_mod_paths, when provided, replaces the stored extra path list.
        force_rescan bypasses the cache unless max_age_seconds has not elapsed.
        """
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

        mods:    dict[str, ModInfo] = {}
        scanned: set[str]           = set()
        game_ver = self.get_game_version_short()

        if self.game_path:
            _scan_mod_dir(self.game_path / 'Data', 'dlc', game_ver, mods, scanned)
            _scan_mod_dir(self.game_path / 'Mods', 'local', game_ver, mods, scanned)

        for ep in self._extra_paths:
            p = Path(ep)
            if p.exists():
                ep_lower = str(p).lower()
                source   = ('workshop'
                            if ('workshop' in ep_lower or 'onyx' in ep_lower)
                            else 'local')
                _scan_mod_dir(p, source, game_ver, mods, scanned)

        self._mods_cache = mods
        self._cache_time = time.monotonic()
        return mods

    def get_detected_dlcs(self) -> list[str]:
        """Return DLC package IDs that are present in the installed mods."""
        mods = self.get_installed_mods()
        return [d for d in _KNOWN_DLCS if d in mods]

    def find_missing_mods(self, mod_ids: list[str]) -> list[str]:
        """Return package IDs from mod_ids that are not installed."""
        installed = self.get_installed_mods()
        return [m for m in mod_ids if m not in installed]


def _find_about_xml(mod_path: Path) -> Optional[Path]:
    for rel in _ABOUT_XML_CANDIDATES:
        c = mod_path / rel
        if c.exists():
            return c
    return None


def _parse_li_block(parent_elem,
                    dep_alternatives: dict[str, set[str]]) -> set[str]:
    """
    Extract lowercased packageId values from <li> children of parent_elem.

    Also populates dep_alternatives for any <alternativePackageIds> found.
    Returns an empty set if parent_elem is None.
    """
    result: set[str] = set()
    if parent_elem is None:
        return result
    for li in parent_elem.findall('li'):
        pid = get_text(li, 'packageId')
        if pid:
            pid_l = pid.lower().strip()
            result.add(pid_l)
            alt_elem = li.find('alternativePackageIds')
            if alt_elem is not None:
                alts: set[str] = set()
                for alt_li in alt_elem.findall('li'):
                    if alt_li.text:
                        alts.add(alt_li.text.lower().strip())
                if alts:
                    dep_alternatives[pid_l] = alts
    return result


def _pick_version_block(parent_elem, game_version: str, major_version: str,
                         text_only: bool = False) -> set[str]:
    """
    Return IDs from the best-matching version-tagged child block of parent_elem.

    Priority: exact game version → major.minor → first major.* match.
    Returns empty set if parent_elem is None or no block matches.
    """
    result: set[str] = set()
    if parent_elem is None:
        return result

    for tag in (f'v{game_version}', f'v{major_version}'):
        ver_elem = parent_elem.find(tag)
        if ver_elem is not None:
            for li in ver_elem.findall('li'):
                val = li.text if text_only else get_text(li, 'packageId')
                if val:
                    result.add(val.lower().strip())
            return result

    major_num = major_version.split('.')[0]
    for child in parent_elem:
        if child.tag.lstrip('v').startswith(major_num):
            for li in child.findall('li'):
                val = li.text if text_only else get_text(li, 'packageId')
                if val:
                    result.add(val.lower().strip())
            break
    return result


def _find_preview(about_xml: Path) -> str:
    """Return the path of the first preview image found, or ''."""
    for name in _PREVIEW_NAMES:
        pp = about_xml.parent / name
        if pp.exists():
            return str(pp)
    return ''


def _read_workshop_id(about_xml: Path, mod_path: Path) -> str:
    """
    Return the workshop ID from PublishedFileId.txt, or mod_path.name if numeric.
    Returns '' if neither is available.
    """
    for name in _WORKSHOP_ID_NAMES:
        pid_file = about_xml.parent / name
        if pid_file.exists():
            try:
                return pid_file.read_text().strip()
            except OSError:
                pass
            break
    if mod_path.name.isdigit():
        return mod_path.name
    return ''


def _scan_mod_dir(dirpath: Path, source: str, game_ver: str,
                   mods: dict[str, ModInfo], scanned: set[str]) -> None:
    """
    Scan dirpath for mod subdirectories and add new ModInfo entries to mods.

    Deduplicates by resolved path to avoid scanning the same dir twice.
    Silently skips directories that raise PermissionError.
    """
    resolved = str(dirpath.resolve())
    if not dirpath.exists() or resolved in scanned:
        return
    scanned.add(resolved)
    try:
        for mod_dir in dirpath.iterdir():
            if not mod_dir.is_dir():
                continue
            info = ModInfo.from_path(mod_dir, source=source,
                                     game_version=game_ver)
            if info and info.package_id not in mods:
                mods[info.package_id] = info
    except PermissionError:
        pass
