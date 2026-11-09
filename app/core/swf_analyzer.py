"""
swf_analyzer.py - High level interface for SWF inspection and item discovery.
Uses pure-Python ABC/SWF parsing without Java or external decompilers.
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import xml.etree.ElementTree as ET

from core import item_catalog

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ASSETS_XML_PATH = DATA_DIR / "assets.xml"
VALID_SWFS_PATH = DATA_DIR / "valid_swfs.json"
SWF_CACHE_DIR = DATA_DIR / "swf_cache"
SWF_CACHE_DIR.mkdir(parents=True, exist_ok=True)

PARTES_CUERPO = [
    ("hats", "Sombrero"),
    ("hats2", "Sombrero 2"),
    ("hairs", "Pelo"),
    ("hairs2", "Pelo 2"),
    ("mouths", "Boca"),
    ("mouths2", "Boca 2"),
    ("neck", "Cuello"),
    ("neck2", "Cuello 2"),
    ("accesories", "Accesorio"),
    ("accesories2", "Accesorio 2"),
    ("cloth", "Ropa"),
    ("cloth2", "Ropa 2"),
    ("clothBack", "Capa"),
    ("clothBack2", "Capa 2"),
    ("leg", "Pantalón"),
    ("leg2", "Pantalón 2"),
    ("foot", "Calzado"),
    ("foot2", "Calzado 2"),
    ("arm", "Brazo"),
    ("arm2", "Brazo 2"),
    ("grip", "Mano"),
    ("grip2", "Mano 2"),
    ("transport", "Transporte"),
    ("transport2", "Transporte 2"),
    ("effect", "Efecto"),
    ("effect2", "Efecto 2"),
]


def list_available_swfs() -> List[Dict[str, Any]]:
    """
    Catálogo de packs para thumbs/cobertura.
    Une valid_swfs.json / assets.xml con SWFs que haya en disco
    (si no, packs nuevos tipo halloween2025 nunca se indexan).
    """
    by_name: Dict[str, Dict[str, Any]] = {}

    if VALID_SWFS_PATH.exists():
        try:
            import json
            with open(VALID_SWFS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for row in data:
                        if not isinstance(row, dict):
                            continue
                        name = (row.get("name") or "").replace(".swf", "").strip()
                        if name:
                            by_name[name] = dict(row)
                            by_name[name]["name"] = name
        except Exception:
            pass

    if not by_name and ASSETS_XML_PATH.exists():
        try:
            tree = ET.parse(ASSETS_XML_PATH)
            root = tree.getroot()
            for f in root.findall(".//file"):
                p = f.attrib.get("path", "")
                if p.lower().endswith(".swf"):
                    name = p[:-4]
                    by_name[name] = {
                        "name": name,
                        "filename": p,
                        "folder": f.attrib.get("folder", "assets"),
                    }
        except Exception:
            pass

    # Merge packs on disk (CDN cache / Desktop assets / repo swfs)
    try:
        for pack in item_catalog._scan_local_swfs():
            name = (pack or "").replace(".swf", "").strip().replace("\\", "/")
            if not name or name in by_name:
                continue
            by_name[name] = {
                "name": name,
                "filename": f"{name}.swf",
                "folder": "assets",
                "source": "disk",
            }
    except Exception:
        pass

    # Enrich item_count when missing (best-effort, cached json often has it)
    out = sorted(by_name.values(), key=lambda r: str(r.get("name") or "").lower())
    return out


def inspect_swf(swf_name: str) -> Dict[str, Any]:
    swf_name = swf_name.replace(".swf", "").strip()
    if not swf_name:
        return {"ok": False, "error": "Nombre de SWF vacio"}

    try:
        pack_res = item_catalog.list_pack_items(swf_name)
        if not pack_res.get("ok"):
            return {
                "ok": False,
                "error": pack_res.get("error") or "No se pudo leer el archivo SWF",
                "swf": swf_name,
                "items": []
            }

        items = pack_res.get("items", [])
        class_list = []
        trucables = []

        for item in items:
            name = item.get("name", "")
            is_on = name.endswith("_on")
            is_asset = "Asset" in name or name.startswith("_")

            entry = {
                "id": item.get("id", name),
                "name": name,
                "full_name": item.get("item", f"{swf_name}.{name}"),
                "is_on": is_on,
                "is_asset": is_asset,
                "mambo_class": item.get("class", ""),
                "inventory": item.get("inventory", "default"),
                "inventory_label": item.get("inventory_label", "mochila"),
                "category": item.get("category", "default"),
                "animated": item.get("animated", False),
                "frameCount": item.get("frameCount", 1)
            }
            class_list.append(entry)

            if not is_on and not is_asset:
                trucables.append(entry)

        mambo_bases = []
        try:
            from core import trucador as _trucador
            mambo_bases = _trucador.list_pack_mambo_bases(swf_name)
        except Exception:
            # Fallback: unique supers seen on items.
            seen = []
            for entry in class_list:
                mc = entry.get("mambo_class") or ""
                if mc and mc not in seen:
                    seen.append(mc)
            mambo_bases = seen

        return {
            "ok": True,
            "swf": swf_name,
            "count": len(class_list),
            "trucables_count": len(trucables),
            "trucables": trucables,
            "classes": class_list,
            "mambo_bases": mambo_bases,
        }

    except Exception as e:
        return {"ok": False, "error": str(e), "swf": swf_name, "items": []}
