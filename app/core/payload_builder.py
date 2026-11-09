"""
payload_builder.py - Generates and validates Mundo Gaturro NPC script payloads.
Used for Lola NPC interception and item acquisition.
"""

import base64
import re
from typing import List, Dict, Any, Union


def add_options_line(item_name: str, attrs: Dict[str, Any], qty: int = 1) -> str:
    """inventory.addOptions pack.item N \" \" {wear_*} — same encode as Consola."""
    clean = str(item_name or "").strip()
    try:
        amount = max(1, int(qty or 1))
    except (TypeError, ValueError):
        amount = 1
    pairs = []
    if isinstance(attrs, dict):
        for key, value in attrs.items():
            k = str(key).strip()
            if not k:
                continue
            v = "" if value is None else str(value)
            v = v.replace("\\", "\\\\").replace('"', '\\"')
            pairs.append(f'"{k}":"{v}"')
    body = "{" + ",".join(pairs) + "}"
    return f'inventory.addOptions "{clean}" {amount} " " {body}'


def build_npc_add_options(item_name: str, attrs: Dict[str, Any], qty: int = 1) -> str:
    line = add_options_line(item_name, attrs, qty)
    return (
        "initial: DO\r\n"
        "    on activate A1\r\n\r\n"
        "INICIO: DO\r\n"
        "    on activate A1\r\n\r\n"
        "A1: DO\r\n"
        "    user.state get\r\n"
        f"    {line}\r\n"
        "    after 1 initial\r\n"
    )


def build_npc_payload(items: List[Dict[str, Any]]) -> str:
    if not items:
        return (
            "initial: DO\r\n"
            "    on activate A1\r\n\r\n"
            "INICIO: DO\r\n"
            "    on activate A1\r\n\r\n"
            "A1: DO\r\n"
            "    user.state get\r\n"
            "    after 1 initial\r\n"
        )

    lines = [
        "initial: DO",
        "    on activate A1",
        "",
        "INICIO: DO",
        "    on activate A1",
        ""
    ]
    count = len(items)

    for i, it in enumerate(items):
        sec_num = i + 1
        next_sec = f"A{sec_num + 1}" if sec_num < count else "initial"
        
        raw_name = str(it.get("name") or it.get("item") or "").strip()
        swf_prefix = str(it.get("swf") or "").strip()
        
        if swf_prefix and "." not in raw_name:
            full_name = f"{swf_prefix}.{raw_name}"
        else:
            full_name = raw_name

        try:
            qty = max(1, int(it.get("qty") or it.get("amount") or 1))
        except (ValueError, TypeError):
            qty = 1

        options = it.get("options") or it.get("custom_attrs")
        lines.append(f"A{sec_num}: DO")
        lines.append("    user.state get")
        if options and isinstance(options, dict):
            line = add_options_line(full_name, options, qty)
            lines.append(f"    {line}")
        else:
            lines.append(f"    inventory.add {qty} {full_name}")
        lines.append(f"    after 1 {next_sec}")
        lines.append("")

    return "\r\n".join(lines).strip() + "\r\n"


def encode_payload_b64(payload_text: str) -> str:
    return base64.b64encode(payload_text.encode("utf-8")).decode("utf-8")


def decode_payload_b64(b64_string: str) -> str:
    try:
        return base64.b64decode(b64_string.strip().encode("utf-8")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def extract_items_from_npc_payload(payload_text: str) -> List[Dict[str, Any]]:
    """
    Parses an existing NPC script (e.g. lola.npc) and extracts ONLY valid items
    added via 'inventory.add <qty> <item_name>'.
    Ignores all script control flow keywords (INICIO, DO, activate, user.state, after, etc.)
    """
    items = []
    seen = set()
    invalid_prefixes = {
        "inventory", "user", "state", "after", "on", "activate", "inicio", "initial",
        "do", "get", "define", "private", "session", "shared", "stored", "say", "goto", "minigame", "fork"
    }

    for line in payload_text.splitlines():
        line = line.strip()
        if line.startswith("inventory.addOptions"):
            match = re.search(
                r'inventory\.addOptions\s+"?([^\s"]+)"?\s+(\d+)',
                line,
            )
            if not match:
                continue
            full_name = match.group(1).strip()
            try:
                qty = max(1, int(match.group(2)))
            except (ValueError, TypeError):
                qty = 1
            if "." not in full_name:
                continue
            swf_part, obj_part = full_name.split(".", 1)
            if swf_part.lower() in invalid_prefixes or obj_part.lower() in invalid_prefixes:
                continue
            if full_name not in seen:
                seen.add(full_name)
                items.append({
                    "swf": swf_part,
                    "item": obj_part,
                    "name": full_name,
                    "qty": qty
                })
            continue

        if line.startswith("inventory.add"):
            parts = line.split()
            if len(parts) >= 3:
                try:
                    qty = max(1, int(parts[1]))
                except (ValueError, TypeError):
                    qty = 1
                full_name = parts[-1].strip().strip('"')
                if "." not in full_name:
                    continue
                swf_part, obj_part = full_name.split(".", 1)
                if swf_part.lower() in invalid_prefixes or obj_part.lower() in invalid_prefixes:
                    continue
                if full_name not in seen:
                    seen.add(full_name)
                    items.append({
                        "swf": swf_part,
                        "item": obj_part,
                        "name": full_name,
                        "qty": qty
                    })
    return items


def parse_item_list_from_text(raw_text: str) -> List[Dict[str, Any]]:
    items = []
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    
    for line in lines:
        if line.startswith("#") or line.startswith("//"):
            continue
            
        qty = 1
        name = line
        
        if ":" in line:
            parts = line.split(":", 1)
            name = parts[0].strip()
            try:
                qty = max(1, int(parts[1].strip()))
            except ValueError:
                qty = 1
        elif " " in line:
            parts = line.split()
            if parts[0].isdigit() and len(parts) >= 2:
                qty = max(1, int(parts[0]))
                name = " ".join(parts[1:])
            elif parts[-1].isdigit() and len(parts) >= 2:
                qty = max(1, int(parts[-1]))
                name = " ".join(parts[:-1])

        swf = ""
        item_class = name
        if "." in name:
            s_parts = name.split(".", 1)
            swf = s_parts[0]
            item_class = s_parts[1]

        items.append({
            "swf": swf,
            "item": item_class,
            "name": name,
            "qty": qty
        })

    return items


def build_catalog_payload(catalog_name: str) -> str:
    """Sintaxis oficial de MG para abrir un catálogo con Lola."""
    clean = str(catalog_name or "").strip()
    return (
        "initial: DO\r\n"
        "    on activate openCat\r\n\r\n"
        "INICIO: DO\r\n"
        "    on activate openCat\r\n\r\n"
        "openCat: DO\r\n"
        f"    catalog {clean}\r\n"
        "    goto initial\r\n"
    )


def build_banner_payload(banner_name: str) -> str:
    """Sintaxis oficial de MG para abrir un modal/banner interactivo."""
    clean = str(banner_name or "").strip()
    return (
        "initial: DO\r\n"
        "    on activate openBanner\r\n\r\n"
        "INICIO: DO\r\n"
        "    on activate openBanner\r\n\r\n"
        "openBanner: DO\r\n"
        f"    modal.banner {clean}\r\n"
        "    goto initial\r\n"
    )


def build_portal_payload(room_id: Union[str, int], coord: str = "") -> str:
    """NpcActionRunner.changeRoom(room, 'x,y'): preserve the source entry tile."""
    room = str(room_id or "").strip()
    if not re.fullmatch(r"[1-9]\d*", room):
        raise ValueError("El portal no tiene una sala de destino numérica válida")
    coord = str(coord or "").strip()
    if coord and not re.fullmatch(r"\d+,\d+", coord):
        raise ValueError("La coordenada del portal debe tener formato x,y")
    command = f"room.change {room}" + (f" {coord}" if coord else "")
    return _click_action_payload(command, "teleport")


def _click_action_payload(command: str, state: str = "execute") -> str:
    return ("initial: DO\r\n    on activate " + state +
            "\r\n\r\nINICIO: DO\r\n    on activate " + state +
            "\r\n\r\n" + state + ": DO\r\n    " + command +
            "\r\n    after 1 initial\r\n")


def _portal_choices(destinations) -> str:
    if len(destinations) == 1:
        return build_portal_payload(*destinations[0])
    names = "-".join(f"Sala {room}" for room, _coord in destinations)
    states = "-".join(f"portal{i}" for i in range(len(destinations)))
    script = _click_action_payload(f'dialog.options "{names}" "-" "{states}" "Elegí un destino"', "choose")
    # Wait for the menu callback instead of racing it with a timed return.
    script = script.replace("    after 1 initial\r\n", "")
    for i, (room, coord) in enumerate(destinations):
        script += f"\r\nportal{i}: DO\r\n    room.change {room}" + (f" {coord}" if coord else "") + "\r\n    after 1 initial\r\n"
    return script


def build_minigame_payload(game_name: str) -> str:
    """Sintaxis oficial de MG para abrir un minijuego interactivo."""
    clean = str(game_name or "").strip()
    return (
        "initial: DO\r\n"
        "    on activate playGame\r\n\r\n"
        "INICIO: DO\r\n"
        "    on activate playGame\r\n\r\n"
        "playGame: DO\r\n"
        f"    minigame {clean}\r\n"
        "    goto initial\r\n"
    )


def adapt_behavior_script_for_lola(b: Dict[str, Any]) -> tuple:
    """Adapt portable actions; keep NPC logic instead of inventing a greeting/prize.

    Command signatures verified in MMO NpcActionRunner.as. Room-specific scripts
    still need their original actors/state; activating them is not proof of success.
    """
    script = (b.get("script") or "").strip()
    title = b.get("title") or b.get("behavior") or b.get("id") or "Behavior"
    kind = b.get("type", "")
    catalogs = b.get("catalogs") or []
    if kind in ("catalog", "vendor", "") and catalogs:
        return build_catalog_payload(catalogs[0]), f"Catálogo '{catalogs[0]}' ({title})"
    if kind in ("catalog", "vendor", ""):
        match = re.search(r"(?m)^\s*catalog\s+([\w/.-]+)", script)
        if match:
            return build_catalog_payload(match[1]), f"Catálogo '{match[1]}' ({title})"
    if kind == "portal":
        # Never discard the spawn coordinates or silently select the first branch.
        destinations = list(dict.fromkeys(re.findall(
            r"(?m)^[ \t]*room\.change[ \t]+([1-9]\d*)(?:[ \t]+(\d+,\d+))?[ \t]*(?:#[^\r\n]*)?$", script)))
        if destinations:
            return _portal_choices(destinations), f"Portal ({title}) · {len(destinations)} destino(s)"
    if kind in ("banner", "portal"):
        match = re.search(r"(?m)^\s*(modal\.banner[ \t]+[^\r\n#]+)", script)
        if match and "$(" not in match[1]:
            return _click_action_payload(match[1].strip()), f"Banner ({title})"
    if not script:
        raise ValueError("Este behavior no contiene un script ejecutable para Lola")
    if not re.search(r"(?mi)^\s*initial\s*:", script):
        raise ValueError("El behavior no tiene estado initial; necesita su contexto original")
    # Quests, inventory.addOptions, dialog branches, variables and all arguments
    # remain intact. Rewriting these to a single SAY used to produce fake success.
    return script.replace("\r\n", "\n").replace("\n", "\r\n") + "\r\n", f"Script original ({title}) · puede requerir la sala o misión original"


def describe_active_payload(script: str) -> Dict[str, Any]:
    """Read-only summary of the actual payload, shared by every Lola entry point."""
    items = extract_items_from_npc_payload(script)
    actions = []
    labels = {"catalog": "Catálogo", "modal.banner": "Banner", "room.change": "Portal", "minigame": "Minijuego"}
    for command, value in re.findall(r"(?m)^\s*(catalog|modal\.banner|room\.change|minigame)[ \t]+([^\r\n]+)", script):
        action = {"type": command, "label": labels[command], "target": value.strip()}
        if action not in actions:
            actions.append(action)
    has_dialog = bool(re.search(r"(?mi)^\s*[^:\r\n]+:\s*SAY\b|^\s*dialog\.options\b", script))
    kind = "behavior" if actions or has_dialog else ("items" if items else "script")
    label = "Behavior / NPC" if kind == "behavior" else ("Objetos preparados" if items else "Script de Lola")
    return {"kind": kind, "label": label, "items": items, "actions": actions, "has_script": bool(script.strip())}
