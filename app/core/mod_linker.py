"""
Links Onyx-downloaded mods into the game's Mods folder.
Per-instance sync: on launch, only active mods get linked.
"""

import ctypes
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

_DLC_PACKAGE_IDS = frozenset({
    'ludeon.rimworld',
    'ludeon.rimworld.royalty',
    'ludeon.rimworld.ideology',
    'ludeon.rimworld.biotech',
    'ludeon.rimworld.anomaly',
    'ludeon.rimworld.odyssey',
})

_DLC_FOLDER_NAMES = frozenset({
    'core', 'royalty', 'ideology', 'biotech',
    'anomaly', 'odyssey',
})

# Windows API constant — junction/reparse-point attribute flag
_FILE_ATTR_REPARSE_POINT = 0x400


# ── DLC Guard ─────────────────────────────────────────────────────────────────

def _is_dlc(mod_id: str, folder_name: str = '') -> bool:
    """Return True if mod_id or folder_name identifies a vanilla DLC."""
    if mod_id.lower() in _DLC_PACKAGE_IDS:
        return True
    if folder_name.lower() in _DLC_FOLDER_NAMES:
        return True
    return False


# ── Public API ────────────────────────────────────────────────────────────────

def sync_instance_mods(
        active_mod_ids: list[str],
        all_mods: dict,
        game_mods_dir: Path,
        onyx_mods_dir: Optional[Path] = None,
) -> dict:
    """
    Synchronise the game's Mods folder to match the active mod list.

    Removes game-side links for mods that are no longer active, and
    creates new links for mods that are active but not yet linked.
    DLC folders are always skipped.  Returns a result dict with
    counters and an 'errors' list of non-fatal problem descriptions.
    """
    results: dict = {
        'linked': 0, 'unlinked': 0, 'skipped': 0,
        'failed': 0, 'errors': [],
    }
    game_mods_dir.mkdir(parents=True, exist_ok=True)

    needed_folders = _build_needed_folders(
        active_mod_ids, all_mods)

    onyx_managed: set[str] = set()
    if onyx_mods_dir and onyx_mods_dir.exists():
        onyx_managed = {
            d.name for d in onyx_mods_dir.iterdir()
            if d.is_dir()
        }

    _remove_stale_links(
        game_mods_dir, onyx_managed,
        needed_folders, results)

    if onyx_mods_dir:
        _add_needed_links(
            onyx_mods_dir, game_mods_dir,
            needed_folders, results)

    return results


def clear_all_managed_mods(
        game_mods_dir: Path,
        onyx_mods_dir: Path,
) -> dict:
    """
    Remove all game-side links for mods managed by Onyx.

    Only removes items whose folder name appears in
    onyx_mods_dir.  DLC folders are always skipped.
    """
    results: dict = {
        'removed': 0, 'failed': 0, 'errors': [],
    }
    if not onyx_mods_dir.exists():
        return results
    onyx_managed = {
        d.name for d in onyx_mods_dir.iterdir()
        if d.is_dir()
    }
    for item in game_mods_dir.iterdir():
        if item.is_dir() and item.name in onyx_managed:
            if item.name.lower() in _DLC_FOLDER_NAMES:
                continue
            if _force_remove(item):
                results['removed'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(
                    f"Failed to remove {item.name}")
    return results


def sync_all_mods(
        onyx_mods_dir: Path,
        game_mods_dir: Path,
) -> dict:
    """
    Link every mod in onyx_mods_dir into game_mods_dir.

    Skips DLC folders and any destination that already exists.
    """
    results: dict = {
        'linked': 0, 'skipped': 0,
        'failed': 0, 'errors': [],
    }
    if not onyx_mods_dir.exists():
        return results
    game_mods_dir.mkdir(parents=True, exist_ok=True)
    for mod_dir in onyx_mods_dir.iterdir():
        if not mod_dir.is_dir():
            continue
        if mod_dir.name.lower() in _DLC_FOLDER_NAMES:
            continue
        dst = game_mods_dir / mod_dir.name
        if _path_exists_any(dst):
            results['skipped'] += 1
            continue
        ok, method = _create_link(mod_dir, dst)
        if ok:
            results['linked'] += 1
        else:
            results['failed'] += 1
            results['errors'].append(
                f"{mod_dir.name}: {method}")
    return results


def link_mod_to_game(
        mod_source: Path,
        game_mods_dir: Path,
) -> tuple[bool, str]:
    """
    Link a single mod source directory into game_mods_dir.

    Returns (True, reason) on success, (False, reason)
    on failure.
    """
    if not mod_source.exists():
        return False, "source_missing"
    if mod_source.name.lower() in _DLC_FOLDER_NAMES:
        return True, "dlc_skipped"
    game_mods_dir.mkdir(parents=True, exist_ok=True)
    dst = game_mods_dir / mod_source.name
    if _path_exists_any(dst):
        return True, "already_exists"
    return _create_link(mod_source, dst)


def unlink_mod_from_game(
        mod_name: str,
        game_mods_dir: Path,
) -> bool:
    """Remove the game-side link for a single mod by folder name."""
    target = game_mods_dir / mod_name
    if not _path_exists_any(target):
        return True
    return _force_remove(target)


def delete_downloaded_mod(
        mod_folder: Path,
        game_mods_dir: Path,
) -> bool:
    """
    Unlink and permanently delete a mod folder from the Onyx
    mods directory.

    Returns True if the folder no longer exists after the
    operation.
    """
    unlink_mod_from_game(mod_folder.name, game_mods_dir)
    if mod_folder.exists():
        try:
            shutil.rmtree(str(mod_folder))
            return True
        except OSError:
            return False
    return True


def verify_game_mods(
        onyx_mods_dir: Path,
        game_mods_dir: Path,
) -> dict:
    """
    Check the status of each Onyx-managed mod in game_mods_dir.

    Returns a dict mapping folder_name to
    'ok' | 'missing' | 'broken'.
    """
    status: dict = {}
    if not onyx_mods_dir.exists():
        return status
    for d in onyx_mods_dir.iterdir():
        if not d.is_dir():
            continue
        if d.name.lower() in _DLC_FOLDER_NAMES:
            continue
        target = game_mods_dir / d.name
        if not _path_exists_any(target):
            status[d.name] = 'missing'
        elif _is_valid_mod(target):
            status[d.name] = 'ok'
        else:
            status[d.name] = 'broken'
    return status


def delete_mod_permanently(
        workshop_id: str,
        onyx_mods_dir: Path,
        game_mods_dir: Path,
        steamcmd_path: str = '',
) -> dict:
    """
    Permanently delete a mod from:
      1. The game Mods folder (junction / symlink / copy)
      2. The Onyx mods folder (source files)
      3. The SteamCMD ACF manifest (if steamcmd_path provided)

    Returns a result dict with keys:
        'removed_link'   bool  — game-side link/dir was removed
        'removed_source' bool  — onyx source folder was removed
        'removed_acf'    bool  — ACF entry was cleaned
        'errors'         list  — any non-fatal error messages
    """
    errors: list[str] = []
    result = {
        'removed_link':   False,
        'removed_source': False,
        'removed_acf':    False,
        'errors':         errors,
    }

    source_folder = _find_source_folder(
        onyx_mods_dir, workshop_id, errors)

    if source_folder is None:
        errors.append(
            f"Mod folder for workshop ID '{workshop_id}'"
            f" not found in {onyx_mods_dir}")
        game_target = game_mods_dir / workshop_id
        if _path_exists_any(game_target):
            if _force_remove(game_target):
                result['removed_link'] = True
            else:
                errors.append(
                    f"Could not remove game link: "
                    f"{game_target}")
        return result

    folder_name = source_folder.name
    game_target = game_mods_dir / folder_name

    if _path_exists_any(game_target):
        if _force_remove(game_target):
            result['removed_link'] = True
        else:
            errors.append(
                f"Could not remove game link: "
                f"{game_target}")
    else:
        result['removed_link'] = True

    if source_folder.exists():
        try:
            shutil.rmtree(str(source_folder))
            if not source_folder.exists():
                result['removed_source'] = True
            else:
                errors.append(
                    f"rmtree completed but folder "
                    f"still exists: {source_folder}")
        except OSError as exc:
            errors.append(
                f"Could not delete source folder "
                f"'{source_folder}': {exc}")
    else:
        result['removed_source'] = True

    if steamcmd_path and workshop_id:
        steamcmd_root = Path(steamcmd_path).parent
        result['removed_acf'] = _remove_from_acf(
            steamcmd_root, workshop_id, errors)

    return result


# ── sync_instance_mods Helpers ────────────────────────────────────────────────

def _build_needed_folders(
        active_mod_ids: list[str],
        all_mods: dict,
) -> dict[str, str]:
    """
    Build a mapping of folder_name to mod_id for non-DLC
    active mods that exist on disk and are not inside the
    game's Data directory.
    """
    needed: dict[str, str] = {}
    for mid in active_mod_ids:
        if _is_dlc(mid):
            continue
        info = all_mods.get(mid)
        if not (info and info.path and info.path.exists()):
            continue
        if _is_dlc(mid, info.path.name):
            continue
        try:
            path_str = str(info.path.resolve()).lower()
            if ('data' + os.sep in path_str
                    and ('rimworld' in path_str
                         or 'game' in path_str)):
                continue
        except OSError:
            pass
        needed[info.path.name] = mid
    return needed


def _remove_stale_links(
        game_mods_dir: Path,
        onyx_managed: set[str],
        needed_folders: dict[str, str],
        results: dict,
) -> None:
    """Remove game-side links for Onyx-managed mods no longer needed."""
    for item in game_mods_dir.iterdir():
        if not item.is_dir():
            continue
        if item.name.lower() in _DLC_FOLDER_NAMES:
            continue
        if (item.name in onyx_managed
                and item.name not in needed_folders):
            if _force_remove(item):
                results['unlinked'] += 1
            else:
                results['errors'].append(
                    f"Failed to remove {item.name}")


def _add_needed_links(
        onyx_mods_dir: Path,
        game_mods_dir: Path,
        needed_folders: dict[str, str],
        results: dict,
) -> None:
    """Create game-side links for all needed mod folders."""
    for folder_name in needed_folders:
        if folder_name.lower() in _DLC_FOLDER_NAMES:
            continue

        src = onyx_mods_dir / folder_name
        if not src.exists():
            results['errors'].append(
                f"Source missing: {folder_name}")
            continue

        dst = game_mods_dir / folder_name

        if _path_exists_any(dst):
            if _is_valid_link(dst, src):
                results['skipped'] += 1
                continue
            _force_remove(dst)

        ok, method = _create_link(src, dst)
        if ok:
            results['linked'] += 1
        else:
            results['failed'] += 1
            results['errors'].append(
                f"{folder_name}: {method}")


def _find_source_folder(
        onyx_mods_dir: Path,
        workshop_id: str,
        errors: list,
) -> Optional[Path]:
    """
    Locate a mod's source folder in onyx_mods_dir by
    workshop_id.

    Checks for a direct folder named workshop_id first,
    then scans PublishedFileId.txt files inside each
    subfolder.  Returns the Path if found, or None.
    """
    candidate = onyx_mods_dir / workshop_id
    if candidate.exists() and candidate.is_dir():
        return candidate

    try:
        for d in onyx_mods_dir.iterdir():
            if not d.is_dir():
                continue
            for pid_name in ('PublishedFileId.txt',
                             'publishedfileid.txt'):
                pid_file = d / 'About' / pid_name
                if not pid_file.exists():
                    pid_file = d / pid_name
                if pid_file.exists():
                    try:
                        content = pid_file.read_text()
                        if content.strip() == workshop_id:
                            return d
                    except OSError:
                        pass
    except PermissionError as exc:
        errors.append(
            f"Cannot scan mods dir: {exc}")

    return None


# ── Low-Level Helpers ─────────────────────────────────────────────────────────

def _path_exists_any(path: Path) -> bool:
    """
    Return True if path exists by any filesystem check.

    Checks Path.exists(), is_symlink(), os.path.lexists(),
    and on Windows also uses GetFileAttributesW to detect
    junctions that Python's stat may not see correctly.
    """
    if path.exists():
        return True
    if path.is_symlink():
        return True
    if os.path.lexists(str(path)):
        return True
    if os.name == 'nt':
        try:
            attrs = (
                ctypes.windll
                .kernel32
                .GetFileAttributesW(str(path))
            )
            if attrs != -1:
                return True
        except Exception:  # pylint: disable=broad-exception-caught
            # ctypes call may fail on unusual FS configs
            pass
    return False


def _is_valid_link(
        link_path: Path,
        expected_target: Path,
) -> bool:
    """
    Return True if link_path is a valid link pointing at
    expected_target.

    For symlinks, verifies the resolved target matches.
    For Windows junctions, verifies the junction is
    accessible as a directory.
    For copies, verifies the folder contains a valid mod.
    """
    if not _path_exists_any(link_path):
        return False
    try:
        if link_path.is_symlink():
            target = link_path.readlink()
            return (
                target == expected_target
                or target.resolve()
                == expected_target.resolve()
            )
        if os.name == 'nt' and _is_junction(link_path):
            return link_path.is_dir()
        return _is_valid_mod(link_path)
    except OSError:
        return False


def _create_link(
        source: Path,
        target: Path,
) -> tuple[bool, str]:
    """
    Create a link from target pointing at source.

    Tries, in order: Windows junction, symlink, full copy.
    Returns (True, method_name) on success,
    (False, reason) on failure.
    """
    if _path_exists_any(target):
        if not _force_remove(target):
            return False, "cannot_remove_existing"

    # Windows: try junction first
    if os.name == 'nt':
        try:
            subprocess.run(
                ['cmd', '/c', 'mklink', '/J',
                 str(target), str(source)],
                capture_output=True, text=True,
                timeout=10, check=False)
            if (_path_exists_any(target)
                    and _is_valid_mod(target)):
                return True, "junction"
        except (OSError, FileNotFoundError):
            pass

    # All platforms: symlink
    try:
        target.symlink_to(
            source, target_is_directory=True)
        if (_path_exists_any(target)
                and _is_valid_mod(target)):
            return True, "symlink"
    except OSError:
        pass

    # Fallback: full copy
    try:
        if _path_exists_any(target):
            _force_remove(target)
        shutil.copytree(
            str(source), str(target),
            dirs_exist_ok=True)
        if _is_valid_mod(target):
            return True, "copy"
        return False, "copy_invalid"
    except FileExistsError:
        return _path_exists_any(target), "already_exists"
    except OSError as exc:
        return False, f"copy_failed:{exc}"


def _force_remove(target: Path) -> bool:
    """
    Remove target by any available method — symlink unlink,
    rmdir, or rmtree.

    Returns True if the path no longer exists after the
    operation.  Best-effort: catches all exceptions and
    returns the final existence check.
    """
    try:
        is_link = target.is_symlink()
        is_junc = _is_junction(target)

        if is_link or is_junc:
            if os.name == 'nt':
                try:
                    os.rmdir(str(target))
                    return not _path_exists_any(target)
                except OSError:
                    try:
                        subprocess.run(
                            ['cmd', '/c', 'rmdir',
                             str(target)],
                            capture_output=True,
                            timeout=10, check=False)
                        return not _path_exists_any(
                            target)
                    except (OSError,
                            FileNotFoundError):
                        pass
            else:
                target.unlink()
                return not _path_exists_any(target)

        elif target.is_dir():
            shutil.rmtree(
                str(target), ignore_errors=True)
            return not _path_exists_any(target)
        elif target.is_file():
            target.unlink()
            return not _path_exists_any(target)
        else:
            if os.name == 'nt':
                subprocess.run(
                    ['cmd', '/c', 'rmdir', '/s', '/q',
                     str(target)],
                    capture_output=True,
                    timeout=10, check=False)
            else:
                shutil.rmtree(
                    str(target), ignore_errors=True)
            return not _path_exists_any(target)

    except Exception:  # pylint: disable=broad-exception-caught
        # best-effort removal — any failure is non-fatal
        pass
    return not _path_exists_any(target)


def _is_valid_mod(path: Path) -> bool:
    """
    Return True if path looks like a valid mod directory.

    Checks for About/About.xml, About/about.xml, or any
    contents at all.
    """
    if not path.is_dir():
        return False
    for n in ('About.xml', 'about.xml'):
        if ((path / 'About' / n).exists()
                or (path / n).exists()):
            return True
    try:
        return any(path.iterdir())
    except PermissionError:
        return False


def _is_junction(path: Path) -> bool:
    """Return True if path is a Windows junction point."""
    if os.name != 'nt':
        return False
    try:
        attrs = (
            ctypes.windll
            .kernel32
            .GetFileAttributesW(str(path))
        )
        if attrs == -1:
            return False
        return bool(attrs & _FILE_ATTR_REPARSE_POINT)
    except Exception:  # pylint: disable=broad-exception-caught
        # ctypes call may fail on unusual FS configs
        return False


# ── ACF Helpers ───────────────────────────────────────────────────────────────

def _remove_from_acf(
        steamcmd_root: Path,
        workshop_id: str,
        errors: list,
) -> bool:
    """
    Remove a workshop item entry from appworkshop_294100.acf
    so SteamCMD does not think the mod is still managed.

    Parses the ACF text manually to avoid adding a dependency.
    Returns True if the file was modified, False otherwise.
    """
    acf_candidates = [
        steamcmd_root / 'steamapps' / 'workshop'
        / 'appworkshop_294100.acf',
        steamcmd_root / 'workshop'
        / 'appworkshop_294100.acf',
    ]

    acf_path: Optional[Path] = None
    for c in acf_candidates:
        if c.exists():
            acf_path = c
            break

    if acf_path is None:
        return False

    try:
        text = acf_path.read_text(
            encoding='utf-8', errors='replace')
    except OSError as exc:
        errors.append(f"Cannot read ACF file: {exc}")
        return False

    original = text
    text = _acf_remove_key_block(text, workshop_id)

    if text == original:
        return False

    try:
        acf_path.write_text(text, encoding='utf-8')
        return True
    except OSError as exc:
        errors.append(
            f"Cannot write ACF file: {exc}")
        return False


def _acf_remove_key_block(src: str, key: str) -> str:
    """
    Remove a quoted key and its following brace block
    from ACF text.

    Handles nested braces correctly.  Only removes blocks
    where the key is followed by whitespace then '{' (not
    inline string values).  Safe to call when the key is
    absent — returns src unchanged.
    """
    search = f'"{key}"'
    pos    = 0

    while True:
        idx = src.find(search, pos)
        if idx == -1:
            break

        brace_start = src.find('{', idx + len(search))
        if brace_start == -1:
            break

        between = src[idx + len(search):brace_start]
        if between.strip():
            pos = idx + 1
            continue

        depth  = 0
        cursor = brace_start
        while cursor < len(src):
            if src[cursor] == '{':
                depth += 1
            elif src[cursor] == '}':
                depth -= 1
                if depth == 0:
                    break
            cursor += 1

        if depth != 0:
            pos = idx + 1
            continue

        brace_end    = cursor
        remove_start = idx

        while (remove_start > 0
               and src[remove_start - 1] in ' \t'):
            remove_start -= 1
        if (remove_start > 0
                and src[remove_start - 1] == '\n'):
            remove_start -= 1

        remove_end = brace_end + 1
        if (remove_end < len(src)
                and src[remove_end] == '\n'):
            remove_end += 1

        src = src[:remove_start] + src[remove_end:]

    return src
