"""
Conflict and performance database loader.

Reads data/known_conflicts.json (converted from JuMLi RON data).
Provides fast lookup by package_id or workshop_id.

Notice types
------------
'unstable'     → orange  #ff8800  — stability issues, crashes
'performance'  → yellow  #ffaa00  — TPS/FPS impact
'alternative'  → orange  #ff8800  — better mod exists
'info'         → grey    #888888  — settings advice, notes
'incompatible' → red     #ff4444  — declared incompatibleWith (from About.xml)
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'known_conflicts.json'


@dataclass
class ConflictNotice:
    """A single notice attached to a mod — type, human-readable message, certainty."""

    notice_type: str
    message:     str
    certainty:   str


@dataclass
class ConflictRecord:
    """All notices for one mod, indexed by package_ids and workshop_ids."""

    package_ids:  list[str]
    workshop_ids: list[int]
    notices:      list[ConflictNotice]


class ConflictDB:
    """
    Singleton-style loader for the JuMLi conflict/performance database.

    Call ConflictDB.instance() to get the shared loaded database.
    Call ConflictDB.reload() to force a fresh load after updating the JSON.
    """

    _instance: Optional['ConflictDB'] = None

    def __init__(self):
        self._by_package:  dict[str, ConflictRecord] = {}
        self._by_workshop: dict[str, ConflictRecord] = {}
        self._load()

    @classmethod
    def instance(cls) -> 'ConflictDB':
        """Return the shared ConflictDB, loading on first access."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reload(cls) -> None:
        """Force a fresh load from disk."""
        cls._instance = cls()

    # ── Public API ────────────────────────────────────────────────────────

    def get_notices(self, package_id: str,
                    workshop_id: str = '') -> list[ConflictNotice]:
        """
        Return all notices for a mod.

        Matches by package_id first, then workshop_id as fallback.
        """
        rec = self._by_package.get(package_id.lower().strip())
        if rec is None and workshop_id:
            rec = self._by_workshop.get(workshop_id.strip())
        return rec.notices if rec else []

    def has_notices(self, package_id: str,
                    workshop_id: str = '') -> bool:
        """Return True if any notices exist for the given mod."""
        return bool(self.get_notices(package_id, workshop_id))

    # ── Internals ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Parse known_conflicts.json and populate lookup dicts."""
        if not _DB_PATH.exists():
            return
        try:
            with open(_DB_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        if not isinstance(data, dict):
            return

        for entry in data.get('records', []):
            if not isinstance(entry, dict):
                continue
            notices = [
                ConflictNotice(
                    notice_type=n.get('type', 'info'),
                    message=n.get('message', ''),
                    certainty=n.get('certainty', 'high'),
                )
                for n in entry.get('notices', [])
                if isinstance(n, dict)
            ]
            rec = ConflictRecord(
                package_ids=entry.get('package_ids', []),
                workshop_ids=entry.get('workshop_ids', []),
                notices=notices,
            )
            for pid in rec.package_ids:
                self._by_package[pid.lower().strip()] = rec
            for wid in rec.workshop_ids:
                self._by_workshop[str(wid).strip()] = rec
