"""
Debug script to check what's actually being written to your instance.
"""

from pathlib import Path
import json
import xml.etree.ElementTree as ET

# ═══════════════════════════════════════════════════════════════════
# CONFIGURE THIS
# ═══════════════════════════════════════════════════════════════════
INSTANCE_NAME = "Instance 2"  # Change to your instance name
INSTANCES_DIR = Path("instances")  # Adjust if different

instance_path = INSTANCES_DIR / INSTANCE_NAME

print("="*80)
print(f"DIAGNOSING INSTANCE: {INSTANCE_NAME}")
print("="*80)

# ───────────────────────────────────────────────────────────────────
# 1. Check instance.json
# ───────────────────────────────────────────────────────────────────
instance_json = instance_path / "instance.json"

if not instance_json.exists():
    print(f"\n✗ instance.json NOT FOUND at: {instance_json}")
    exit(1)

print(f"\n✓ Found instance.json")

with open(instance_json, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"\n[instance.json]")
print(f"  Name: {data.get('name')}")
print(f"  Version: {data.get('rimworld_version')}")
print(f"  Active mods: {len(data.get('mods', []))}")
print(f"  Inactive mods: {len(data.get('inactive_mods', []))}")

active_mods = data.get('mods', [])
print(f"\n  First 10 active mods:")
for i, mod in enumerate(active_mods[:10], 1):
    print(f"    {i}. {mod}")

# ───────────────────────────────────────────────────────────────────
# 2. Check ModsConfig.xml
# ───────────────────────────────────────────────────────────────────
modsconfig_xml = instance_path / "Config" / "ModsConfig.xml"

if not modsconfig_xml.exists():
    print(f"\n✗ ModsConfig.xml NOT FOUND at: {modsconfig_xml}")
else:
    print(f"\n✓ Found ModsConfig.xml")
    
    tree = ET.parse(modsconfig_xml)
    root = tree.getroot()
    
    version = root.find('version')
    print(f"\n[ModsConfig.xml]")
    print(f"  Version: {version.text if version is not None else 'MISSING'}")
    
    active = root.find('activeMods')
    if active is not None:
        xml_mods = [li.text for li in active.findall('li') if li.text]
        print(f"  Active mods: {len(xml_mods)}")
        
        print(f"\n  First 10 mods in XML:")
        for i, mod in enumerate(xml_mods[:10], 1):
            print(f"    {i}. {mod}")
        
        # Compare with instance.json
        if set(xml_mods) != set(active_mods):
            print(f"\n  ⚠ MISMATCH between instance.json and ModsConfig.xml!")
            
            in_json_not_xml = set(active_mods) - set(xml_mods)
            in_xml_not_json = set(xml_mods) - set(active_mods)
            
            if in_json_not_xml:
                print(f"\n  In instance.json but NOT in XML:")
                for mod in list(in_json_not_xml)[:5]:
                    print(f"    - {mod}")
            
            if in_xml_not_json:
                print(f"\n  In XML but NOT in instance.json:")
                for mod in list(in_xml_not_json)[:5]:
                    print(f"    - {mod}")
    else:
        print(f"  ✗ No <activeMods> section!")
    
    print(f"\n[RAW XML CONTENT]")
    print("-"*80)
    with open(modsconfig_xml, 'r', encoding='utf-8') as f:
        print(f.read())
    print("-"*80)

# ───────────────────────────────────────────────────────────────────
# 3. Check if mods exist in game folder
# ───────────────────────────────────────────────────────────────────
print(f"\n[CHECKING GAME MODS FOLDER]")
print("  Where is your RimWorld installation?")
print("  (Enter the path to RimWorld folder, e.g., C:\\RimWorld)")
game_path = input("  > ").strip()

if game_path:
    game_mods = Path(game_path) / "Mods"
    if game_mods.exists():
        print(f"\n  ✓ Game mods folder: {game_mods}")
        
        missing = []
        for mod_id in active_mods[:20]:
            # Try to find this mod
            found = False
            for folder in game_mods.iterdir():
                if folder.is_dir():
                    about_xml = folder / "About" / "About.xml"
                    if about_xml.exists():
                        try:
                            tree = ET.parse(about_xml)
                            root = tree.getroot()
                            pkg_id = root.find('packageId')
                            if pkg_id is not None and pkg_id.text:
                                if pkg_id.text.lower() == mod_id.lower():
                                    found = True
                                    break
                        except:
                            pass
            
            if not found:
                missing.append(mod_id)
        
        if missing:
            print(f"\n  ⚠ {len(missing)} mods NOT FOUND in game folder:")
            for mod in missing[:10]:
                print(f"    ! {mod}")
        else:
            print(f"\n  ✓ All checked mods found in game folder")
    else:
        print(f"\n  ✗ Mods folder not found: {game_mods}")

print("\n" + "="*80)
print("DIAGNOSIS COMPLETE")
print("="*80)