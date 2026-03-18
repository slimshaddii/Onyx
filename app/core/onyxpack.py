"""
.onyx format — Onyx Launcher modpack sharing.
ZIP-based: manifest.json + modlist.json + load_order.json + optional config/icon.
"""

import json
import zipfile
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

from app.core.instance import Instance
from app.core.rimworld import ModInfo

ONYX_FORMAT_VERSION = 1
ONYX_VERSION        = "1.0"
ONYX_EXTENSION      = ".onyx"
ONYX_MAGIC          = "onyx-modpack-v1"


@dataclass
class OnyxManifest:
    format_version: int  = ONYX_FORMAT_VERSION
    magic: str           = ONYX_MAGIC
    name: str            = ''
    author: str          = ''
    description: str     = ''
    created: str         = ''
    rimworld_version: str = ''
    mod_count: int       = 0
    onyx_version: str    = ONYX_VERSION


@dataclass
class OnyxMod:
    id:          str
    name:        str
    workshop_id: str  = ''
    source:      str  = ''
    required:    bool = True


@dataclass
class OnyxPreview:
    manifest:        OnyxManifest
    mods:            list[OnyxMod]
    load_order:      list[str]
    has_config:      bool          = False
    has_icon:        bool          = False
    missing_mods:    list[OnyxMod] = field(default_factory=list)
    installed_mods:  list[OnyxMod] = field(default_factory=list)
    valid:           bool          = True
    error:           str           = ''


# ── Export ─────────────────────────────────────────────────────────────────────

def export_onyx(instance: Instance, output_path: Path,
                all_mods: dict[str, ModInfo],
                include_config: bool = False,
                author: str = '',
                description: str = '') -> tuple[bool, str]:
    """Export an instance as a .onyx ZIP file."""
    try:
        manifest = {
            'format_version': ONYX_FORMAT_VERSION,
            'magic':           ONYX_MAGIC,
            'name':            instance.name,
            'author':          author,
            'description':     description or instance.notes or '',
            'created':         datetime.now().isoformat(),
            'rimworld_version': instance.rimworld_version or '',
            'mod_count':       len(instance.mods),
            'onyx_version':    ONYX_VERSION,
        }

        def _mod_entry(mid: str, required: bool) -> dict:
            info = all_mods.get(mid)
            return {
                'id':          mid,
                'name':        info.name        if info else mid,
                'workshop_id': info.workshop_id if info else '',
                'source':      info.source      if info else 'unknown',
                'required':    required,
            }

        mods = (
            [_mod_entry(mid, True)  for mid in instance.mods] +
            [_mod_entry(mid, False) for mid in instance.inactive_mods]
        )

        with zipfile.ZipFile(str(output_path), 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('manifest.json',   json.dumps(manifest,            indent=2))
            zf.writestr('modlist.json',    json.dumps({'mods': mods},      indent=2))
            zf.writestr('load_order.json', json.dumps(list(instance.mods), indent=2))

            if include_config and instance.config_dir.exists():
                for cf in instance.config_dir.iterdir():
                    if cf.is_file():
                        zf.write(str(cf), f'config/{cf.name}')

            for ext in ('png', 'jpg', 'jpeg', 'ico'):
                icon_path = instance.path / f'icon.{ext}'
                if icon_path.exists():
                    zf.write(str(icon_path), f'icon.{ext}')
                    break

        total = len(instance.mods) + len(instance.inactive_mods)
        return (True,
                f"Exported {total} mods "
                f"({len(instance.mods)} active) to {output_path.name}")
    except Exception as e:
        return False, f"Export failed: {e}"


# ── Peek (read without extract) ────────────────────────────────────────────────

def peek_onyx(path: Path) -> OnyxPreview:
    """Read a .onyx file's metadata without full extraction."""
    preview = OnyxPreview(manifest=OnyxManifest(), mods=[], load_order=[])

    try:
        if not path.exists():
            preview.valid = False
            preview.error = "File not found"
            return preview

        if not zipfile.is_zipfile(str(path)):
            preview.valid = False
            preview.error = "Not a valid .onyx file"
            return preview

        with zipfile.ZipFile(str(path), 'r') as zf:
            names = zf.namelist()

            if 'manifest.json' not in names:
                preview.valid = False
                preview.error = "Missing manifest.json — not a valid .onyx pack"
                return preview

            md = json.loads(zf.read('manifest.json'))

            # Always validate the magic field — reject unknown or missing values
            if md.get('magic') != ONYX_MAGIC:
                preview.valid = False
                preview.error = (
                    f"Unknown or missing magic: '{md.get('magic', '<none>')}'"
                    f" (expected '{ONYX_MAGIC}')")
                return preview

            preview.manifest = OnyxManifest(
                format_version=md.get('format_version', 0),
                magic=md.get('magic', ''),
                name=md.get('name', ''),
                author=md.get('author', ''),
                description=md.get('description', ''),
                created=md.get('created', ''),
                rimworld_version=md.get('rimworld_version', ''),
                mod_count=md.get('mod_count', 0),
                onyx_version=md.get('onyx_version', ''),
            )

            if 'modlist.json' in names:
                ml = json.loads(zf.read('modlist.json'))
                for m in ml.get('mods', []):
                    preview.mods.append(OnyxMod(
                        id=m.get('id', ''),
                        name=m.get('name', ''),
                        workshop_id=m.get('workshop_id', ''),
                        source=m.get('source', ''),
                        required=m.get('required', True),
                    ))

            if 'load_order.json' in names:
                preview.load_order = json.loads(zf.read('load_order.json'))

            preview.has_config = any(n.startswith('config/') for n in names)
            preview.has_icon   = any(n.startswith('icon.')   for n in names)

    except json.JSONDecodeError as e:
        preview.valid = False
        preview.error = f"Invalid JSON in pack: {e}"
    except zipfile.BadZipFile:
        preview.valid = False
        preview.error = "Corrupted .onyx file"
    except Exception as e:
        preview.valid = False
        preview.error = f"Error reading pack: {e}"

    return preview


# ── Mod availability check ─────────────────────────────────────────────────────

def check_onyx_mods(preview: OnyxPreview,
                    installed_mods: dict[str, ModInfo]) -> OnyxPreview:
    """Partition preview.mods into installed_mods / missing_mods."""
    preview.installed_mods = []
    preview.missing_mods   = []
    for mod in preview.mods:
        if mod.id in installed_mods:
            preview.installed_mods.append(mod)
        else:
            preview.missing_mods.append(mod)
    return preview


# ── Import ─────────────────────────────────────────────────────────────────────

def import_onyx(onyx_path: Path,
                instance_manager,
                instance_name: str,
                install_config: bool = True
                ) -> tuple[Optional[Instance], list[OnyxMod], str]:
    """
    Import a .onyx pack as a new instance.

    Returns (instance, missing_mods, error_string).
    On failure, instance is None and error_string is non-empty.
    """
    preview = peek_onyx(onyx_path)
    if not preview.valid:
        return None, [], preview.error

    try:
        # Active mods come from load_order; inactive from required=False entries
        active_ids = (preview.load_order
                      if preview.load_order
                      else [m.id for m in preview.mods if m.required])
        active_set   = set(active_ids)
        inactive_ids = [m.id for m in preview.mods
                        if not m.required and m.id not in active_set]

        notes = "\n".join(filter(None, [
            f"Imported from: {onyx_path.name}",
            f"Author: {preview.manifest.author}" if preview.manifest.author else '',
            preview.manifest.description,
        ]))

        # create_instance writes ModsConfig.xml internally
        inst = instance_manager.create_instance(
            name=instance_name,
            mods=active_ids,
            version=preview.manifest.rimworld_version or '1.6',
            notes=notes.strip(),
        )

        inst.inactive_mods = inactive_ids
        inst.save()

        # Extract optional config files
        if install_config and preview.has_config:
            with zipfile.ZipFile(str(onyx_path), 'r') as zf:
                for name in zf.namelist():
                    if name.startswith('config/') and len(name) > len('config/'):
                        filename = name[len('config/'):]
                        target   = inst.config_dir / filename
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(zf.read(name))

        # Extract optional icon
        if preview.has_icon:
            with zipfile.ZipFile(str(onyx_path), 'r') as zf:
                for name in zf.namelist():
                    if name.startswith('icon.'):
                        ext    = name.rsplit('.', 1)[-1]
                        target = inst.path / f'icon.{ext}'
                        target.write_bytes(zf.read(name))
                        break

        return inst, preview.missing_mods, ''

    except FileExistsError:
        return None, [], f"Instance '{instance_name}' already exists"
    except Exception as e:
        return None, [], f"Import failed: {e}"