"""Launch dialog — configure and fire a RimWorld
instance launch."""

from pathlib import Path

from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QLineEdit, QGroupBox,
    QGridLayout,
)

from app.core.app_settings import AppSettings
from app.core.instance import Instance
from app.core.launcher import Launcher
from app.core.save_parser import (
    parse_save_header, compare_save_mods, SaveCompat,
)
from app.ui.detail.save_compat import (
    COMPAT_ICON, COMPAT_COLOR, COMPAT_LABEL,
)
from app.ui.styles import get_colors


# ── LaunchDialog ─────────────────────────────────────

class LaunchDialog(QDialog):
    """Dialog for reviewing instance info, configuring
    launch args, and launching."""

    def __init__(self, parent, instance: Instance,
                 launcher: Launcher):
        super().__init__(parent)
        self.instance      = instance
        self.launcher      = launcher
        self.launch_result = None
        self._main_window  = parent

        self.compat_warning: QLabel    | None = None
        self.custom:         QLineEdit | None = None
        self.log_cb:         QCheckBox | None = None
        self.save_cb:        QCheckBox | None = None
        self.launch_btn:     QPushButton | None = None
        self.arg_cbs:    list[tuple[QCheckBox, dict]] = []
        self.arg_inputs: dict[str, QLineEdit] = {}

        self.setWindowTitle(
            f"Launch — {instance.name}")
        self.setMinimumWidth(500)
        self._build()
        self._check_save_compat()

    def _build(self):
        lo = QVBoxLayout(self)

        info = QGroupBox("Instance")
        gl   = QGridLayout()
        gl.addWidget(QLabel("Name:"), 0, 0)
        gl.addWidget(
            QLabel(f"<b>{self.instance.name}</b>"),
            0, 1)
        gl.addWidget(QLabel("Mods:"), 1, 0)
        gl.addWidget(
            QLabel(str(self.instance.mod_count)),
            1, 1)
        gl.addWidget(QLabel("Saves:"), 2, 0)
        gl.addWidget(
            QLabel(str(self.instance.save_count)),
            2, 1)
        gl.addWidget(QLabel("Path:"), 3, 0)
        pl = QLabel(str(self.instance.path))
        pl.setStyleSheet(
            "color:#6c7086;font-size:11px;")
        gl.addWidget(pl, 3, 1)
        info.setLayout(gl)
        lo.addWidget(info)

        self.compat_warning = QLabel("")
        self.compat_warning.setWordWrap(True)
        self.compat_warning.hide()
        lo.addWidget(self.compat_warning)

        ag = QGroupBox("Launch Arguments")
        al = QVBoxLayout()

        common = Launcher.get_common_launch_args()

        for a in common:
            row = QHBoxLayout()
            cb  = QCheckBox(a['arg'])
            cb.setToolTip(a['desc'])
            cb.setChecked(
                a['arg']
                in self.instance.launch_args)
            row.addWidget(cb)
            row.addWidget(QLabel(a['desc']))

            if a.get('has_value'):
                vi = QLineEdit()
                vi.setFixedWidth(80)
                vi.setPlaceholderText(
                    a.get('default', ''))
                if (a['arg']
                        in self.instance.launch_args):
                    try:
                        idx = (
                            self.instance.launch_args
                            .index(a['arg']))
                        if (idx + 1 < len(
                                self.instance
                                .launch_args)):
                            vi.setText(
                                self.instance
                                .launch_args[idx + 1])
                    except ValueError:
                        pass
                row.addWidget(vi)
                self.arg_inputs[a['arg']] = vi

            row.addStretch()
            self.arg_cbs.append((cb, a))
            al.addLayout(row)

        al.addWidget(QLabel("Custom:"))
        self.custom = QLineEdit()
        self.custom.setPlaceholderText(
            "Extra arguments…")
        known = {a['arg'] for a in common}
        custom_parts: list[str] = []
        i = 0
        while i < len(self.instance.launch_args):
            arg = self.instance.launch_args[i]
            if (arg not in known
                    and arg not in self.arg_inputs):
                custom_parts.append(arg)
            elif arg in self.arg_inputs:
                i += 1
            i += 1
        self.custom.setText(
            ' '.join(custom_parts))
        al.addWidget(self.custom)

        self.log_cb = QCheckBox(
            "Redirect log to instance")
        self.log_cb.setChecked(True)
        al.addWidget(self.log_cb)
        ag.setLayout(al)
        lo.addWidget(ag)

        self.save_cb = QCheckBox(
            "Remember arguments and skip this "
            "dialog next time")
        self.save_cb.setChecked(
            self.instance.mods_configured)
        lo.addWidget(self.save_cb)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        self.launch_btn = QPushButton("▶ Launch")
        self.launch_btn.setObjectName(
            "primaryButton")
        self.launch_btn.clicked.connect(
            self._launch)
        btns.addWidget(self.launch_btn)
        lo.addLayout(btns)

    def _check_save_compat(self):
        saves = self.instance.get_save_files()
        if not saves:
            return

        active_ids = list(self.instance.mods)

        all_mod_ids: set[str] = set()
        if (self._main_window
                and hasattr(
                    self._main_window, 'rw')):
            installed = (
                self._main_window.rw
                .get_installed_mods())
            all_mod_ids = set(installed.keys())

        if not all_mod_ids:
            all_mod_ids = {
                m.lower() for m in active_ids
            }

        worst = SaveCompat.COMPATIBLE
        bad_saves: list[
            tuple[str, SaveCompat]] = []

        for s in saves:
            header = parse_save_header(
                Path(s['path']))
            if header is None:
                continue
            compat = compare_save_mods(
                header, active_ids, all_mod_ids)
            if compat != SaveCompat.COMPATIBLE:
                bad_saves.append(
                    (s['name'], compat))
                if (worst == SaveCompat.COMPATIBLE
                        or compat
                        == SaveCompat.MISSING):
                    worst = compat

        if not bad_saves:
            return

        c     = get_colors(
            AppSettings.instance().theme)
        icon  = COMPAT_ICON[worst]
        color = COMPAT_COLOR[worst]
        lines = [
            f"{icon} Save compatibility warning:"
        ]
        for name, compat in bad_saves[:4]:
            lines.append(
                f"  • {name} — "
                f"{COMPAT_LABEL[compat]}")
        if len(bad_saves) > 4:
            lines.append(
                f"  … and "
                f"{len(bad_saves) - 4} more")

        self.compat_warning.setText(
            '\n'.join(lines))
        self.compat_warning.setStyleSheet(
            f"color:{color};"
            f" font-weight:bold;"
            f" padding:4px 6px;"
            f" background:{c['bg_panel']};"
            f" border:1px solid {color};"
            f" border-radius:4px;")
        self.compat_warning.show()

    def _launch(self):
        extra: list[str] = []
        for cb, a in self.arg_cbs:
            if cb.isChecked():
                extra.append(a['arg'])
                if (a.get('has_value')
                        and a['arg']
                        in self.arg_inputs):
                    v = (self.arg_inputs[a['arg']]
                         .text().strip())
                    extra.append(
                        v or a.get('default', ''))

        c = self.custom.text().strip()
        if c:
            extra.extend(c.split())

        if self.save_cb.isChecked():
            self.instance.launch_args = extra
            self.instance.mods_configured = True
        else:
            self.instance.mods_configured = False
            self.instance.launch_args = extra
        self.instance.save()

        _s        = AppSettings.instance()
        dr        = _s.data_root
        exe       = _s.rimworld_exe
        onyx_mods = (
            Path(dr) / 'mods' if dr else None)
        game_mods = (
            Path(exe).parent / 'Mods'
            if exe else None)

        all_mods = None
        if (self._main_window
                and hasattr(
                    self._main_window, 'rw')):
            all_mods = (
                self._main_window.rw
                .get_installed_mods())

        self.launch_result = self.launcher.launch(
            self.instance, extra,
            log_to_instance=(
                self.log_cb.isChecked()),
            onyx_mods_dir=onyx_mods,
            game_mods_dir=game_mods,
            all_mods=all_mods)
        self.accept()
