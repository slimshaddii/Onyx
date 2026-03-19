"""
Mod update checker.
Compares local mod timestamps against Steam Workshop time_updated.
Timestamps stored in data_root/mod_timestamps.json.
"""

import json
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class ModUpdateInfo:
    workshop_id:    str
    name:           str
    local_time:     int   # unix timestamp of local version
    remote_time:    int   # unix timestamp from Steam API
    has_update:     bool  # remote_time > local_time
    mod_path:       str = ''


class ModTimestampStore:
    """
    Persists {workshop_id: unix_timestamp} to data_root/mod_timestamps.json.
    Records when a mod was downloaded/updated by Onyx.
    """

    def __init__(self, data_root: Path):
        self._path = data_root / 'mod_timestamps.json'
        self._data: dict[str, int] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._data = json.loads(
                    self._path.read_text(encoding='utf-8'))
            except Exception:
                self._data = {}

    def _save(self):
        try:
            self._path.write_text(
                json.dumps(self._data, indent=2),
                encoding='utf-8')
        except Exception:
            pass

    def record(self, workshop_id: str, timestamp: Optional[int] = None):
        """Record download time for a mod. Uses current time if not specified."""
        self._data[workshop_id] = timestamp or int(time.time())
        self._save()

    def record_batch(self, workshop_ids: list[str],
                     timestamp: Optional[int] = None):
        ts = timestamp or int(time.time())
        for wid in workshop_ids:
            self._data[wid] = ts
        self._save()

    def get(self, workshop_id: str) -> int:
        """Return stored timestamp or 0 if not recorded."""
        return self._data.get(workshop_id, 0)

    def get_all(self) -> dict[str, int]:
        return dict(self._data)

    def remove(self, workshop_id: str):
        self._data.pop(workshop_id, None)
        self._save()


def check_updates(
    workshop_ids: list[str],
    timestamp_store: ModTimestampStore,
    mod_names: Optional[dict[str, str]] = None,
    mod_paths: Optional[dict[str, str]] = None,
) -> list[ModUpdateInfo]:
    """
    Check Steam Workshop for updates to the given workshop IDs.
    Returns list of ModUpdateInfo, one per mod checked.
    Mods not in timestamp_store use mtime of mod_path as fallback.

    Batches requests in groups of 50 (Steam API limit).
    """
    import requests

    mod_names = mod_names or {}
    mod_paths = mod_paths or {}

    if not workshop_ids:
        return []

    url = ('https://api.steampowered.com/'
           'ISteamRemoteStorage/GetPublishedFileDetails/v1/')

    results: list[ModUpdateInfo] = []

    for start in range(0, len(workshop_ids), 50):
        chunk = workshop_ids[start:start + 50]
        post_data = {'itemcount': len(chunk)}
        for i, wid in enumerate(chunk):
            post_data[f'publishedfileids[{i}]'] = wid

        try:
            resp = requests.post(url, data=post_data, timeout=15)
            resp.raise_for_status()
            details = (resp.json()
                       .get('response', {})
                       .get('publishedfiledetails', []))
        except Exception:
            # Network failure — skip this chunk
            continue

        for d in details:
            wid         = str(d.get('publishedfileid', ''))
            result_code = d.get('result', 0)
            if result_code != 1 or not wid:
                continue

            remote_time = int(d.get('time_updated', 0))
            name        = d.get('title') or mod_names.get(wid, wid)

            # Local timestamp: stored record first, then file mtime fallback
            local_time = timestamp_store.get(wid)
            if local_time == 0 and wid in mod_paths:
                try:
                    import os
                    local_time = int(os.path.getmtime(mod_paths[wid]))
                except Exception:
                    local_time = 0

            results.append(ModUpdateInfo(
                workshop_id=wid,
                name=name,
                local_time=local_time,
                remote_time=remote_time,
                has_update=(remote_time > local_time > 0),
                mod_path=mod_paths.get(wid, ''),
            ))

    return results


def get_workshop_file_sizes(
    workshop_ids: list[str],
) -> dict[str, int]:
    """
    Fetch file sizes for workshop IDs from Steam API.
    Returns {workshop_id: size_bytes}.
    Used by download manager for speed/ETA calculation.
    """
    import requests

    if not workshop_ids:
        return {}

    url = ('https://api.steampowered.com/'
           'ISteamRemoteStorage/GetPublishedFileDetails/v1/')
    sizes: dict[str, int] = {}

    for start in range(0, len(workshop_ids), 50):
        chunk = workshop_ids[start:start + 50]
        post_data = {'itemcount': len(chunk)}
        for i, wid in enumerate(chunk):
            post_data[f'publishedfileids[{i}]'] = wid

        try:
            resp = requests.post(url, data=post_data, timeout=15)
            resp.raise_for_status()
            details = (resp.json()
                       .get('response', {})
                       .get('publishedfiledetails', []))
            for d in details:
                wid  = str(d.get('publishedfileid', ''))
                size = int(d.get('file_size', 0))
                if wid and size:
                    sizes[wid] = size
        except Exception:
            continue

    return sizes