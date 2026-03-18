"""
Item creation and badge logic for the mod editor.
Separated from dialog.py to keep each file focused.
"""

from PyQt6.QtWidgets import QListWidgetItem
from PyQt6.QtCore import Qt

from app.ui.modeditor.drag_list import COLOR_ROLE, TEXT_ROLE
from app.ui.modeditor.issue_checker import get_badges, check_version

# ── Color constants ───────────────────────────────────────────────────────────
# Must stay in sync with issue_checker.py's palette.
COLOR_ERROR      = '#ff4444'   # Red    — not on disk / hard missing dep
COLOR_DEPENDENCY = '#ff8800'   # Orange — dep not active (on disk)
COLOR_WARNING    = '#ff8800'   # Orange — version mismatch (same visual tier)
COLOR_ORDER      = '#ffaa00'   # Yellow — load-order violation
COLOR_NEW        = '#74d4cc'   # Teal   — newly added to this instance
COLOR_NORMAL     = '#e0e0e0'   # White  — no issues


# ── Severity ranking used by _badge_color ─────────────────────────────────────
# Lower number = higher priority = wins when multiple badges are present.
_SEVERITY_RANK = {
    'error':   0,   # red
    'dep':     1,   # orange — dep on disk, not active
    'warning': 2,   # orange — version mismatch
    'order':   3,   # yellow — load-order violation
}


class ItemBuilder:
    """
    Mixin that owns all QListWidgetItem creation for ModEditorDialog.

    Host class must expose:
        self.inst             — Instance
        self.all_mods         — dict[str, ModInfo]
        self.names            — dict[str, str]
        self.active           — DragDropList
        self.avail            — DragDropList
        self._original_mods   — set[str]
        self._known_mod_ids   — set[str]
    """

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _game_version(self) -> str:
        return self.inst.rimworld_version or ''

    def _badge_color(self, badges: list) -> str:
        """
        Return the hex color for the highest-severity badge in the list.

        Priority (low rank number wins):
            0 error   → red    #ff4444
            1 dep     → orange #ff8800
            2 warning → orange #ff8800
            3 order   → yellow #ffaa00
        """
        if not badges:
            return COLOR_NORMAL
        worst = min(badges, key=lambda b: _SEVERITY_RANK.get(b[2], 99))
        return worst[1]   # color stored in tuple position 1

    def _make_item(self, label: str, mid: str,
                   color: str, tooltip: str) -> QListWidgetItem:
        """
        Build a QListWidgetItem with three custom data roles:
          UserRole   → mod package-id
          COLOR_ROLE → hex color string  (read by apply_item_widgets)
          TEXT_ROLE  → display text      (survives setText(''))
        """
        it = QListWidgetItem(label)
        it.setData(Qt.ItemDataRole.UserRole, mid)
        it.setData(COLOR_ROLE, color)
        it.setData(TEXT_ROLE,  label)
        it.setToolTip(tooltip)
        return it

    # ── Active list ───────────────────────────────────────────────────────────

    def _mk_active(self, mid: str, skip_badges: bool = False):
        """
        Append one mod to the active list.

        skip_badges=True  — fast path for batch loading.
            Caller MUST call _refresh_badges() then active.apply_item_widgets().
        skip_badges=False — computes badges inline.
        """
        name   = self.names.get(mid, mid)
        is_new = mid not in self._original_mods

        if skip_badges:
            label = f"[NEW] {name}  [{mid}]" if is_new else f"{name}  [{mid}]"
            if mid.lower() == 'ludeon.rimworld':
                label = f"[C] {label}"
            self.active.addItem(
                self._make_item(label, mid,
                                COLOR_NEW if is_new else COLOR_NORMAL, ''))
            return

        # ── Full path — compute badges now ───────────────────────────────────
        order      = self.active.get_ids() + [mid]
        active_ids = set(order)
        badges     = get_badges(mid, self.all_mods, active_ids,
                                self._game_version(), order)

        prefix = ''.join(b[0] for b in badges)
        if is_new:
            prefix = f"[NEW] {prefix}" if prefix else "[NEW]"

        label = f"{prefix} {name}  [{mid}]" if prefix else f"{name}  [{mid}]"
        if mid.lower() == 'ludeon.rimworld':
            label = f"[C] {label}"

        if not self.all_mods.get(mid):
            color, tip = COLOR_ERROR, "Not on disk"
        elif badges:
            color = self._badge_color(badges)
            tip   = '\n'.join(b[3] for b in badges)
        elif is_new:
            color, tip = COLOR_NEW, "Newly added to this instance"
        else:
            color, tip = COLOR_NORMAL, ''

        self.active.addItem(self._make_item(label, mid, color, tip))

    def _batch_load_active(self, mod_ids: list):
        """
        Load a full list of mods into the active panel.
        Uses skip_badges for speed, then computes all badges in one pass.
        """
        self.active.setUpdatesEnabled(False)
        for mid in mod_ids:
            self._mk_active(mid, skip_badges=True)
        self.active.setUpdatesEnabled(True)

        self._refresh_badges()
        self.active.apply_item_widgets()

    def _refresh_badges(self):
        """
        Recompute badges for every item in the active list in one pass.

        Color assignment per severity
        ──────────────────────────────
        error   → red    #ff4444   (not on disk, hard missing dep)
        dep     → orange #ff8800   (dep on disk, not active)
        warning → orange #ff8800   (version mismatch)
        order   → yellow #ffaa00   (load-order violation)
        new     → teal   #74d4cc   (newly added, no issues)
        normal  → white  #e0e0e0   (no issues, not new)

        Caller must invoke active.apply_item_widgets() afterwards.
        """
        order      = self.active.get_ids()
        active_ids = set(order)
        _pos       = {m: i for i, m in enumerate(order)}

        for i in range(self.active.count()):
            it  = self.active.item(i)
            mid = it.data(Qt.ItemDataRole.UserRole)
            if not mid:
                continue

            name   = self.names.get(mid, mid)
            is_new = mid not in self._original_mods
            badges = get_badges(mid, self.all_mods, active_ids,
                                self._game_version(), order, _pos)

            # ── Label ────────────────────────────────────────────────────────
            prefix = ''.join(b[0] for b in badges)
            if is_new:
                prefix = f"[NEW] {prefix}" if prefix else "[NEW]"

            label = f"{prefix} {name}  [{mid}]" if prefix else f"{name}  [{mid}]"
            if mid.lower() == 'ludeon.rimworld':
                label = f"[C] {label}"

            # ── Color + tooltip ───────────────────────────────────────────────
            if not self.all_mods.get(mid):
                color, tip = COLOR_ERROR, "Not on disk"
            elif badges:
                color = self._badge_color(badges)   # picks worst by _SEVERITY_RANK
                tip   = '\n'.join(b[3] for b in badges)
            elif is_new:
                color, tip = COLOR_NEW, "Newly added to this instance"
            else:
                color, tip = COLOR_NORMAL, ''

            it.setData(TEXT_ROLE,  label)
            it.setData(COLOR_ROLE, color)
            it.setToolTip(tip)
            it.setText(label)

    # ── Available list ────────────────────────────────────────────────────────

    def _mk_avail(self, mid: str, info):
        """Append one mod to the available (inactive) list."""
        src    = {'dlc': '[DLC]', 'workshop': '[WS]',
                  'local': '[L]'}.get(info.source, '')
        ver_ok = check_version(info, self._game_version())
        is_new = mid not in self._known_mod_ids

        if not ver_ok:
            # Version mismatch → orange (same tier as dep warning)
            prefix, color = '[!] ', COLOR_WARNING
            tip = f"Supports: {', '.join(info.supported_versions)}"
        elif is_new:
            prefix, color = '[NEW] ', COLOR_NEW
            tip = "New mod — not yet used in any instance"
        else:
            prefix, color, tip = '', COLOR_NORMAL, ''

        label = f"{prefix}{src} {info.name}  [{mid}]"
        self.avail.addItem(self._make_item(label, mid, color, tip))

    def _mk_avail_missing(self, mid: str):
        """Append a placeholder for a mod that cannot be found on disk."""
        label = f"❌ {mid}  [not on disk]"
        tip   = "This mod is in the instance but not found on disk"
        self.avail.addItem(self._make_item(label, mid, COLOR_ERROR, tip))