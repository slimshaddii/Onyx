"""
Item creation and badge logic for the mod editor.
Separated from dialog.py to keep each file focused.
"""

from PyQt6.QtWidgets import QListWidgetItem
from PyQt6.QtCore import Qt

from app.ui.modeditor.drag_list import COLOR_ROLE, TEXT_ROLE
from app.ui.modeditor.issue_checker import get_badges, check_version

# ── Color constants ───────────────────────────────────────────────────────────
COLOR_ERROR   = '#ff4444'   # Red    — not on disk / hard error
COLOR_WARNING = '#ffaa00'   # Yellow — version mismatch / dep not active
COLOR_ORDER   = '#74d4cc'   # Teal   — load-order violation
COLOR_NEW     = '#74d4cc'   # Teal   — newly added to this instance
COLOR_NORMAL  = '#e0e0e0'   # White  — no issues


class ItemBuilder:
    """
    Mixin that owns all QListWidgetItem creation for ModEditorDialog.

    Host class must expose:
        self.inst             — Instance
        self.all_mods         — dict[str, ModInfo]
        self.names            — dict[str, str]
        self.active           — DragDropList
        self.avail            — DragDropList
        self._original_mods   — set[str]  (mods already saved in this instance)
        self._known_mod_ids   — set[str]  (mods used in any instance)
    """

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _game_version(self) -> str:
        return self.inst.rimworld_version or ''

    def _badge_color(self, badges: list) -> str:
        """Return hex color for the highest-severity badge."""
        if not badges:
            return COLOR_NORMAL
        worst = min(badges,
                    key=lambda b: {'error': 0, 'warning': 1, 'order': 2}.get(b[2], 3))
        return worst[1]

    def _make_item(self, label: str, mid: str,
                   color: str, tooltip: str) -> QListWidgetItem:
        """
        Build a QListWidgetItem with three custom data roles:
          UserRole  → mod package-id          (used by get_ids, drag-drop)
          COLOR_ROLE → hex color string        (read by apply_item_widgets)
          TEXT_ROLE  → display text            (read by filter_text + snapshot
                                                after setText('') clears item.text())
        """
        it = QListWidgetItem(label)
        it.setData(Qt.ItemDataRole.UserRole, mid)
        it.setData(COLOR_ROLE, color)
        it.setData(TEXT_ROLE,  label)   # mirrors the label
        it.setToolTip(tooltip)
        return it

    # ── Active list ───────────────────────────────────────────────────────────

    def _mk_active(self, mid: str, skip_badges: bool = False):
        """
        Append one mod to the active list.

        skip_badges=True  — fast path for batch loading.
          Caller MUST call _refresh_badges() then active.apply_item_widgets().

        skip_badges=False — computes badges inline; call apply_item_widgets()
          on the list when convenient (e.g. after a single activation).
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
        # Always prepend [NEW] when applicable, regardless of badge presence
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
        Updates TEXT_ROLE and COLOR_ROLE.
        Caller must invoke active.apply_item_widgets() afterwards to
        push the changes into the visible QLabel widgets.
        """
        order      = self.active.get_ids()
        active_ids = set(order)

        for i in range(self.active.count()):
            it  = self.active.item(i)
            mid = it.data(Qt.ItemDataRole.UserRole)
            if not mid:
                continue

            name   = self.names.get(mid, mid)
            is_new = mid not in self._original_mods
            badges = get_badges(mid, self.all_mods, active_ids,
                                self._game_version(), order)

            # ── Label ────────────────────────────────────────────────────────
            prefix = ''.join(b[0] for b in badges)
            # FIX: was "if is_new and not badges" — dropped [NEW] when badges existed.
            # Now always prepend [NEW] when is_new, regardless of badge count.
            if is_new:
                prefix = f"[NEW] {prefix}" if prefix else "[NEW]"

            label = f"{prefix} {name}  [{mid}]" if prefix else f"{name}  [{mid}]"
            if mid.lower() == 'ludeon.rimworld':
                label = f"[C] {label}"

            # ── Color + tooltip ───────────────────────────────────────────────
            if not self.all_mods.get(mid):
                color, tip = COLOR_ERROR, "Not on disk"
            elif badges:
                color = self._badge_color(badges)
                tip   = '\n'.join(b[3] for b in badges)
            elif is_new:
                color, tip = COLOR_NEW, "Newly added to this instance"
            else:
                color, tip = COLOR_NORMAL, ''

            # Write TEXT_ROLE first — apply_item_widgets reads this after
            # setText('') has cleared item.text().
            it.setData(TEXT_ROLE,  label)
            it.setData(COLOR_ROLE, color)
            it.setToolTip(tip)
            # Keep item.text() in sync so the narrow window between
            # _refresh_badges and apply_item_widgets stays correct.
            it.setText(label)

    # ── Available list ────────────────────────────────────────────────────────

    def _mk_avail(self, mid: str, info):
        """Append one mod to the available (inactive) list."""
        src    = {'dlc': '[DLC]', 'workshop': '[WS]',
                  'local': '[L]'}.get(info.source, '')
        ver_ok = check_version(info, self._game_version())
        is_new = mid not in self._known_mod_ids

        if not ver_ok:
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
        self.avail.addItem(self._make_item(label, mid, '#ff6b6b', tip))