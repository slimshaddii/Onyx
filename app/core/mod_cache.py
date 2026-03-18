"""
Mod cache and 'what's new' tracking.
Stores known mod IDs to detect newly added mods.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional


class ModCache:
    """Tracks known mods across sessions for 'what's new' detection."""
    
    def __init__(self, data_root: Path):
        self.cache_path = data_root / 'mod_cache.json'
        self._known_mods: dict[str, dict] = {}  # mod_id -> {first_seen, name, source}
        self._instance_mods: set[str] = set()    # mods used in any instance
        self._session_new: set[str] = set()      # new mods detected this session
        self._load()
    
    def _load(self):
        if self.cache_path.exists():
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._known_mods = data.get('known_mods', {})
                self._instance_mods = set(data.get('instance_mods', []))
            except (json.JSONDecodeError, KeyError):
                self._known_mods = {}
                self._instance_mods = set()
    
    def save(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'known_mods': self._known_mods,
            'instance_mods': list(self._instance_mods),
            'last_updated': datetime.now().isoformat(),
        }
        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def update_from_scan(self, installed_mods: dict) -> list[str]:
        """
        Update cache with scan results.
        Returns list of NEW mod IDs (not seen before).
        """
        new_mods = []
        now = datetime.now().isoformat()
        
        for mod_id, info in installed_mods.items():
            if mod_id not in self._known_mods:
                new_mods.append(mod_id)
                self._session_new.add(mod_id)
                self._known_mods[mod_id] = {
                    'first_seen': now,
                    'name': info.name,
                    'source': info.source,
                }
            else:
                # Update name in case it changed
                self._known_mods[mod_id]['name'] = info.name
        
        if new_mods:
            self.save()
        
        return new_mods
    
    def update_instance_mods(self, instances: list):
        """Update which mods are used in any instance. Pass list[Instance]."""
        self._instance_mods = {
            mid
            for inst in instances
            for mid in inst.all_mods
        }
        self.save()
    
    def is_new(self, mod_id: str) -> bool:
        """True if mod was added in the current session."""
        return mod_id in self._session_new
    
    def is_unassigned(self, mod_id: str) -> bool:
        """True if mod is not used in any instance."""
        return mod_id not in self._instance_mods
    
    def get_known_mod_ids(self) -> set[str]:
        """All mod IDs we've ever seen."""
        return set(self._known_mods.keys())
    
    def get_instance_mod_ids(self) -> set[str]:
        """All mod IDs used in at least one instance."""
        return set(self._instance_mods)
    
    def clear_new_flags(self):
        """Mark all current mods as 'known' (clear new status)."""
        self._session_new.clear()