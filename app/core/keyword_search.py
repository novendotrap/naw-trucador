"""
Búsqueda de objetos por palabra (cross-pack).

Usa el índice de thumbs + keywords de theme_tags.
Ej: q="halloween" → objetos de packs/nombres que matchean el tema,
no la lista de archivos SWF.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from core import theme_tags, thumb_store

_JUNK = {
    "catalogbtn", "btn", "button", "loading", "loader", "placeholder",
    "iconloading", "empty", "null", "undefined",
}
_PACK_ONLY_CAP = 10  # diversificar cuando el match es solo por pack/tema

# Sinónimos ES/EN frecuentes que no están en el nombre del pack
_ALIASES = {
    "griego": ["greek", "griego", "grecia"],
    "grecia": ["greek", "griego", "grecia"],
    "greek": ["greek", "griego", "grecia"],
    "marmol": ["marble", "marmol", "greek"],
    "antorcha": ["antorcha", "torch", "vela"],
    "brasero": ["brasero", "fuego", "fuente", "vela"],
}


def _tokens_from_query(q: str) -> List[str]:
    raw = (q or "").strip().lower()
    if not raw:
        return []
    parts = [raw]
    parts.extend(p for p in re.split(r"[\s,/_|+.-]+", raw) if len(p) >= 2)
    # Expandir si la query es un tema conocido (id o label)
    theme = theme_tags.theme_by_id(raw)
    if not theme:
        for t in theme_tags.THEMES:
            label = str(t.get("label") or "").lower()
            if label == raw or raw in label or label.startswith(raw):
                theme = t
                break
    if theme:
        # Keywords cortas ("papa", "snow") ensucian mucho: mínimo 4 chars.
        parts.extend(
            str(k).lower()
            for k in (theme.get("keywords") or [])
            if len(str(k).strip()) >= 4
        )
    # Expandir sinónimos conocidos
    for p in list(parts):
        parts.extend(_ALIASES.get(p) or [])
    # únicos preservando orden
    seen = set()
    out = []
    for p in parts:
        p = p.strip().lower()
        if len(p) < 2:
            continue
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _score_item(pack: str, name: str, tokens: List[str]) -> tuple[int, str]:
    """Devuelve (score, match_kind). kind: name | pack | none."""
    pl = pack.lower()
    nl = name.lower()
    pn = theme_tags._norm(pack)
    nn = theme_tags._norm(name)
    best = 0
    kind = "none"
    for tok in tokens:
        tn = theme_tags._norm(tok)
        if not tn:
            continue
        # nombre exacto / prefijo / substring
        if nl == tok or nn == tn:
            if 100 > best:
                best, kind = 100, "name"
        elif nl.startswith(tok) or nn.startswith(tn):
            if 85 > best:
                best, kind = 85, "name"
        elif tok in nl or tn in nn:
            # evitar matches demasiado cortos dentro de nombres largos
            if len(tok) >= 3 or len(nl) <= 8:
                if 70 > best:
                    best, kind = 70, "name"
        # pack
        elif tok in pl or tn in pn:
            if 40 > best:
                best, kind = 40, "pack"
        elif pl.startswith(tok) or pn.startswith(tn):
            if 45 > best:
                best, kind = 45, "pack"
    return best, kind


def search_by_keyword(
    q: str,
    theme: str = "",
    limit: int = 80,
) -> List[Dict[str, Any]]:
    tokens = _tokens_from_query(q)
    if not tokens:
        return []

    theme_id = (theme or "").strip().lower()
    if theme_id in ("", "todos", "all"):
        theme_id = ""

    items = thumb_store.list_items()
    scored: List[Dict[str, Any]] = []
    pack_only_counts: Dict[str, int] = {}

    for it in items:
        pack = str(it.get("pack") or "")
        name = str(it.get("name") or "")
        if not pack or not name:
            continue
        if name.lower() in _JUNK:
            continue
        if theme_id and not (
            theme_tags.pack_matches_theme(pack, theme_id)
            or theme_tags.item_matches_theme(pack, name, theme_id)
        ):
            continue

        score, kind = _score_item(pack, name, tokens)
        if score <= 0:
            continue

        if kind == "pack":
            n = pack_only_counts.get(pack, 0)
            if n >= _PACK_ONLY_CAP:
                continue
            pack_only_counts[pack] = n + 1

        scored.append({
            "pack": pack,
            "name": name,
            "score": score / 100.0,
            "match": kind,
            "thumb_url": f"/api/thumbs/file?pack={pack}&name={name}",
            "engine": "keyword",
        })

    # name matches first, then pack; tie-break by name
    scored.sort(key=lambda r: (-r["score"], 0 if r["match"] == "name" else 1, r["name"].lower()))
    top = scored[: max(1, min(int(limit or 80), 200))]
    for row in top:
        row["score"] = round(float(row["score"]), 4)
    return top
