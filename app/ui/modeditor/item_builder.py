"""Item creation and badge logic for the mod editor."""

from PyQt6.QtCore import Qt  # pylint: disable=no-name-in-module

from app.core.app_settings import AppSettings
from app.ui.styles import get_colors
from app.ui.modeditor.drag_list import ModItem, COLOR_ROLE, TEXT_ROLE, NEW_ROLE
from app.ui.modeditor.issue_checker import get_badges, check_version


def _get_color(key: str) -> str:
    return get_colors(AppSettings.instance().theme)[key]


_SEVERITY_RANK = {
    'error':       0,
    'dep':         1,
    'warning':     2,
    'order':       3,
    'performance': 4,
    'info':        5,
}


class ItemBuilder:
    """Mixin for ModEditorDialog.

    Host class must expose:
        self.inst, self.all_mods, self.names,
        self.active, self.avail,
        self._original_mods, self._known_mod_ids
    """

    # pylint: disable=no-member

    def _game_version(self) -> str:
        return self.inst.rimworld_version or ''

    def _badge_color(self, badges: list) -> str:
        if not badges:
            return _get_color('item_normal')
        worst = min(badges, key=lambda b: _SEVERITY_RANK.get(b[2], 99))
        return worst[1]

    def _make_item(self, label: str, mid: str, color: str,
                   tooltip: str, is_new: bool = False) -> ModItem:
        return ModItem(text=label, mid=mid, color=color,
                       tooltip=tooltip, is_new=is_new)

    def _build_label(self, name: str, mid: str, is_core: bool = False) -> str:
        label = f"{name}  [{mid}]"
        if is_core:
            label = f"[C] {label}"
        return label

    def _mk_active(self, mid: str, skip_badges: bool = False):
        name    = self.names.get(mid, mid)
        is_new  = mid not in self._original_mods
        is_core = mid.lower() == 'ludeon.rimworld'
        label   = self._build_label(name, mid, is_core)

        if skip_badges:
            color = _get_color('accent') if is_new else _get_color('item_normal')
            self.active.addItem(self._make_item(label, mid, color, '', is_new))
            return

        order        = self.active.get_ids() + [mid]
        active_ids   = set(order)
        ignored_deps = set(self.inst.ignored_deps)
        badges       = get_badges(mid, self.all_mods, active_ids,
                                  self._game_version(), order,
                                  ignored_deps=ignored_deps)

        if not self.all_mods.get(mid):
            color, tip = _get_color('error'), "Not on disk"
        elif badges:
            color = self._badge_color(badges)
            tip   = '\n'.join(b[3] for b in badges)
        elif is_new:
            color, tip = _get_color('accent'), "Newly added to this instance"
        else:
            color, tip = _get_color('item_normal'), ''

        self.active.addItem(self._make_item(label, mid, color, tip, is_new))

    def _batch_load_active(self, mod_ids: list):
        """Load all active mods without per-item badge computation, then refresh."""
        self.active.setUpdatesEnabled(False)
        for mid in mod_ids:
            self._mk_active(mid, skip_badges=True)
        self._refresh_badges()
        self.active.setUpdatesEnabled(True)
        self.active.apply_item_widgets()

    def _refresh_badges(self):
        """Recompute badges for every item in the active list in one pass.

        Updates color, tooltip, and is_new on each ModItem directly,
        then emits dataChanged so the delegate repaints.
        """
        order          = self.active.get_ids()
        active_ids     = set(order)
        _pos           = {m: i for i, m in enumerate(order)}
        ignored_deps   = set(self.inst.ignored_deps)
        ignored_errors = set(self.inst.ignored_errors)

        for i in range(self.active.count()):
            it = self.active.item(i)
            if it is None or not it.mid:
                continue

            mid     = it.mid
            is_new  = mid not in self._original_mods
            is_core = mid.lower() == 'ludeon.rimworld'
            label   = self._build_label(self.names.get(mid, mid), mid, is_core)

            badges = get_badges(mid, self.all_mods, active_ids,
                                self._game_version(), order, _pos,
                                ignored_deps=ignored_deps,
                                ignored_errors=ignored_errors)

            if not self.all_mods.get(mid):
                color, tip = _get_color('error'), "Not on disk"
            elif badges:
                color = self._badge_color(badges)
                tip   = '\n'.join(b[3] for b in badges)
            elif is_new:
                color, tip = _get_color('accent'), "Newly added to this instance"
            else:
                color, tip = _get_color('item_normal'), ''

            it.text    = label
            it.color   = color
            it.tooltip = tip
            it.is_new  = is_new

            # pylint: disable=protected-access
            index = self.active._model.index(i)
            self.active._model.dataChanged.emit(
                index, index,
                [COLOR_ROLE, TEXT_ROLE, NEW_ROLE, Qt.ItemDataRole.ToolTipRole])
            # pylint: enable=protected-access

    def _mk_avail(self, mid: str, info):
        """Build and add an available-list item for *mid*."""
        src   = {'dlc': '[DLC]', 'workshop': '[WS]',
                 'local': '[L]'}.get(info.source, '')
        label = f"{src} {info.name}  [{mid}]".strip()

        ver_ok = check_version(info, self._game_version())
        is_new = mid not in self._known_mod_ids

        if not ver_ok:
            color = _get_color('warning')
            tip   = f"Supports: {', '.join(info.supported_versions)}"
        elif is_new:
            color = _get_color('accent')
            tip   = "New mod — not yet used in any instance"
        else:
            color = _get_color('item_normal')
            tip   = ''

        self.avail.addItem(self._make_item(label, mid, color, tip, is_new))

    def _mk_avail_missing(self, mid: str):
        """Build and add an error item for a mod that is in the instance but not on disk."""
        label = f"❌ {mid}  [not on disk]"
        tip   = "This mod is in the instance but not found on disk"
        self.avail.addItem(
            self._make_item(label, mid, _get_color('error'), tip, False))

    # pylint: enable=no-member
