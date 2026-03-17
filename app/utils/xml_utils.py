import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


def parse_xml_safe(filepath: Path) -> Optional[ET.Element]:
    try:
        tree = ET.parse(str(filepath))
        return tree.getroot()
    except (ET.ParseError, FileNotFoundError, PermissionError):
        return None


def get_text(element: Optional[ET.Element], tag: str, default: str = '') -> str:
    if element is None:
        return default
    child = element.find(tag)
    return child.text.strip() if child is not None and child.text else default


def get_list(element: Optional[ET.Element], tag: str) -> list[str]:
    if element is None:
        return []
    parent = element.find(tag)
    if parent is None:
        return []
    return [li.text.strip() for li in parent.findall('li') if li.text]