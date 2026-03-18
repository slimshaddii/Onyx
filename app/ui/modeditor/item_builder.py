"""
Item creation and badge logic for the mod editor.
"""

from PyQt6.QtWidgets import QListWidgetItem
from PyQt6.QtCore import Qt

from app.ui.modeditor.drag_list import COLOR_ROLE, TEXT_ROLE, NEW_ROLE
from app.ui.modeditor.issue_checker import get_badges, check_version

COLOR_ERROR      = '#ff4444'
COLOR_DEPENDENCY = '#ff8800'
COLOR_WARNING    = '#ff8800'
COLOR_ORDER      = '#ffaa00'
COLOR_NEW        = '#74d4cc'
COLOR_NORMAL     = '#e0e0e0'

_SEVERITY_RANK = {
    'error':       0,
    'dep':         1,
    'warning':     2,
    'order':       3,
    'performance': 4,
    'info':        5,
}


class ItemBuilder:
    """
    Mixin for ModEditorDialog.

    Label format: "ModName  [package.id]"
    No issue icons in the label — the colored dot in apply_item_widgets
    communicates severity. [NEW] pill is rendered separately via NEW_ROLE.
    [C] prefix kept for Core (only structural label we keep).
    """

    def _game_version(self) -> str:
        return self.inst.rimworld_version or ''

    def _badge_color(self, badges: list) -> str:
        if not badges:
            return COLOR_NORMAL
        worst = min(badges, key=lambda b: _SEVERITY_RANK.get(b[2], 99))
        return worst[1]

    def _make_item(self, label: str, mid: str, color: str,
                   tooltip: str, is_new: bool = False) -> QListWidgetItem:
        it = QListWidgetItem(label)
        it.setData(Qt.ItemDataRole.UserRole, mid)
        it.setData(COLOR_ROLE, color)
        it.setData(TEXT_ROLE,  label)
        it.setData(NEW_ROLE,   is_new)
        it.setToolTip(tooltip)
        return it

    def _build_label(self, name: str, mid: str, is_core: bool = False) -> str:
        """
        Build clean label — no issue icons.
        Format: "Name  [mid]"  or  "[C] Name  [mid]" for Core.
        """
        label = f"{name}  [{mid}]"
        if is_core:
            label = f"[C] {label}"
        return label

    # ── Active list ───────────────────────────────────────────────────────────

    def _mk_active(self, mid: str, skip_badges: bool = False):
        name    = self.names.get(mid, mid)
        is_new  = mid not in self._original_mods
        is_core = mid.lower() == 'ludeon.rimworld'
        label   = self._build_label(name, mid, is_core)

        if skip_badges:
            self.active.addItem(
                self._make_item(label, mid,
                                COLOR_NEW if is_new else COLOR_NORMAL,
                                '', is_new))
            return

        order        = self.active.get_ids() + [mid]
        active_ids   = set(order)
        ignored_deps = set(self.inst.ignored_deps)
        badges       = get_badges(mid, self.all_mods, active_ids,
                                  self._game_version(), order,
                                  ignored_deps=ignored_deps)

        if not self.all_mods.get(mid):
            color, tip = COLOR_ERROR, "Not on disk"
        elif badges:
            color = self._badge_color(badges)
            tip   = '\n'.join(b[3] for b in badges)
        elif is_new:
            color, tip = COLOR_NEW, "Newly added to this instance"
        else:
            color, tip = COLOR_NORMAL, ''

        self.active.addItem(
            self._make_item(label, mid, color, tip, is_new))

    def _batch_load_active(self, mod_ids: list):
        self.active.setUpdatesEnabled(False)
        for mid in mod_ids:
            self._mk_active(mid, skip_badges=True)
        self.active.setUpdatesEnabled(True)

        self._refresh_badges()
        self.active.apply_item_widgets()

    def _refresh_badges(self):
        """
        Recompute badges for every item in the active list.
        Updates COLOR_ROLE, TEXT_ROLE, NEW_ROLE.
        Caller must invoke active.apply_item_widgets() afterwards.
        """
        order        = self.active.get_ids()
        active_ids   = set(order)
        _pos         = {m: i for i, m in enumerate(order)}
        ignored_deps = set(self.inst.ignored_deps)

        for i in range(self.active.count()):
            it  = self.active.item(i)
            mid = it.data(Qt.ItemDataRole.UserRole)
            if not mid:
                continue

            name    = self.names.get(mid, mid)
            is_new  = mid not in self._original_mods
            is_core = mid.lower() == 'ludeon.rimworld'
            label   = self._build_label(name, mid, is_core)

            badges = get_badges(mid, self.all_mods, active_ids,
                                self._game_version(), order, _pos,
                                ignored_deps=ignored_deps)

            if not self.all_mods.get(mid):
                color, tip = COLOR_ERROR, "Not on disk"
            elif badges:
                color = self._badge_color(badges)
                tip   = '\n'.join(b[3] for b in badges)
            elif is_new:
                color, tip = COLOR_NEW, "Newly added to this instance"
            else:
                color, tip = COLOR_NORMAL, ''

            it.setData(TEXT_ROLE,  label)
            it.setData(COLOR_ROLE, color)
            it.setData(NEW_ROLE,   is_new)
            it.setToolTip(tip)
            it.setText(label)

    # ── Available list ────────────────────────────────────────────────────────

    def _mk_avail(self, mid: str, info):
        src    = {'dlc': '[DLC]', 'workshop': '[WS]',
                  'local': '[L]'}.get(info.source, '')
        ver_ok = check_version(info, self._game_version())
        is_new = mid not in self._known_mod_ids

        label = f"{src} {info.name}  [{mid}]".strip()

        if not ver_ok:
            color = COLOR_WARNING
            tip   = f"Supports: {', '.join(info.supported_versions)}"
        elif is_new:
            color = COLOR_NEW
            tip   = "New mod — not yet used in any instance"
        else:
            color = COLOR_NORMAL
            tip   = ''

        self.avail.addItem(
            self._make_item(label, mid, color, tip, is_new))

    def _mk_avail_missing(self, mid: str):
        label = f"❌ {mid}  [not on disk]"
        tip   = "This mod is in the instance but not found on disk"
        self.avail.addItem(
            self._make_item(label, mid, COLOR_ERROR, tip, False))