"""
Links Onyx-downloaded mods into the game's Mods folder.
Per-instance sync: on launch, only active mods get linked.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# DLC package IDs — these are loaded from Game/Data/ automatically.
# NEVER link these into Game/Mods/ or RimWorld will see duplicates.
_DLC_PACKAGE_IDS = {
    'ludeon.rimworld',
    'ludeon.rimworld.royalty',
    'ludeon.rimworld.ideology',
    'ludeon.rimworld.biotech',
    'ludeon.rimworld.anomaly',
    'ludeon.rimworld.odyssey',
}

# DLC folder names in Game/Data/ — also skip these by folder name
_DLC_FOLDER_NAMES = {
    'core', 'royalty', 'ideology', 'biotech', 'anomaly', 'odyssey',
}


def _is_dlc(mod_id: str, folder_name: str = '') -> bool:
    """Check if a mod is a DLC that RimWorld loads from Data/ automatically."""
    if mod_id.lower() in _DLC_PACKAGE_IDS:
        return True
    if folder_name.lower() in _DLC_FOLDER_NAMES:
        return True
    return False


def sync_instance_mods(active_mod_ids: list[str],
                       all_mods: dict,
                       game_mods_dir: Path,
                       onyx_mods_dir: Optional[Path] = None) -> dict:
    """
    Sync game Mods folder to match this instance's active mods.
    Removes Onyx-managed links not in active list, adds missing ones.
    Never touches DLC mods (they load from Game/Data/).
    """
    results = {'linked': 0, 'unlinked': 0, 'skipped': 0, 'failed': 0, 'errors': []}
    game_mods_dir.mkdir(parents=True, exist_ok=True)

    needed_folders = {}
    for mid in active_mod_ids:
        # Skip DLCs — they're in Game/Data/
        if _is_dlc(mid):
            continue
        info = all_mods.get(mid)
        if info and info.path and info.path.exists():
            # Also skip if the folder name matches a DLC
            if _is_dlc(mid, info.path.name):
                continue
            # Skip mods whose source path is inside Game/Data/
            try:
                path_str = str(info.path.resolve()).lower()
                if 'data' + os.sep in path_str and ('rimworld' in path_str or 'game' in path_str):
                    # This mod lives in Game/Data/ — don't link
                    continue
            except Exception:
                pass
            needed_folders[info.path.name] = mid

    print(f"[Sync] Active mods need {len(needed_folders)} folders linked (DLCs excluded)")

    onyx_managed = set()
    if onyx_mods_dir and onyx_mods_dir.exists():
        onyx_managed = {d.name for d in onyx_mods_dir.iterdir() if d.is_dir()}

    print(f"[Sync] Found {len(onyx_managed)} Onyx-managed mods")

    # Remove links that shouldn't be there (only Onyx-managed, never DLCs)
    for item in game_mods_dir.iterdir():
        if not item.is_dir():
            continue
        # Never touch DLC folders
        if item.name.lower() in _DLC_FOLDER_NAMES:
            continue
        if item.name in onyx_managed:
            if item.name not in needed_folders:
                print(f"[Sync] Removing unneeded mod: {item.name}")
                if _force_remove(item):
                    results['unlinked'] += 1
                else:
                    results['errors'].append(f"Failed to remove {item.name}")

    # Add needed links
    if onyx_mods_dir:
        for folder_name, mod_id in needed_folders.items():
            # Double-check: don't link DLC folder names
            if folder_name.lower() in _DLC_FOLDER_NAMES:
                continue

            src = onyx_mods_dir / folder_name
            if not src.exists():
                print(f"[Sync] Source missing for {mod_id}: {src}")
                results['errors'].append(f"Source missing: {folder_name}")
                continue

            dst = game_mods_dir / folder_name

            if _path_exists_any(dst):
                if _is_valid_link(dst, src):
                    results['skipped'] += 1
                    continue
                else:
                    print(f"[Sync] Removing broken link: {folder_name}")
                    _force_remove(dst)

            print(f"[Sync] Linking {folder_name}")
            ok, method = _create_link(src, dst)
            if ok:
                results['linked'] += 1
                print(f"[Sync] ✓ Linked {folder_name} ({method})")
            else:
                results['failed'] += 1
                results['errors'].append(f"{folder_name}: {method}")
                print(f"[Sync] ✗ Failed {folder_name}: {method}")

    print(f"[Sync] Complete: linked={results['linked']}, unlinked={results['unlinked']}, "
          f"skipped={results['skipped']}, failed={results['failed']}")

    return results


def clear_all_managed_mods(game_mods_dir: Path, onyx_mods_dir: Path) -> dict:
    results = {'removed': 0, 'failed': 0, 'errors': []}
    if not onyx_mods_dir.exists():
        return results
    onyx_managed = {d.name for d in onyx_mods_dir.iterdir() if d.is_dir()}
    for item in game_mods_dir.iterdir():
        if item.is_dir() and item.name in onyx_managed:
            if item.name.lower() in _DLC_FOLDER_NAMES:
                continue
            if _force_remove(item):
                results['removed'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(f"Failed to remove {item.name}")
    return results


def sync_all_mods(onyx_mods_dir: Path, game_mods_dir: Path) -> dict:
    """Link ALL downloaded mods into game folder (skipping DLCs)."""
    results = {'linked': 0, 'skipped': 0, 'failed': 0, 'errors': []}
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
            results['errors'].append(f"{mod_dir.name}: {method}")
    return results


def link_mod_to_game(mod_source: Path, game_mods_dir: Path) -> tuple[bool, str]:
    if not mod_source.exists():
        return False, "source_missing"
    if mod_source.name.lower() in _DLC_FOLDER_NAMES:
        return True, "dlc_skipped"
    game_mods_dir.mkdir(parents=True, exist_ok=True)
    dst = game_mods_dir / mod_source.name
    if _path_exists_any(dst):
        return True, "already_exists"
    return _create_link(mod_source, dst)


def unlink_mod_from_game(mod_name: str, game_mods_dir: Path) -> bool:
    target = game_mods_dir / mod_name
    if not _path_exists_any(target):
        return True
    return _force_remove(target)


def delete_downloaded_mod(mod_folder: Path, game_mods_dir: Path) -> bool:
    unlink_mod_from_game(mod_folder.name, game_mods_dir)
    if mod_folder.exists():
        try:
            shutil.rmtree(str(mod_folder))
            return True
        except Exception as e:
            print(f"[ModLink] Delete failed: {e}")
            return False
    return True


def verify_game_mods(onyx_mods_dir: Path, game_mods_dir: Path) -> dict:
    status = {}
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


# ── Low-level helpers (unchanged) ────────────────────────────────

def _path_exists_any(path: Path) -> bool:
    if path.exists():
        return True
    if path.is_symlink():
        return True
    if os.path.lexists(str(path)):
        return True
    if os.name == 'nt':
        try:
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            if attrs != -1:
                return True
        except Exception:
            pass
    return False


def _is_valid_link(link_path: Path, expected_target: Path) -> bool:
    if not _path_exists_any(link_path):
        return False
    try:
        if link_path.is_symlink():
            target = link_path.readlink()
            return target == expected_target or target.resolve() == expected_target.resolve()
        if os.name == 'nt' and _is_junction(link_path):
            return link_path.is_dir()
        return _is_valid_mod(link_path)
    except Exception:
        return False


def _create_link(source: Path, target: Path) -> tuple[bool, str]:
    if _path_exists_any(target):
        if not _force_remove(target):
            return False, "cannot_remove_existing"

    if os.name == 'nt':
        try:
            r = subprocess.run(
                ['cmd', '/c', 'mklink', '/J', str(target), str(source)],
                capture_output=True, text=True, timeout=10, check=False)
            if _path_exists_any(target) and _is_valid_mod(target):
                return True, "junction"
            err = (r.stderr or r.stdout).strip()
            if err:
                print(f"[Link] Junction failed {source.name}: {err}")
        except Exception as e:
            print(f"[Link] Junction error {source.name}: {e}")

    try:
        target.symlink_to(source, target_is_directory=True)
        if _path_exists_any(target) and _is_valid_mod(target):
            return True, "symlink"
    except OSError as e:
        print(f"[Link] Symlink failed {source.name}: {e}")

    try:
        if _path_exists_any(target):
            _force_remove(target)
        shutil.copytree(str(source), str(target), dirs_exist_ok=True)
        if _is_valid_mod(target):
            return True, "copy"
        return False, "copy_invalid"
    except FileExistsError:
        return _path_exists_any(target), "already_exists"
    except Exception as e:
        print(f"[Link] Copy failed {source.name}: {e}")
        return False, f"copy_failed:{e}"


def _force_remove(target: Path) -> bool:
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
                            ['cmd', '/c', 'rmdir', str(target)],
                            capture_output=True, timeout=10, check=False)
                        return not _path_exists_any(target)
                    except Exception:
                        pass
            else:
                target.unlink()
                return not _path_exists_any(target)
        elif target.is_dir():
            shutil.rmtree(str(target), ignore_errors=True)
            return not _path_exists_any(target)
        elif target.is_file():
            target.unlink()
            return not _path_exists_any(target)
        else:
            if os.name == 'nt':
                subprocess.run(
                    ['cmd', '/c', 'rmdir', '/s', '/q', str(target)],
                    capture_output=True, timeout=10, check=False)
                return not _path_exists_any(target)
    except Exception as e:
        print(f"[Link] Remove failed {target.name}: {e}")

    return not _path_exists_any(target)


def _is_valid_mod(path: Path) -> bool:
    if not path.is_dir():
        return False
    for n in ('About.xml', 'about.xml'):
        if (path / 'About' / n).exists() or (path / n).exists():
            return True
    try:
        return any(path.iterdir())
    except PermissionError:
        return False


def _is_junction(path: Path) -> bool:
    if os.name != 'nt':
        return False
    try:
        import ctypes
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs == -1:
            return False
        FILE_ATTRIBUTE_REPARSE_POINT = 0x400
        return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    except Exception:
        return False