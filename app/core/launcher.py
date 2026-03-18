import subprocess
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
from app.core.instance import Instance
from app.core.mod_linker import sync_instance_mods
from app.core.modlist import read_mods_config, write_mods_config
from app.utils.file_utils import backup_folder

_FALLBACK_VERSION = '1.6.4630 rev467'


class LaunchResult:
    def __init__(self, success: bool, message: str = '', process=None):
        self.success = success
        self.message = message
        self.process = process


class Launcher:
    def __init__(self, rimworld_exe: str, auto_backup: bool = False,
                 backup_count: int = 3):
        self.rimworld_exe     = rimworld_exe
        self.auto_backup      = auto_backup
        self.backup_count     = backup_count
        self._current_process = None
        self._launch_time: Optional[datetime] = None
        self._recover_orphaned_config()

    def _recover_orphaned_config(self):
        from app.core.paths import get_default_rw_data
        temp = get_default_rw_data() / '_onyx_temp_disabled'
        real = get_default_rw_data() / 'Config'
        if temp.exists() and not real.exists():
            try:
                shutil.move(str(temp), str(real))
            except Exception:
                pass

    def launch(self, instance: Instance,
               extra_args: Optional[list[str]] = None,
               log_to_instance: bool = True,
               onyx_mods_dir: Optional[Path] = None,
               game_mods_dir: Optional[Path] = None,
               all_mods: Optional[dict] = None) -> LaunchResult:

        if not os.path.isfile(self.rimworld_exe):
            return LaunchResult(
                False,
                f"RimWorld executable not found: {self.rimworld_exe}")

        # ── 1: Prepare instance directories ──────────────────────────────
        config_dir = instance.path / 'Config'
        saves_dir  = instance.path / 'Saves'
        config_dir.mkdir(parents=True, exist_ok=True)
        saves_dir.mkdir(parents=True, exist_ok=True)
        for sub in ('HugsLib', 'Scenarios', 'External'):
            (instance.path / sub).mkdir(parents=True, exist_ok=True)

        # ── 2: Isolate from default RimWorld config ───────────────────────
        from app.core.paths import get_default_rw_data
        default_config_dir   = get_default_rw_data() / 'Config'
        temp_disabled_config = None

        if default_config_dir.exists():
            temp_disabled_config = default_config_dir.parent / '_onyx_temp_disabled'
            try:
                if temp_disabled_config.exists():
                    shutil.rmtree(temp_disabled_config, ignore_errors=True)
                shutil.move(str(default_config_dir), str(temp_disabled_config))
            except Exception:
                temp_disabled_config = None

        # ── 3: Sync mods to game folder ───────────────────────────────────
        if onyx_mods_dir and game_mods_dir and all_mods and instance.mods:
            sync_instance_mods(
                instance.mods, all_mods, game_mods_dir, onyx_mods_dir)

        # ── 4: Write ModsConfig.xml ───────────────────────────────────────
        mods_to_write = instance.mods or ['ludeon.rimworld']
        write_mods_config(
            config_dir,
            mods_to_write,
            instance.rimworld_version or _FALLBACK_VERSION,
        )

        # ── 5: Ensure Prefs.xml exists ────────────────────────────────────
        prefs_path = config_dir / 'Prefs.xml'
        if not prefs_path.exists():
            self._create_default_prefs(prefs_path)

        # ── 6: Backup saves ───────────────────────────────────────────────
        if self.auto_backup and instance.has_saves:
            backup_folder(saves_dir, instance.path / '_backups',
                          self.backup_count)

        # ── 7: Build launch command ───────────────────────────────────────
        instance_abs = str(instance.path.resolve())

        args: list[str] = [
            self.rimworld_exe,
            f'-savedatafolder={instance_abs}',
        ]
        if log_to_instance:
            log_abs = str((instance.path / 'Player.log').resolve())
            args.append(f'-logfile={log_abs}')

        seen_flags: set[str] = {'-savedatafolder', '-logfile'}
        for arg_list in (instance.launch_args or [], extra_args or []):
            idx = 0
            while idx < len(arg_list):
                arg = arg_list[idx]
                if arg.startswith('-'):
                    base = arg.split('=')[0]
                    if base not in seen_flags:
                        seen_flags.add(base)
                        if ('=' not in arg and
                                idx + 1 < len(arg_list) and
                                not arg_list[idx + 1].startswith('-')):
                            args.append(f"{arg}={arg_list[idx + 1]}")
                            idx += 1
                        else:
                            args.append(arg)
                idx += 1

        # ── Launch ────────────────────────────────────────────────────────
        try:
            self._launch_time = datetime.now()
            process = subprocess.Popen(
                args,
                cwd=os.path.dirname(self.rimworld_exe),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._current_process = process
            instance.last_played  = datetime.now().isoformat()
            instance.save()

            if temp_disabled_config:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(3000, lambda: self._restore_default_config(
                    default_config_dir, temp_disabled_config))

            return LaunchResult(
                True,
                f"Launched '{instance.name}' (PID {process.pid})",
                process)

        except Exception as e:
            if temp_disabled_config:
                self._restore_default_config(
                    default_config_dir, temp_disabled_config)
            return LaunchResult(False, f"Failed to launch: {e}")

    def _create_default_prefs(self, target: Path):
        target.write_text('''\
<?xml version="1.0" encoding="utf-8"?>
<Prefs>
  <VolumeGame>0.7</VolumeGame>
  <VolumeMusic>0.4</VolumeMusic>
  <VolumeAmbient>1</VolumeAmbient>
  <UIScale>1</UIScale>
  <RunInBackground>True</RunInBackground>
  <ScreenWidth>1920</ScreenWidth>
  <ScreenHeight>1080</ScreenHeight>
  <FullScreen>False</FullScreen>
  <LangFolderName>English</LangFolderName>
</Prefs>''', encoding='utf-8')

    def _restore_default_config(self, default_path: Path, temp_path: Path):
        try:
            if temp_path.exists():
                if default_path.exists():
                    shutil.rmtree(default_path, ignore_errors=True)
                shutil.move(str(temp_path), str(default_path))
        except Exception:
            pass

    def is_running(self) -> bool:
        return (self._current_process is not None and
                self._current_process.poll() is None)

    def stop(self):
        if self.is_running():
            self._current_process.terminate()

    def get_playtime_minutes(self) -> int:
        if self._launch_time:
            return int(
                (datetime.now() - self._launch_time).total_seconds() / 60)
        return 0

    @staticmethod
    def get_common_launch_args() -> list[dict]:
        return [
            {'arg': '-popupwindow',       'desc': 'Borderless window',       'has_value': False},
            {'arg': '-screen-fullscreen', 'desc': 'Fullscreen (0/1)',         'has_value': True, 'default': '0'},
            {'arg': '-screen-width',      'desc': 'Width',                   'has_value': True, 'default': '1920'},
            {'arg': '-screen-height',     'desc': 'Height',                  'has_value': True, 'default': '1080'},
            {'arg': '-force-d3d11',       'desc': 'Force DirectX 11',        'has_value': False},
            {'arg': '-force-vulkan',      'desc': 'Force Vulkan',            'has_value': False},
            {'arg': '-nolog',             'desc': 'Disable logging',         'has_value': False},
            {'arg': '-force-gfx-mt',      'desc': 'Multithreaded rendering', 'has_value': False},
        ]