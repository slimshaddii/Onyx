"""
Modlist history — timestamped snapshots of an instance's active mod list.

Stored at: <instance_path>/history.json
Each snapshot records the ordered active mod list and a human label.
Max snapshots kept: 50 (older ones are pruned automatically).
"""

import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

MAX_SNAPSHOTS = 50


@dataclass
class Snapshot:
    timestamp: str          # ISO-8601
    label: str              # "Auto-save" or user-supplied label
    mods: list[str]         # ordered active mod IDs
    mod_count: int          # len(mods) — convenience field

    @classmethod
    def from_dict(cls, d: dict) -> 'Snapshot':
        mods = d.get('mods', [])
        return cls(
            timestamp=d.get('timestamp', ''),
            label=d.get('label', 'Auto-save'),
            mods=mods,
            mod_count=d.get('mod_count', len(mods)),
        )

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp,
            'label':     self.label,
            'mods':      self.mods,
            'mod_count': self.mod_count,
        }

    def fmt_date(self) -> str:
        try:
            return datetime.fromisoformat(
                self.timestamp).strftime("%b %d, %Y  %H:%M")
        except (ValueError, TypeError):
            return self.timestamp[:16]


class ModHistory:
    """Read/write history.json for one instance."""

    def __init__(self, instance_path: Path):
        self._path       = instance_path / 'history.json'
        self._snapshots: list[Snapshot] = []
        self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def snapshots(self) -> list[Snapshot]:
        """All snapshots, newest first."""
        return list(self._snapshots)

    def record(self, mods: list[str], label: str = 'Auto-save'):
        """
        Add a new snapshot. Skips recording if the mod list is identical
        to the most recent snapshot (no point storing a no-op save).
        Prunes oldest entries when MAX_SNAPSHOTS is exceeded.
        """
        if self._snapshots and self._snapshots[0].mods == mods:
            return

        snap = Snapshot(
            timestamp=datetime.now().isoformat(),
            label=label,
            mods=list(mods),
            mod_count=len(mods),
        )
        self._snapshots.insert(0, snap)

        if len(self._snapshots) > MAX_SNAPSHOTS:
            self._snapshots = self._snapshots[:MAX_SNAPSHOTS]

        self._save()

    def diff(self, snap_a: Snapshot,
             snap_b: Snapshot) -> dict[str, list[str]]:
        """
        Return mods added and removed going from snap_b → snap_a.

        Returns
        -------
        {
          'added':   mods in snap_a but not snap_b,
          'removed': mods in snap_b but not snap_a,
        }
        """
        set_a = set(snap_a.mods)
        set_b = set(snap_b.mods)
        return {
            'added':   sorted(set_a - set_b),
            'removed': sorted(set_b - set_a),
        }

    def delete(self, index: int):
        """Remove snapshot at position *index* (0 = newest)."""
        if 0 <= index < len(self._snapshots):
            self._snapshots.pop(index)
            self._save()

    def clear(self):
        self._snapshots.clear()
        self._save()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load(self):
        if not self._path.exists():
            return
        try:
            with open(self._path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._snapshots = [
                Snapshot.from_dict(d)
                for d in data.get('snapshots', [])
            ]
        except (json.JSONDecodeError, OSError):
            self._snapshots = []

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix('.json.tmp')
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(
                    {'snapshots': [s.to_dict() for s in self._snapshots]},
                    f, indent=2)
            tmp.replace(self._path)
        except Exception:
            tmp.unlink(missing_ok=True)