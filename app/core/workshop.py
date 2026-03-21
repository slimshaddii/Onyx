"""
Steam Workshop API.
All network calls happen either in QThreads or synchronously
with try/except. Numeric fields are always coerced to int.
"""

from dataclasses import dataclass
import json
from typing import Optional

from PyQt6.QtCore import (  # pylint: disable=no-name-in-module
    QThread, pyqtSignal,
)
import requests

_STEAM_FILE_DETAILS_URL = (
    'https://api.steampowered.com/'
    'ISteamRemoteStorage/GetPublishedFileDetails/v1/'
)
_STEAM_QUERY_FILES_URL = (
    'https://api.steampowered.com/'
    'IPublishedFileService/QueryFiles/v1/'
)
_RIMWORLD_APP_ID = 294100

POPULAR_IDS = [
    '2009463077', '1874644848', '818773962',
    '2573814850', '1561769193', '2023507013',
    '1702143502', '2266773437', '1541721856',
    '1531299628', '2451324814', '2571189146',
    '1545126946', '1909914131', '735106432',
    '2025785084', '1845154007', '2559553540',
    '2679126949', '2023513450', '761421485',
    '1180826516', '1847735914', '1603027969',
    '2017032620', '1631756268', '2559644849',
]


@dataclass
class WorkshopItem:
    """A single Steam Workshop item with metadata."""

    workshop_id:   str  = ''
    title:         str  = ''
    description:   str  = ''
    author:        str  = ''
    preview_url:   str  = ''
    subscriptions: int  = 0
    favorites:     int  = 0
    file_size:     int  = 0
    time_updated:  int  = 0
    time_created:  int  = 0
    tags:          list = None
    is_installed:  bool = False

    def __post_init__(self):
        """Normalise tags and coerce numeric fields."""
        if self.tags is None:
            self.tags = []
        for attr in (
                'file_size', 'subscriptions',
                'favorites', 'time_updated',
                'time_created'):
            try:
                setattr(self, attr,
                        int(getattr(self, attr)
                            or 0))
            except (ValueError, TypeError):
                setattr(self, attr, 0)

    @property
    def size_mb(self) -> float:
        """File size in megabytes."""
        try:
            if self.file_size:
                return (int(self.file_size)
                        / (1024 * 1024))
            return 0.0
        except (ValueError, TypeError):
            return 0.0

    @property
    def subs_short(self) -> str:
        """Subscription count as short string."""
        n = self.subscriptions
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}k"
        return str(n) if n else ""

    @property
    def workshop_url(self) -> str:
        """Full URL to this item's Workshop page."""
        return (
            "https://steamcommunity.com/"
            "sharedfiles/filedetails/"
            f"?id={self.workshop_id}"
        )


def _safe_int(val, default: int = 0) -> int:
    try:
        return int(val) if val else default
    except (ValueError, TypeError):
        return default


def fetch_details_sync(
        ids: list[str],
        installed_ids: Optional[set] = None,
) -> list[WorkshopItem]:
    """Fetch Workshop item details synchronously (batched)."""
    if not ids:
        return []
    installed_ids = installed_ids or set()
    all_items: list[WorkshopItem] = []

    for start in range(0, len(ids), 50):
        chunk     = ids[start:start + 50]
        post_data = {'itemcount': len(chunk)}
        for i, wid in enumerate(chunk):
            post_data[
                f'publishedfileids[{i}]'] = wid

        try:
            resp = requests.post(
                _STEAM_FILE_DETAILS_URL,
                data=post_data, timeout=15)
            resp.raise_for_status()
            details = (
                resp.json()
                .get('response', {})
                .get('publishedfiledetails', []))
            for d in details:
                if _safe_int(
                        d.get('result')) != 1:
                    continue
                wid = str(
                    d.get('publishedfileid', ''))
                all_items.append(WorkshopItem(
                    workshop_id=wid,
                    title=d.get('title', '?'),
                    description=str(
                        d.get('description', '')
                    )[:1000],
                    preview_url=d.get(
                        'preview_url', ''),
                    subscriptions=_safe_int(
                        d.get('subscriptions')),
                    favorites=_safe_int(
                        d.get('favorited')),
                    file_size=_safe_int(
                        d.get('file_size')),
                    time_updated=_safe_int(
                        d.get('time_updated')),
                    tags=[
                        t.get('tag', '')
                        for t in d.get('tags', [])
                    ],
                    is_installed=(
                        wid in installed_ids),
                ))
        except (
            requests.RequestException,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            print(
                "[Workshop] fetch_details_sync"
                f" error: {exc}")
            continue

    return all_items


def search_with_api_sync(
        query: str, api_key: str,
        sort_type: int = 12,
        per_page: int = 30,
        installed_ids: Optional[set] = None,
) -> list[WorkshopItem]:
    """Search Workshop via API key synchronously."""
    installed_ids = installed_ids or set()
    params = {
        'key':                      api_key,
        'query_type':               sort_type,
        'page':                     1,
        'numperpage':               per_page,
        'appid':                    _RIMWORLD_APP_ID,
        'search_text':              query,
        'return_tags':              True,
        'return_previews':          True,
        'return_short_description': True,
        'strip_description_bbcode': True,
    }
    try:
        resp = requests.get(
            _STEAM_QUERY_FILES_URL,
            params=params, timeout=15)
        resp.raise_for_status()
        items: list[WorkshopItem] = []
        pf_details = (
            resp.json()
            .get('response', {})
            .get('publishedfiledetails', []))
        for fd in pf_details:
            preview = ''
            for p in fd.get('previews', []):
                if _safe_int(
                        p.get('preview_type')
                ) == 0:
                    preview = p.get('url', '')
                    break
            wid = str(
                fd.get('publishedfileid', ''))
            items.append(WorkshopItem(
                workshop_id=wid,
                title=fd.get('title', '?'),
                description=fd.get(
                    'short_description', ''
                )[:500],
                preview_url=preview,
                subscriptions=_safe_int(
                    fd.get('subscriptions')),
                favorites=_safe_int(
                    fd.get('favorited')),
                file_size=_safe_int(
                    fd.get('file_size')),
                time_updated=_safe_int(
                    fd.get('time_updated')),
                tags=[
                    t.get('tag', '')
                    for t in fd.get('tags', [])
                ],
                is_installed=(
                    wid in installed_ids),
            ))
        return items
    except (
        requests.RequestException,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        print(
            "[Workshop] API search"
            f" error: {exc}")
        return []


class WorkshopSearchThread(QThread):
    """
    QThread that searches the Steam Workshop and emits results.

    Uses API key search if available, otherwise falls back
    to fetching the popular mods list.
    """

    results_ready = pyqtSignal(list)
    error_signal  = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    SORT_MAP = {
        'trend':         12,
        'recent':         1,
        'subscriptions':  4,
        'favorites':      7,
        'last_updated':  21,
    }

    def __init__(self, query: str = '',
                 api_key: str = '',
                 per_page: int = 30,
                 sort: str = 'trend',
                 installed_ids=None):
        super().__init__()
        self.query         = query
        self.api_key       = api_key
        self.per_page      = per_page
        self.sort          = sort
        self.installed_ids = installed_ids or set()
        self._cancelled    = False

    def cancel(self) -> None:
        """Request cancellation before results are emitted."""
        self._cancelled = True

    def run(self) -> None:
        """Execute the Workshop search on the background thread."""
        if self._cancelled:
            return
        try:
            if self.api_key:
                self.status_signal.emit(
                    "Searching…")
                items = search_with_api_sync(
                    self.query, self.api_key,
                    self.SORT_MAP.get(
                        self.sort, 12),
                    self.per_page,
                    self.installed_ids)
            else:
                if self.query:
                    self.status_signal.emit(
                        "Text search needs API "
                        "key. Showing popular "
                        "mods.")
                else:
                    self.status_signal.emit(
                        "Loading popular mods…")
                items = fetch_details_sync(
                    POPULAR_IDS,
                    self.installed_ids)

            if not self._cancelled:
                self.results_ready.emit(items)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # QThread.run must not propagate
            if not self._cancelled:
                self.error_signal.emit(str(exc))


class WorkshopDetailThread(QThread):
    """QThread that fetches full details for specific Workshop IDs."""

    detail_ready = pyqtSignal(list)
    error_signal = pyqtSignal(str)

    def __init__(self, ids: list[str],
                 installed_ids=None):
        super().__init__()
        self.ids           = ids
        self.installed_ids = installed_ids or set()

    def run(self) -> None:
        """Fetch details and emit the result list."""
        try:
            self.detail_ready.emit(
                fetch_details_sync(
                    self.ids,
                    self.installed_ids))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # QThread.run must not propagate
            self.error_signal.emit(str(exc))
