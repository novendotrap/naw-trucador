"""
catalog_db.py - Store and catalog database management.
Provides quick access to the 82 discovered stores and categorized SWF packages.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BEHAVIORS_PATH = DATA_DIR / "behaviors.json"
TIENDAS_PATH = DATA_DIR / "tiendas_catalogs.json"

CATEGORIES = {
    "ropa": ["costumes", "clothes", "wears", "shoes", "remeras", "vestidos", "pijamada", "animeClothes", "moda"],
    "sombreros": ["hats", "gorros", "sombreros", "pelucas", "hairs"],
    "accesorios": ["accesories", "anteojos", "collares", "alas", "mascaras"],
    "armas_agarre": ["weapons", "espadas", "varitas", "baston"],
    "casa_muebles": ["house", "beds", "furniture", "bathroom", "kitchen", "decoracion", "navidad", "halloween"],
    "transporte": ["transport", "autos", "motos", "skate", "patines", "vehiculos"],
    "mascotas": ["pets", "gaturros", "dragones", "animales"],
    "eventos": ["aniversario", "halloween", "pascua", "mundial", "navidad", "copaAmérica"]
}


def load_behaviors() -> List[Dict[str, Any]]:
    if BEHAVIORS_PATH.exists():
        try:
            with open(BEHAVIORS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    if TIENDAS_PATH.exists():
        try:
            with open(TIENDAS_PATH, "r", encoding="utf-8") as f:
                items = json.load(f)
                out = []
                for it in items:
                    beh = it.get("behavior", "")
                    cats = [c.get("name") for c in it.get("catalogs", []) if isinstance(c, dict)]
                    out.append({
                        "id": beh.replace("/", "_"),
                        "behavior": beh,
                        "title": beh.replace("/", " - ").title(),
                        "desc": "Behavior interactivo del juego.",
                        "category": "General",
                        "type": "catalog" if cats else "vendor",
                        "catalogs": cats,
                        "script": ""
                    })
                return out
        except Exception:
            pass
    return []


def search_behaviors(query: str = "", btype: str = "") -> List[Dict[str, Any]]:
    all_b = load_behaviors()
    q = query.lower().strip()
    bt = (btype or "").lower().strip()
    results = []
    for item in all_b:
        if bt and bt != "all" and item.get("type", "").lower() != bt:
            continue
        if not q:
            results.append(item)
            continue
        beh = item.get("behavior", "").lower()
        title = item.get("title", "").lower()
        desc = item.get("desc", "").lower()
        cat = item.get("category", "").lower()
        cats = [str(c).lower() for c in item.get("catalogs", [])]
        samples = [str(s).lower() for s in item.get("items_sample", [])]
        if q in beh or q in title or q in desc or q in cat or any(q in c for c in cats) or any(q in s for s in samples):
            results.append(item)
    return results


# Compatibilidad hacia atrás
load_tiendas = load_behaviors
search_tiendas = search_behaviors


def categorize_swf(swf_name: str) -> str:
    name_low = swf_name.lower()
    for cat, keywords in CATEGORIES.items():
        if any(kw.lower() in name_low for kw in keywords):
            return cat
    return "otros"
