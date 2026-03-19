"""
Parse RimWorld .rws save file headers without loading the full save.

.rws files are gzip-compressed XML. Only the <meta> block is read —
the <game> block (which can be hundreds of MB) is never decompressed.

Public API
----------
parse_save_header(path)  → SaveHeader | None
compare_save_mods(header, active_ids)  → SaveCompat
"""

import gzip
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

_META_END  = b'</meta>'
_META_START = b'<meta>'
_MAX_BYTES  = 4 * 1024 * 1024   # 4 MB safety cap
_CHUNK_SIZE = 65536
_UTF8_BOM   = b'\xef\xbb\xbf'
_GZIP_MAGIC = b'\x1f\x8b'


class SaveCompat(Enum):
    """Compatibility status between a save file's mod list and the active mod list."""

    COMPATIBLE = 'compatible'   # mod lists match exactly
    CHANGED    = 'changed'      # some mods added/removed
    MISSING    = 'missing'      # mods in save not installed at all
    UNKNOWN    = 'unknown'      # could not parse save


@dataclass
class SaveHeader:
    """Metadata extracted from the <meta> block of a .rws save file."""

    save_name:    str
    game_version: str
    mod_ids:      list[str] = field(default_factory=list)
    mod_names:    list[str] = field(default_factory=list)
    path:         Path      = Path()

    @property
    def mod_count(self) -> int:
        """Number of mods recorded in the save."""
        return len(self.mod_ids)


def parse_save_header(path: Path) -> Optional[SaveHeader]:
    """
    Read only the <meta> section of a .rws save file.

    Streams the data and stops as soon as </meta> is seen
    so the massive <game> block is never decompressed.

    Returns None if the file cannot be read or parsed.
    """
    try:
        raw = _read_meta_bytes(path)
        if raw is None:
            return None

        root      = ET.fromstring(raw)
        version   = _text(root, 'gameVersion', '')
        mod_ids   = [li.text.strip() for li in _find_list(root, 'modIds')
                     if li.text]
        mod_names = [li.text.strip() for li in _find_list(root, 'modNames')
                     if li.text]

        return SaveHeader(
            save_name=path.stem,
            game_version=version,
            mod_ids=mod_ids,
            mod_names=mod_names,
            path=path,
        )
    except ET.ParseError:
        return None


def compare_save_mods(header: SaveHeader,
                      active_ids: list[str],
                      all_mod_ids: set[str]) -> SaveCompat:
    """
    Compare the mod list recorded in *header* against the currently active list.

    Parameters
    ----------
    header      : SaveHeader from parse_save_header()
    active_ids  : ordered list of currently active mod IDs
    all_mod_ids : set of ALL installed mod IDs (for missing detection)
    """
    if not header.mod_ids:
        return SaveCompat.UNKNOWN

    save_set   = {m.lower() for m in header.mod_ids}
    active_set = {m.lower() for m in active_ids}

    if save_set - all_mod_ids:
        return SaveCompat.MISSING

    if save_set != active_set:
        return SaveCompat.CHANGED

    return SaveCompat.COMPATIBLE


def diff_save_mods(header: SaveHeader,
                   active_ids: list[str]) -> dict[str, list[str]]:
    """
    Return a detailed diff between save mods and active mods.

    Returns
    -------
    {
      'added':   mods active now but NOT in the save,
      'removed': mods in the save but NOT active now,
    }
    """
    save_set   = {m.lower() for m in header.mod_ids}
    active_set = {m.lower() for m in active_ids}
    return {
        'added':   sorted(active_set - save_set),
        'removed': sorted(save_set   - active_set),
    }


def _read_meta_bytes(path: Path) -> Optional[bytes]:
    """
    Stream a .rws save file and return the raw <meta>...</meta> bytes.

    Supports gzip-compressed (RimWorld 1.5 and earlier) and plain UTF-8
    (RimWorld 1.6+) formats. Strips a UTF-8 BOM if present.
    Returns None on any read or format error.
    """
    try:
        raw_header = path.read_bytes()[:3]
    except OSError:
        return None

    is_gzip = raw_header[:2] == _GZIP_MAGIC

    try:
        buf = bytearray()
        if is_gzip:
            with gzip.open(str(path), 'rb') as gz:
                while len(buf) < _MAX_BYTES:
                    chunk = gz.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    buf.extend(chunk)
                    if _META_END in buf:
                        break
        else:
            with open(str(path), 'rb') as f:
                while len(buf) < _MAX_BYTES:
                    chunk = f.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    buf.extend(chunk)
                    if _META_END in buf:
                        break
    except (gzip.BadGzipFile, OSError, EOFError):
        return None

    if not buf:
        return None

    data = bytes(buf)
    if data.startswith(_UTF8_BOM):
        data = data[3:]

    end_idx = data.find(_META_END)
    if end_idx == -1:
        return None

    start_idx = data.find(_META_START)
    if start_idx == -1:
        return None

    return data[start_idx: end_idx + len(_META_END)]


def _text(element: ET.Element, tag: str, default: str = '') -> str:
    child = element.find(tag)
    return child.text.strip() if child is not None and child.text else default


def _find_list(element: ET.Element, tag: str):
    parent = element.find(tag)
    return parent.findall('li') if parent is not None else []
