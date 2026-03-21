"""
Mod update checker.
Compares local mod timestamps against Steam Workshop time_updated.
Timestamps stored in data_root/mod_timestamps.json.
"""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests


# ── Module-Level Constants ────────────────────────────────────────────────────

_STEAM_FILE_DETAILS_URL = (
    'https://api.steampowered.com/'
    'ISteamRemoteStorage/GetPublishedFileDetails/v1/'
)


# ── ModUpdateInfo ─────────────────────────────────────────────────────────────

@dataclass
class ModUpdateInfo:
    """Update status for a single Workshop mod."""

    workshop_id: str
    name:        str
    local_time:  int
    remote_time: int
    has_update:  bool
    mod_path:    str = ''


# ── ModTimestampStore ─────────────────────────────────────────────────────────

class ModTimestampStore:
    """
    Persists {workshop_id: unix_timestamp} to
    data_root/mod_timestamps.json.

    Records when a mod was downloaded/updated by Onyx.
    """

    def __init__(self, data_root: Path):
        self._path = data_root / 'mod_timestamps.json'
        self._data: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(
                    self._path.read_text(
                        encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._data, indent=2),
                encoding='utf-8')
        except OSError:
            pass

    def record(self, workshop_id: str,
               timestamp: Optional[int] = None,
               ) -> None:
        """Record download time for a mod.

        Uses current time only when timestamp is None.
        An explicit 0 is stored as-is.
        """
        self._data[workshop_id] = (
            int(time.time()) if timestamp is None
            else timestamp
        )
        self._save()

    def record_batch(self, workshop_ids: list[str],
                     timestamp: Optional[int] = None,
                     ) -> None:
        """Record the same timestamp for multiple workshop IDs."""
        ts = (int(time.time()) if timestamp is None
              else timestamp)
        for wid in workshop_ids:
            self._data[wid] = ts
        self._save()

    def get(self, workshop_id: str) -> int:
        """Return stored timestamp or 0 if not recorded."""
        return self._data.get(workshop_id, 0)

    def get_all(self) -> dict[str, int]:
        """Return a copy of all workshop_id to timestamp mappings."""
        return dict(self._data)

    def remove(self, workshop_id: str) -> None:
        """Remove the stored timestamp for a workshop ID."""
        self._data.pop(workshop_id, None)
        self._save()


# ── Public API ────────────────────────────────────────────────────────────────

def check_updates(
    workshop_ids:    list[str],
    timestamp_store: ModTimestampStore,
    mod_names:       Optional[dict[str, str]] = None,
    mod_paths:       Optional[dict[str, str]] = None,
) -> list[ModUpdateInfo]:
    """
    Check Steam Workshop for updates to the given workshop IDs.

    Returns one ModUpdateInfo per mod checked.  Mods not in
    timestamp_store use the mtime of mod_path as a fallback
    local timestamp.  Batches requests in groups of 50
    (Steam API limit).
    """
    if not workshop_ids:
        return []

    mod_names = mod_names or {}
    mod_paths = mod_paths or {}
    results:  list[ModUpdateInfo] = []

    for start in range(0, len(workshop_ids), 50):
        chunk   = workshop_ids[start:start + 50]
        details = _fetch_published_file_details(chunk)

        for d in details:
            wid = str(d.get('publishedfileid', ''))
            result_code = d.get('result', 0)
            if result_code != 1 or not wid:
                continue

            remote_time = int(d.get('time_updated', 0))
            name = (d.get('title')
                    or mod_names.get(wid, wid))
            local_time = _get_local_time(
                wid, timestamp_store, mod_paths)

            results.append(ModUpdateInfo(
                workshop_id=wid,
                name=name,
                local_time=local_time,
                remote_time=remote_time,
                has_update=(
                    remote_time > local_time > 0),
                mod_path=mod_paths.get(wid, ''),
            ))

    return results


def get_workshop_file_sizes(
        workshop_ids: list[str],
) -> dict[str, int]:
    """
    Fetch file sizes for workshop IDs from Steam API.

    Returns {workshop_id: size_bytes}.
    Used by the download manager for speed/ETA calculation.
    Batches requests in groups of 50 (Steam API limit).
    """
    if not workshop_ids:
        return {}

    sizes: dict[str, int] = {}

    for start in range(0, len(workshop_ids), 50):
        chunk   = workshop_ids[start:start + 50]
        details = _fetch_published_file_details(chunk)

        for d in details:
            wid  = str(d.get('publishedfileid', ''))
            size = int(d.get('file_size', 0))
            if wid and size:
                sizes[wid] = size

    return sizes


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _build_post_data(chunk: list[str]) -> dict:
    """Build the POST body for a Steam GetPublishedFileDetails request."""
    data: dict = {'itemcount': len(chunk)}
    for i, wid in enumerate(chunk):
        data[f'publishedfileids[{i}]'] = wid
    return data


def _fetch_published_file_details(
        chunk: list[str],
) -> list[dict]:
    """
    POST one chunk of workshop IDs to the Steam API.

    Returns the publishedfiledetails list, or [] on any
    network or parse error.
    """
    try:
        resp = requests.post(
            _STEAM_FILE_DETAILS_URL,
            data=_build_post_data(chunk),
            timeout=15)
        resp.raise_for_status()
        return (resp.json()
                .get('response', {})
                .get('publishedfiledetails', []))
    except (requests.RequestException,
            json.JSONDecodeError, ValueError):
        return []


def _get_local_time(
        wid: str,
        timestamp_store: ModTimestampStore,
        mod_paths: dict[str, str],
) -> int:
    """
    Return the local timestamp for a workshop mod.

    Uses the stored record first; falls back to the mtime
    of the mod folder if the store has no record and a path
    is available.
    """
    local_time = timestamp_store.get(wid)
    if local_time == 0 and wid in mod_paths:
        try:
            local_time = int(
                os.path.getmtime(mod_paths[wid]))
        except OSError:
            local_time = 0
    return local_time
