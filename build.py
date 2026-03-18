"""
Onyx Launcher build script.
Usage:
    python build.py           # Build for current platform
    python build.py --clean   # Clean previous build first
    python build.py --no-zip  # Build but don't zip
"""

import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path


APP_NAME    = "OnyxLauncher-Beta"
DIST_DIR    = Path("dist")
BUILD_DIR   = Path("build")
SPEC_FILE   = "main.spec"
OUTPUT_DIR  = DIST_DIR / APP_NAME


def clean():
    print("[Build] Cleaning previous build…")
    for d in (DIST_DIR, BUILD_DIR):
        if d.exists():
            shutil.rmtree(d)
            print(f"  Removed {d}/")


def convert_icon():
    """Convert onyx_icon.png to .ico if needed (Windows only)."""
    if sys.platform != 'win32':
        return
    ico = Path("app/ui/resources/onyx_icon.ico")
    png = Path("app/ui/resources/onyx_icon.png")
    if ico.exists():
        print(f"[Build] Icon found: {ico}")
        return
    if not png.exists():
        print("[Build] WARNING: No icon found at app/ui/resources/onyx_icon.png")
        return
    try:
        from PIL import Image
        img = Image.open(png)
        img.save(str(ico), format='ICO',
                 sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
        print(f"[Build] Converted {png} → {ico}")
    except ImportError:
        print("[Build] WARNING: Pillow not installed — "
              "cannot auto-convert icon. "
              "Install with: pip install Pillow")
    except Exception as e:
        print(f"[Build] WARNING: Icon conversion failed: {e}")


def build():
    print(f"[Build] Building {APP_NAME} for {sys.platform}…")
    result = subprocess.run(
        [sys.executable, '-m', 'PyInstaller',
         '--noconfirm',
         SPEC_FILE],
        check=False)
    if result.returncode != 0:
        print("[Build] ERROR: PyInstaller failed.")
        sys.exit(result.returncode)
    print("[Build] PyInstaller done.")


def verify():
    if not OUTPUT_DIR.exists():
        print(f"[Build] ERROR: Expected output not found: {OUTPUT_DIR}")
        sys.exit(1)

    # Check executable exists
    if sys.platform == 'win32':
        exe = OUTPUT_DIR / 'OnyxLauncher.exe'
    elif sys.platform == 'darwin':
        exe = OUTPUT_DIR / 'OnyxLauncher'
    else:
        exe = OUTPUT_DIR / 'OnyxLauncher'

    if not exe.exists():
        print(f"[Build] ERROR: Executable not found: {exe}")
        sys.exit(1)

    print(f"[Build] Verified: {exe}")


def make_zip():
    # Name zip with platform suffix
    if sys.platform == 'win32':
        platform_tag = 'windows'
    elif sys.platform == 'darwin':
        platform_tag = 'macos'
    else:
        platform_tag = 'linux'

    zip_name = DIST_DIR / f"{APP_NAME}-{platform_tag}.zip"

    print(f"[Build] Creating {zip_name}…")
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        for file in OUTPUT_DIR.rglob('*'):
            if file.is_file():
                arcname = Path(APP_NAME) / file.relative_to(OUTPUT_DIR)
                zf.write(file, arcname)

    size_mb = zip_name.stat().st_size / (1024 * 1024)
    print(f"[Build] ZIP created: {zip_name} ({size_mb:.1f} MB)")
    return zip_name


def main():
    args = sys.argv[1:]
    do_clean  = '--clean'  in args
    do_zip    = '--no-zip' not in args

    if do_clean:
        clean()

    convert_icon()
    build()
    verify()

    if do_zip:
        zip_path = make_zip()
        print(f"\n[Build] Done — distribute: {zip_path}")
    else:
        print(f"\n[Build] Done — folder: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()