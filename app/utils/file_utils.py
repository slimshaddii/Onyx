"""
File-system utility functions used across the Onyx Launcher codebase.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path


# ── Directory Operations ──────────────────────────────────────────────────────

def ensure_dir(path: Path) -> None:
    """Create the directory and parents if they do not exist."""
    path.mkdir(parents=True, exist_ok=True)


def safe_copy_tree(src: Path, dst: Path) -> None:
    """Remove dst if it exists, then copy src to dst."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(str(src), str(dst))


def safe_delete_tree(path: Path) -> None:
    """Remove an entire directory tree if it exists."""
    if path.exists():
        shutil.rmtree(str(path))


# ── Size Utilities ────────────────────────────────────────────────────────────

def get_folder_size(path: Path) -> int:
    """Return total size in bytes of all files under path."""
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


def human_size(num_bytes: float) -> str:
    """Return a human-readable size string (e.g. '12.3 MB')."""
    for unit in ('B', 'KB', 'MB', 'GB'):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


# ── Backup ────────────────────────────────────────────────────────────────────

def backup_folder(
        src: Path,
        backup_root: Path,
        max_backups: int = 3,
) -> None:
    """
    Copy *src* into *backup_root* with a timestamped name.

    Keeps only the *max_backups* most-recent backup_* directories;
    non-backup entries in backup_root are never touched.
    """
    ensure_dir(backup_root)
    if not src.exists():
        return

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"backup_{timestamp}"
    shutil.copytree(str(src), str(backup_path))

    backups = sorted(
        [p for p in backup_root.iterdir()
         if p.is_dir() and p.name.startswith('backup_')],
        key=lambda p: p.name,
    )
    while len(backups) > max_backups:
        shutil.rmtree(str(backups.pop(0)))


# ── JSON I/O ──────────────────────────────────────────────────────────────────

def load_json(path: Path, default=None):
    """Load and return parsed JSON from path, or default on failure."""
    if path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default if default is not None else {}
    return default if default is not None else {}


def save_json(path: Path, data) -> None:
    """Atomically write data as JSON to path via temp file."""
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + '.tmp')
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # json.dump + file ops can raise heterogeneous
        # exceptions (TypeError, OSError, ValueError);
        # must clean up the temp file in all cases
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Failed to save {path.name}: {exc}"
        ) from exc
