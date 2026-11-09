"""
Filtro temático de packs/objetos por palabras clave en el nombre.

Mundo Gaturro ya agrupa mucho por pack (halloweenClothes, navidad2017/wears…).
Esto no usa IA: es rápido y bastante preciso para eventos/temas conocidos.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# id → label + keywords (pack name / item name)
THEMES: List[Dict[str, Any]] = [
    {
        "id": "halloween",
        "label": "Halloween",
        "emoji": "🎃",
        "keywords": [
            "halloween", "hallo", "fantasma", "vamp", "zombie", "zombies",
            "bruj", "calabaza", "murcielago", "esqueleto", "momia", "terror",
            "mansionembrujada", "dracula", "franken",
        ],
    },
    {
        "id": "navidad",
        "label": "Navidad",
        "emoji": "🎄",
        "keywords": [
            "navidad", "christmas", "xmas", "noel", "papa", "reno", "elfo",
            "snow", "nieve", "invierno", "ginger", "regalo", "santa",
        ],
    },
    {
        "id": "pascua",
        "label": "Pascua",
        "emoji": "🐣",
        "keywords": ["pascua", "pascuas", "conejo", "huevo", "easter", "chick"],
    },
    {
        "id": "sanvalentin",
        "label": "San Valentín",
        "emoji": "💕",
        "keywords": [
            "sanval", "sanvalentin", "valent", "amor", "corazon", "heart",
            "cupido", "romance", "tuneldelamor",
        ],
    },
    {
        "id": "piratas",
        "label": "Piratas",
        "emoji": "🏴‍☠️",
        "keywords": ["pirata", "piratas", "barco", "tesoro", "isla", "corsario"],
    },
    {
        "id": "espacial",
        "label": "Espacial",
        "emoji": "🚀",
        "keywords": [
            "espacial", "space", "alien", "ovni", "astronaut", "planeta",
            "galaxia", "extraterrestre", "jetpack",
        ],
    },
    {
        "id": "mundial",
        "label": "Mundial / Deporte",
        "emoji": "⚽",
        "keywords": [
            "mundial", "futbol", "football", "copa", "gol", "deporte",
            "olimpi", "basket", "tenis", "decathlon",
        ],
    },
    {
        "id": "playa",
        "label": "Playa / Verano",
        "emoji": "🏖️",
        "keywords": [
            "playa", "verano", "summer", "bikini", "surf", "mar", "arena",
            "tropical", "piscina",
        ],
    },
    {
        "id": "fiesta",
        "label": "Fiesta / Cumple",
        "emoji": "🎉",
        "keywords": [
            "fiesta", "cumple", "aniversario", "party", "disco", "baile",
            "confeti",
        ],
    },
    {
        "id": "egipto",
        "label": "Egipto",
        "emoji": "🏺",
        "keywords": ["egipto", "egypt", "faraon", "piramide", "cleopatra", "momia"],
    },
    {
        "id": "anime",
        "label": "Anime / Otaku",
        "emoji": "✨",
        "keywords": ["anime", "manga", "otaku", "kawaii", "neko", "sakura"],
    },
    {
        "id": "fantasia",
        "label": "Fantasía",
        "emoji": "🪄",
        "keywords": [
            "fantasia", "mago", "hada", "dragon", "unicornio", "castillo",
            "princesa", "caballero", "medieval", "varita",
        ],
    },
]


def _norm(text: str) -> str:
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum() or ch in "._-/")


def theme_by_id(theme_id: str) -> Optional[Dict[str, Any]]:
    tid = (theme_id or "").strip().lower()
    for t in THEMES:
        if t["id"] == tid:
            return t
    return None


def match_theme(text: str, theme: Dict[str, Any]) -> bool:
    hay = _norm(text)
    if not hay:
        return False
    for kw in theme.get("keywords") or []:
        if _norm(kw) in hay:
            return True
    return False


def detect_themes(text: str) -> List[str]:
    return [t["id"] for t in THEMES if match_theme(text, t)]


def pack_matches_theme(pack_name: str, theme_id: str) -> bool:
    theme = theme_by_id(theme_id)
    if not theme:
        return True
    return match_theme(pack_name, theme)


def item_matches_theme(pack_name: str, item_name: str, theme_id: str) -> bool:
    theme = theme_by_id(theme_id)
    if not theme:
        return True
    # Si el pack ya es del tema, todos sus items cuentan.
    if match_theme(pack_name, theme):
        return True
    return match_theme(item_name, theme)


def list_themes(pack_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    packs = pack_names or []
    out = []
    for t in THEMES:
        count = sum(1 for p in packs if match_theme(p, t)) if packs else 0
        out.append({
            "id": t["id"],
            "label": t["label"],
            "emoji": t.get("emoji") or "",
            "pack_count": count,
            "keywords": list(t["keywords"][:8]),
        })
    out.sort(key=lambda row: (-row["pack_count"], row["label"]))
    return out


def filter_packs(pack_names: List[str], theme_id: str = "", q: str = "") -> List[str]:
    theme = theme_by_id(theme_id) if theme_id else None
    qn = (q or "").strip().lower()
    results = []
    for raw in pack_names:
        name = str(raw or "").replace(".swf", "").strip()
        if not name:
            continue
        if theme and not match_theme(name, theme):
            continue
        if qn and qn not in name.lower():
            continue
        results.append(name)
    return results
