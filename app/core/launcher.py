"""
RimWorld process launcher with per-instance config isolation.

Handles executable resolution, config isolation, mod syncing,
save backup, argument building, and playtime tracking.
"""

import os
import stat
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QTimer  # pylint: disable=no-name-in-module

from app.core.instance import Instance
from app.core.mod_linker import sync_instance_mods
from app.core.modlist import write_mods_config
from app.core.paths import get_default_rw_data
from app.utils.file_utils import backup_folder


# ── Module-Level Constants ────────────────────────────────────────────────────

_FALLBACK_VERSION = '1.6.4630 rev467'

_DEFAULT_PREFS_XML = '''\
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
</Prefs>'''


# ── LaunchResult ──────────────────────────────────────────────────────────────

class LaunchResult:
    """Outcome of a Launcher.launch() call."""

    def __init__(self, success: bool,
                 message: str = '',
                 process: Optional[subprocess.Popen] = None):
        self.success = success
        self.message = message
        self.process = process


# ── Launcher ──────────────────────────────────────────────────────────────────

class Launcher:
    """
    Launches RimWorld with per-instance config isolation.

    Isolation works by temporarily moving the default RimWorld
    Config directory aside, writing the instance config in its
    place, launching the game, then restoring the default config
    after a short delay.
    """

    def __init__(self, rimworld_exe: str,
                 auto_backup: bool = False,
                 backup_count: int = 3):
        self.rimworld_exe = rimworld_exe
        self.auto_backup  = auto_backup
        self.backup_count = backup_count
        self._current_process: Optional[
            subprocess.Popen] = None
        self._launch_time: Optional[datetime] = None
        self._recover_orphaned_config()

    # ── Public API ────────────────────────────────────────────────────────

    def launch(
            self,
            instance: Instance,
            extra_args: Optional[list[str]] = None,
            log_to_instance: bool = True,
            onyx_mods_dir: Optional[Path] = None,
            game_mods_dir: Optional[Path] = None,
            all_mods: Optional[dict] = None,
    ) -> LaunchResult:
        """
        Launch RimWorld for the given instance.

        Steps performed:
          1. Resolve and validate the executable.
          2. Ensure the executable is runnable (chmod
             on non-Windows).
          3. Create required instance subdirectories.
          4. Temporarily disable the default RimWorld
             Config (isolation).
          5. Sync mod folders to the game directory.
          6. Write ModsConfig.xml for this instance.
          7. Create a default Prefs.xml if none exists.
          8. Backup saves if auto_backup is enabled.
          9. Build the launch argument list.
          10. Start the process; restore config on
              failure or after 3 s.
        """
        exe = _resolve_exe(
            instance, self.rimworld_exe)
        if not os.path.isfile(exe):
            return LaunchResult(
                False,
                f"RimWorld executable not found: "
                f"{exe}")

        _ensure_executable(exe)
        _ensure_instance_dirs(instance)

        default_config_dir, temp_disabled = (
            _isolate_default_config())

        if (onyx_mods_dir and game_mods_dir
                and all_mods and instance.mods):
            sync_instance_mods(
                instance.mods, all_mods,
                game_mods_dir, onyx_mods_dir)

        mods_to_write = (
            instance.mods or ['ludeon.rimworld'])
        write_mods_config(
            instance.config_dir,
            mods_to_write,
            instance.rimworld_version
            or _FALLBACK_VERSION,
        )

        prefs_path = (
            instance.config_dir / 'Prefs.xml')
        if not prefs_path.exists():
            prefs_path.write_text(
                _DEFAULT_PREFS_XML,
                encoding='utf-8')

        if self.auto_backup and instance.has_saves:
            backup_folder(
                instance.saves_dir,
                instance.path / '_backups',
                self.backup_count)

        args = _build_launch_args(
            exe, instance, extra_args,
            log_to_instance)

        try:
            self._launch_time = datetime.now()
            process = subprocess.Popen(
                args,
                cwd=os.path.dirname(exe),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._current_process = process
            instance.last_played = (
                datetime.now().isoformat())
            instance.save()

            if temp_disabled:
                QTimer.singleShot(
                    3000,
                    lambda: _restore_default_config(
                        default_config_dir,
                        temp_disabled))

            return LaunchResult(
                True,
                f"Launched '{instance.name}' "
                f"(PID {process.pid})",
                process,
            )

        except (OSError, FileNotFoundError,
                PermissionError) as exc:
            if temp_disabled:
                _restore_default_config(
                    default_config_dir,
                    temp_disabled)
            return LaunchResult(
                False, f"Failed to launch: {exc}")

    def is_running(self) -> bool:
        """Return True if the launched process is still running."""
        return (
            self._current_process is not None
            and self._current_process.poll() is None
        )

    def stop(self) -> None:
        """Send SIGTERM to the running process, if any."""
        if self.is_running():
            self._current_process.terminate()

    def get_playtime_minutes(self) -> int:
        """Return elapsed minutes since launch, or 0."""
        if self._launch_time:
            return int(
                (datetime.now() - self._launch_time)
                .total_seconds() / 60)
        return 0

    # ── Static Helpers ────────────────────────────────────────────────────

    @staticmethod
    def get_session_minutes_from_log(
            instance_path: Path,
    ) -> int:
        """
        Estimate session length from Player.log timestamps.

        Uses file creation time (ctime) and last-modified
        time (mtime).  Note: on Linux, ctime is the
        inode-change time, not creation time, so results
        may be approximate on that platform.

        Returns 0 if the log file is absent or unreadable.
        """
        log_path = instance_path / 'Player.log'
        if not log_path.exists():
            return 0
        try:
            stat_result = log_path.stat()
            mtime = datetime.fromtimestamp(
                stat_result.st_mtime)
            ctime = datetime.fromtimestamp(
                stat_result.st_ctime)
            return max(
                0,
                int((mtime - ctime)
                    .total_seconds() / 60))
        except (ValueError, OSError):
            return 0

    @staticmethod
    def get_common_launch_args() -> list[dict]:
        """Return the list of well-known RimWorld launch arguments."""
        return [
            {
                'arg': '-popupwindow',
                'desc': 'Borderless window',
                'has_value': False,
            },
            {
                'arg': '-screen-fullscreen',
                'desc': 'Fullscreen (0/1)',
                'has_value': True,
                'default': '0',
            },
            {
                'arg': '-screen-width',
                'desc': 'Width',
                'has_value': True,
                'default': '1920',
            },
            {
                'arg': '-screen-height',
                'desc': 'Height',
                'has_value': True,
                'default': '1080',
            },
            {
                'arg': '-force-d3d11',
                'desc': 'Force DirectX 11',
                'has_value': False,
            },
            {
                'arg': '-force-vulkan',
                'desc': 'Force Vulkan',
                'has_value': False,
            },
            {
                'arg': '-nolog',
                'desc': 'Disable logging',
                'has_value': False,
            },
            {
                'arg': '-force-gfx-mt',
                'desc': 'Multithreaded rendering',
                'has_value': False,
            },
        ]

    # ── Private ───────────────────────────────────────────────────────────

    def _recover_orphaned_config(self) -> None:
        """
        Restore the default RimWorld Config if it was left
        disabled by a previous launcher crash before the
        3-second restore timer fired.
        """
        rw_data = get_default_rw_data()
        temp    = rw_data / '_onyx_temp_disabled'
        real    = rw_data / 'Config'
        if temp.exists() and not real.exists():
            try:
                shutil.move(str(temp), str(real))
            except OSError:
                pass


# ── Module-Level Helpers ──────────────────────────────────────────────────────

def _resolve_exe(instance: Instance,
                 global_exe: str) -> str:
    """Return the effective RimWorld exe path for this instance."""
    override = getattr(
        instance, 'rimworld_exe_override', '')
    return override if override else global_exe


def _ensure_executable(exe: str) -> None:
    """On non-Windows platforms, ensure the executable bit is set."""
    if os.name != 'nt':
        exe_path     = Path(exe)
        current_mode = exe_path.stat().st_mode
        exe_path.chmod(
            current_mode
            | stat.S_IEXEC
            | stat.S_IXGRP
            | stat.S_IXOTH)


def _ensure_instance_dirs(instance: Instance) -> None:
    """Create all required subdirectories for the instance."""
    for sub in ('Config', 'Saves', 'HugsLib',
                'Scenarios', 'External'):
        (instance.path / sub).mkdir(
            parents=True, exist_ok=True)


def _isolate_default_config(
) -> tuple[Path, Optional[Path]]:
    """
    Move the default RimWorld Config aside so the game
    reads the instance config instead.

    Returns (default_config_dir, temp_path).
    temp_path is None if the move failed or there was
    nothing to move.
    """
    rw_data    = get_default_rw_data()
    config_dir = rw_data / 'Config'
    temp       = rw_data / '_onyx_temp_disabled'

    if not config_dir.exists():
        return config_dir, None

    try:
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)
        shutil.move(str(config_dir), str(temp))
        return config_dir, temp
    except OSError:
        return config_dir, None


def _restore_default_config(
        default_path: Path,
        temp_path: Path,
) -> None:
    """
    Move the temporarily disabled default Config back.

    Safe to call even if temp_path no longer exists.
    """
    try:
        if temp_path.exists():
            if default_path.exists():
                shutil.rmtree(
                    default_path,
                    ignore_errors=True)
            shutil.move(
                str(temp_path), str(default_path))
    except OSError:
        pass


def _build_launch_args(
        exe: str,
        instance: Instance,
        extra_args: Optional[list[str]],
        log_to_instance: bool,
) -> list[str]:
    """
    Construct the full argument list for subprocess.Popen.

    Merges instance launch_args and extra_args,
    deduplicating by flag name.  Flags that take a separate
    value token (e.g. '-screen-width 1920') are joined into
    a single '=' form ('-screen-width=1920').
    """
    instance_abs = str(instance.path.resolve())
    args: list[str] = [
        exe, f'-savedatafolder={instance_abs}',
    ]

    if log_to_instance:
        log_abs = str(
            (instance.path / 'Player.log').resolve())
        args.append(f'-logfile={log_abs}')

    seen: set[str] = {
        '-savedatafolder', '-logfile',
    }

    for arg_list in (instance.launch_args or [],
                     extra_args or []):
        idx = 0
        while idx < len(arg_list):
            arg = arg_list[idx]
            if arg.startswith('-'):
                base = arg.split('=')[0]
                if base not in seen:
                    seen.add(base)
                    if (
                        '=' not in arg
                        and idx + 1 < len(arg_list)
                        and not arg_list[
                            idx + 1].startswith('-')
                    ):
                        args.append(
                            f"{arg}="
                            f"{arg_list[idx + 1]}")
                        idx += 1
                    else:
                        args.append(arg)
            idx += 1

    return args
