import shutil
import os
import json
from pathlib import Path
from datetime import datetime


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def safe_copy_tree(src: Path, dst: Path):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(str(src), str(dst))


def safe_delete_tree(path: Path):
    if path.exists():
        shutil.rmtree(str(path))


def get_folder_size(path: Path) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


def human_size(num_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def backup_folder(src: Path, backup_root: Path, max_backups: int = 3):
    ensure_dir(backup_root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"backup_{timestamp}"
    if src.exists():
        shutil.copytree(str(src), str(backup_path))

    backups = sorted(backup_root.iterdir(), key=lambda p: p.name)
    while len(backups) > max_backups:
        shutil.rmtree(str(backups.pop(0)))


def load_json(path: Path, default=None):
    if path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default if default is not None else {}
    return default if default is not None else {}


def save_json(path: Path, data):
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + '.tmp')
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to save {path.name}: {e}") from e