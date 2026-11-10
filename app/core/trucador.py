"""

trucador.py - Compiles modified SWF files to trick clothing / avatar items.



ClothMamboAsset.process() copies clothes[slot] → attributes["wear_"+slot].

Official items set that map in the class itself. We do it in the constructor

so it does not depend on addFrameScript / frame1 (FFDec often drops that bind,

which is why Lola gave the item but clicking it showed nothing).



Clothes values:

  same pack  → Class_on

  other pack → pack.Class_on   (official anime.pantalon_blanco style)



Empty string clears a slot (official disfraz* uses accesories:"").

"""



from __future__ import annotations



import json

import time

import os

import re

import shutil

import subprocess

from pathlib import Path

from typing import Any, Dict, List, Optional, Set, Tuple

from .java_runtime import java_executable



ROOT_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT_DIR / "data"

CACHE_DIR = DATA_DIR / "swf_cache"

OVERRIDES_DIR = DATA_DIR / "overrides"

TRICKS_PATH = DATA_DIR / "tricks.json"

CLASS_OVERRIDES_PATH = DATA_DIR / "class_overrides.json"

EFFECT_TRICKS_PATH = DATA_DIR / "effect_tricks.json"

FFDEC_JAR = ROOT_DIR / "ffdec" / "ffdec.jar"



OVERRIDES_DIR.mkdir(parents=True, exist_ok=True)

CACHE_DIR.mkdir(parents=True, exist_ok=True)



ADD_AS3_DIR = ROOT_DIR / "tools" / "ffdec_add_class"

ADD_AS3_CLASS = "com.naw.ffdec.AddAs3Classes"

PLAYERGLOBAL_CANDIDATES = [

    ROOT_DIR / "ffdec" / "flashlib" / "playerglobal32_0.swc",

    Path(r"C:\Program Files (x86)\FFDec\flashlib\playerglobal32_0.swc"),

    Path(r"C:\Program Files\FFDec\flashlib\playerglobal32_0.swc"),

]



# Donor packs that usually ship the Mambo base hierarchy we need to inject.

DONOR_PACKS_BY_MAMBO: Dict[str, list[str]] = {

    "ClothMamboAsset": ["costumes", "costumes2", "costumes4", "costumesHalloween", "costumes3"],

    "PetClothMamboAsset": ["animalsCostumes", "costumesAnimals", "costumes"],

    "TransportMamboAsset": ["costumes", "costumes2", "toys"],

    "TransportOnMamboAsset": ["costumes", "costumes2"],

    "EvolveMamboAsset": ["costumes", "costumes2"],

    "ConsumableMamboAsset": ["food", "toys", "customToys", "petFood"],

    "UsableMamboAsset": ["food", "toys", "customToys"],

    "GrabbableMamboAsset": ["food", "toys"],

    "PetFoodMamboAsset": ["petFood", "food"],

    "PetCareMamboAsset": ["petFood", "toys"],

    "PetToyMamboAsset": ["petToys", "toys"],

    "OwnedNpcMamboAsset": ["beds", "bathroom", "tables", "plant", "plants", "kitchen"],

    "NpcMamboAsset": ["plants", "food", "kitchen", "toys", "plant"],

    "NpcHolderMamboAsset": ["beds", "bathroom", "tables", "plant"],

    "HolderMamboAsset": ["beds", "bathroom", "toys", "tables", "plant"],

    "HouseMamboAsset": ["bathroom", "privateRoom", "beds"],

    "HouseDecorationMamboAsset": ["tables", "carpets", "kitchen", "techosDecoracion", "plant"],

    "HomeInteractiveMamboAsset": ["kitchen", "bathroom", "beds"],

    "VendorMamboAsset": ["kitchen", "tables"],

    "BannerMamboAsset": ["techosDecoracion", "plant"],

    "ImageMamboAsset": ["techosDecoracion", "plant"],

    "MiniGameMamboAsset": ["toys", "customToys"],

    "PersonalPropertyMamboAsset": ["beds", "tables", "plant"],

    "MamboAsset": ["food", "costumes", "beds", "toys"],

}



CANONICAL_CLOTH_SLOTS = {

    "hats", "hairs", "accesories", "mouths", "neck",

    "cloth", "clothFront", "clothBack",

    "leg", "foot", "arm", "grip", "glove",

    "transport", "effect",

}





def remap_to_canonical_slots(

    clothes_map: Dict[str, str],

    parts_info: Optional[Dict[str, Any]] = None,

) -> Tuple[Dict[str, str], Dict[str, Any]]:

    """

    Garantiza que NINGÚN slot con sufijo numérico (ej. hats2, cloth2, hairs2)

    quede en el ActionScript del SWF ni viaje a SmartFoxServer.

    En el servidor y cliente de Mundo Gaturro solo existen wear_hats, wear_accesories,

    wear_hairs, wear_clothFront, etc. Si viaja wear_hats2 el servidor bota el socket

    inmediatamente mostrando 'Desconectado por inactividad'.

    """

    out_clothes: Dict[str, str] = {}

    out_info: Dict[str, Any] = dict(parts_info or {}) if isinstance(parts_info, dict) else {}



    # Preservar primero los slots que ya son canónicos

    for slot, val in (clothes_map or {}).items():

        if slot in CANONICAL_CLOTH_SLOTS:

            out_clothes[slot] = val



    def _matches_keywords(slot_name: str, val: str, *words: str) -> bool:

        text = str(val or "").lower()

        if slot_name in out_info and isinstance(out_info[slot_name], dict):

            text += " " + str(out_info[slot_name].get("name") or "").lower()

        return any(w in text for w in words)



    for slot, val in (clothes_map or {}).items():

        if slot in CANONICAL_CLOTH_SLOTS:

            continue



        s_lower = slot.lower()

        target = "accesories"



        if s_lower.startswith("hat"):

            if _matches_keywords(slot, val, "pelo", "peluca", "hair", "peinado") and "hairs" not in out_clothes:

                target = "hairs"

            elif "accesories" not in out_clothes:

                target = "accesories"

            elif "hairs" not in out_clothes:

                target = "hairs"

            elif "mouths" not in out_clothes:

                target = "mouths"

            else:

                target = "accesories"



        elif s_lower.startswith("hair"):

            if _matches_keywords(slot, val, "gorro", "sombrero", "corona", "tiara", "vincha", "casco") and "hats" not in out_clothes:

                target = "hats"

            elif "accesories" not in out_clothes:

                target = "accesories"

            elif "hats" not in out_clothes:

                target = "hats"

            else:

                target = "accesories"



        elif s_lower.startswith("clothback"):

            if "clothFront" not in out_clothes:

                target = "clothFront"

            elif "cloth" not in out_clothes:

                target = "cloth"

            else:

                target = "clothFront"



        elif s_lower.startswith("cloth"):

            if "clothFront" not in out_clothes:

                target = "clothFront"

            elif "clothBack" not in out_clothes:

                target = "clothBack"

            else:

                target = "clothFront"



        elif s_lower.startswith("mouth"):

            if "accesories" not in out_clothes:

                target = "accesories"

            elif "neck" not in out_clothes:

                target = "neck"

            else:

                target = "accesories"



        elif s_lower.startswith("neck"):

            if "accesories" not in out_clothes:

                target = "accesories"

            elif "mouths" not in out_clothes:

                target = "mouths"

            else:

                target = "accesories"



        elif s_lower.startswith("acc"):

            if "hats" not in out_clothes:

                target = "hats"

            elif "hairs" not in out_clothes:

                target = "hairs"

            elif "mouths" not in out_clothes:

                target = "mouths"

            elif "neck" not in out_clothes:

                target = "neck"

            else:

                target = "hats"



        elif s_lower.startswith("arm"):

            if "glove" not in out_clothes:

                target = "glove"

            elif "grip" not in out_clothes:

                target = "grip"

            else:

                target = "glove"



        elif s_lower.startswith("grip"):

            if "glove" not in out_clothes:

                target = "glove"

            elif "arm" not in out_clothes:

                target = "arm"

            else:

                target = "glove"



        elif s_lower.startswith("leg"):

            if "foot" not in out_clothes:

                target = "foot"

            else:

                target = "leg"



        elif s_lower.startswith("foot"):

            if "leg" not in out_clothes:

                target = "leg"

            else:

                target = "foot"



        else:

            clean = re.sub(r"\d+$", "", slot)

            if clean in CANONICAL_CLOTH_SLOTS and clean not in out_clothes:

                target = clean

            else:

                target = "accesories"



        out_clothes[target] = val

        if slot in out_info:

            out_info[target] = out_info.pop(slot)



    return out_clothes, out_info



MAMBO_PRESETS = [

    {"id": "ClothMamboAsset", "label": "Ropa (ClothMamboAsset)", "inventory": "visualizer"},

    {"id": "ConsumableMamboAsset", "label": "Mochila (ConsumableMamboAsset)", "inventory": "default"},

    # Casa: NpcMamboAsset suele ya estar en food/toys → sin inyectar (no cuelga al entrar).

    {"id": "NpcMamboAsset", "label": "Casa/NPC (recomendado)", "inventory": "house"},

    # Holder / decoración se sacaron del preset: inyectar Holder rompe toys y abre minijuegos.

]



# Nunca inyectar estas bases: el stub incompleto cuelga el MG o abre jueguitos (Gaturrin, etc.).

UNSAFE_INJECT_BASES = {

    "HolderMamboAsset",

    "NpcHolderMamboAsset",

    "MiniGameMamboAsset",

    "HomeInteractiveMamboAsset",

}



SLOT_ALIASES = {

    "hat": "hats",

    "hats": "hats",

    "head": "hats",

    "shoes": "foot",

    "shoe": "foot",

    "pie": "foot",

    "capa": "clothBack",

}



WEAR_KEY = {

    "transport": "vehicle",

    "effect": "attr_effect",

}





def _load_tricks() -> Dict[str, Any]:

    if not TRICKS_PATH.exists():

        return {}

    try:

        data = json.loads(TRICKS_PATH.read_text(encoding="utf-8"))

        return data if isinstance(data, dict) else {}

    except Exception:

        return {}





def _save_tricks(data: Dict[str, Any]) -> None:

    TRICKS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")





def _load_class_overrides() -> Dict[str, Any]:

    if not CLASS_OVERRIDES_PATH.exists():

        return {}

    try:

        data = json.loads(CLASS_OVERRIDES_PATH.read_text(encoding="utf-8"))

        return data if isinstance(data, dict) else {}

    except Exception:

        return {}





def _save_class_overrides(data: Dict[str, Any]) -> None:

    CLASS_OVERRIDES_PATH.write_text(

        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"

    )





def list_mambo_targets() -> Dict[str, Any]:

    from core.item_catalog import BAG_MAMBO, HOUSE_MAMBO, INV_LABELS, VISUALIZER_MAMBO



    # Holder/MiniGame fuera: inyectarlos o forzarlos rompe toys y abre minijuegos.

    advanced = sorted(

        (VISUALIZER_MAMBO | HOUSE_MAMBO | BAG_MAMBO) - UNSAFE_INJECT_BASES

    )

    return {

        "presets": MAMBO_PRESETS,

        "advanced": [

            {

                "id": name,

                "label": name,

                "inventory": (

                    "visualizer" if name in VISUALIZER_MAMBO

                    else "house" if name in HOUSE_MAMBO

                    else "default"

                ),

                "inventory_label": INV_LABELS.get(

                    "visualizer" if name in VISUALIZER_MAMBO

                    else "house" if name in HOUSE_MAMBO

                    else "default",

                    "",

                ),

            }

            for name in advanced

        ],

    }





def clear_pack_tricks(swf_name: str) -> None:

    pack = (swf_name or "").replace(".swf", "").strip()

    tricks = _load_tricks()

    if pack in tricks:

        tricks.pop(pack, None)

        _save_tricks(tricks)

    # Keep class overrides; rebuild so override SWF still reflects them.

    _rebuild_pack_override(pack)





def _entry_clothes(entry: Any) -> Dict[str, str]:

    """Accept old flat maps and new {clothes, parts_info} entries (canonical slots only)."""

    if not isinstance(entry, dict):

        return {}

    parts_info = entry.get("parts_info") if isinstance(entry.get("parts_info"), dict) else None

    if "clothes" in entry and isinstance(entry["clothes"], dict):

        raw = {str(k): "" if v is None else str(v) for k, v in entry["clothes"].items()}

        mapped, _ = remap_to_canonical_slots(raw, parts_info)

        return mapped

    # Legacy: slot -> graphic string

    out: Dict[str, str] = {}

    for k, v in entry.items():

        if k in ("parts_info", "clothes"):

            continue

        if isinstance(v, (str, int, float)):

            out[str(k)] = str(v)

    mapped, _ = remap_to_canonical_slots(out, parts_info)

    return mapped





def _entry_parts_info(entry: Any) -> Dict[str, Any]:

    if not isinstance(entry, dict):

        return {}

    info = entry.get("parts_info")

    if not isinstance(info, dict):

        return {}

    # If clothes map was remapped to canonical slots, keep parts_info aligned

    raw_clothes = entry.get("clothes") if isinstance(entry.get("clothes"), dict) else {}

    if raw_clothes:

        _, remapped_info = remap_to_canonical_slots(raw_clothes, info)

        return remapped_info

    return info





def _clean_parts_info(parts_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:

    if not parts_info or not isinstance(parts_info, dict):

        return {}

    cleaned: Dict[str, Any] = {}

    for slot, info in parts_info.items():

        slot_clean = normalize_slot(slot)

        if not slot_clean:

            continue

        if isinstance(info, dict):

            cleaned[slot_clean] = {

                "name": str(info.get("name") or "").strip(),

                "pack": str(info.get("pack") or "").replace(".swf", "").strip(),

                "thumb": str(info.get("thumb") or ""),

            }

        elif isinstance(info, str) and info.strip():

            pack, leaf = parse_item_ref(info)

            cleaned[slot_clean] = {"name": leaf, "pack": pack, "thumb": ""}

    return cleaned





def list_tricks() -> list[Dict[str, Any]]:

    """Solo trucos de ropa (look). Los cambios de clase van en list_class_changes()."""

    tricks = _load_tricks()

    rows: list[Dict[str, Any]] = []

    for pack, items in tricks.items():

        if not isinstance(items, dict):

            continue

        for obj_name, entry in items.items():

            clothes = _entry_clothes(entry)

            if not clothes:

                continue

            parts_info = _entry_parts_info(entry)

            part_rows = []

            for slot, value in clothes.items():

                info = parts_info.get(slot) if isinstance(parts_info.get(slot), dict) else {}

                pack_part = (info.get("pack") or "").strip()

                name_part = (info.get("name") or "").strip()

                if not name_part and value:

                    pack_part, name_part = parse_item_ref(value, default_pack=pack)

                    if name_part.endswith("_on"):

                        name_part = name_part[:-3]

                part_rows.append({

                    "slot": slot,

                    "value": value,

                    "pack": pack_part,

                    "name": name_part,

                    "thumb": info.get("thumb") or "",

                })

            try:

                qty = max(1, min(99, int(entry.get("qty") or 1)))

            except (TypeError, ValueError):

                qty = 1

            rows.append({

                "id": f"{pack}.{obj_name}",

                "kind": "clothes",

                "pack": pack,

                "object": obj_name,

                "item": f"{pack}.{obj_name}",

                "parts": clothes,

                "parts_info": parts_info,

                "part_rows": part_rows,

                "parts_count": len(clothes),

                "qty": qty,

                "override_exists": (OVERRIDES_DIR / f"{pack}.swf").exists(),

            })

    rows.sort(key=lambda r: r["item"].lower())

    return rows





def list_class_changes() -> list[Dict[str, Any]]:

    """Cambios de clase Mambo (no son trucos de ropa)."""

    from core.item_catalog import BAG_MAMBO, HOUSE_MAMBO, INV_LABELS, VISUALIZER_MAMBO



    class_map = _load_class_overrides()

    rows: list[Dict[str, Any]] = []

    for pack, items in class_map.items():

        if not isinstance(items, dict):

            continue

        for obj_name, entry in items.items():

            if not isinstance(entry, dict):

                continue

            mambo_to = str(entry.get("to") or "").strip()

            if not mambo_to:

                continue

            inv = (

                "visualizer" if mambo_to in VISUALIZER_MAMBO

                else "house" if mambo_to in HOUSE_MAMBO

                else "default" if mambo_to in BAG_MAMBO

                else ""

            )

            try:

                qty = max(1, min(99, int(entry.get("qty") or 1)))

            except (TypeError, ValueError):

                qty = 1

            rows.append({

                "id": f"{pack}.{obj_name}",

                "kind": "class",

                "pack": pack,

                "object": obj_name,

                "item": f"{pack}.{obj_name}",

                "mambo_class": mambo_to,

                "mambo_from": str(entry.get("from") or ""),

                "inventory": inv,

                "inventory_label": INV_LABELS.get(inv, inv),

                "qty": qty,

                "override_exists": (OVERRIDES_DIR / f"{pack}.swf").exists(),

                "at": str(entry.get("at") or ""),

            })

    rows.sort(key=lambda r: r["item"].lower())

    return rows





def list_lola_items() -> list[Dict[str, Any]]:

    """Items que Lola puede dar: ropa trucada + cambios de clase + efectos trucados."""

    rows = list(list_tricks())

    seen = {r["item"] for r in rows}

    for row in list_class_changes():

        if row["item"] not in seen:

            rows.append(row)

            seen.add(row["item"])

    for row in list_effect_tricks():

        rows.append(row)

    return rows


def get_tricks_counts() -> Dict[str, int]:
    """Retorna el desglose y total de trucos activos (ropa, clases y efectos)."""
    tricks = list_tricks()
    classes = list_class_changes()
    effects = list_effect_tricks()
    return {
        "total": len(tricks) + len(classes) + len(effects),
        "looks": len(tricks),
        "classes": len(classes),
        "effects": len(effects),
    }


def _load_effect_tricks() -> Dict[str, Any]:

    if not EFFECT_TRICKS_PATH.exists():

        return {}

    try:

        data = json.loads(EFFECT_TRICKS_PATH.read_text(encoding="utf-8"))

        return data if isinstance(data, dict) else {}

    except Exception:

        return {}





def _save_effect_tricks(data: Dict[str, Any]) -> None:

    EFFECT_TRICKS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")





def build_action_item_payload(

    base_item: str = "food.banana",

    action: str = "kick",

    sub_item: str = "",

    destination: str = "default",

    uses: int = 9999,

    auto_on: bool = True

) -> Dict[str, Any]:

    base = (base_item or "food.banana").strip()

    act = (action or "kick").strip()

    sub = (sub_item or "").strip()



    # 1. Resolver nombre completo de la accion

    if sub:

        if auto_on and not sub.endswith("_on") and not sub.endswith("_so"):

            sub = f"{sub}_on"

        if "." not in act:

            full_action = f"{act}.{sub}"

        else:

            full_action = act

    else:

        full_action = act



    inv = "house" if destination.lower() in ("house", "casa") else "default"



    # 2. Configurar customAttributes segun el inventario de destino

    if inv == "house":

        custom_attrs = {

            "useAction": full_action,

            "holder": "true",

            "sizeW": "1",

            "sizeH": "1",

            "session": "false"

        }

    else:

        custom_attrs = {

            "attr_action": full_action,

            "uses": str(uses),

            "grabbable": "true",

            "session": "false"

        }



    return {

        "base_item": base,

        "full_action": full_action,

        "inventory": inv,

        "custom_attrs": custom_attrs

    }





def save_effect_trick(

    base_item: str = "food.banana",

    action: str = "kick",

    sub_item: str = "",

    destination: str = "default",

    uses: int = 9999,

    qty: int = 1,

    auto_on: bool = True

) -> Dict[str, Any]:

    p = build_action_item_payload(base_item, action, sub_item, destination, uses, auto_on)

    base = p["base_item"]

    full_act = p["full_action"]

    inv = p["inventory"]

    custom_attrs = p["custom_attrs"]

    

    if "." in base:

        pack, obj = base.split(".", 1)

    else:

        pack = "food"

        obj = base

        base = f"{pack}.{obj}"



    effect_id = f"{base}__{full_act}".replace("/", "_")

    all_effects = _load_effect_tricks()

    entry = {

        "id": effect_id,

        "kind": "effect",

        "pack": pack,

        "object": obj,

        "item": base,

        "base_item": base,

        "action": action,

        "sub_item": sub_item,

        "full_action": full_act,

        "inventory": inv,

        "uses": uses,

        "custom_attrs": custom_attrs,

        "options": custom_attrs,

        "qty": max(1, min(99, int(qty or 1))),

        "created_at": int(time.time())

    }

    prev_entry = all_effects.get(effect_id)

    all_effects[effect_id] = entry

    _save_effect_tricks(all_effects)



    rebuilt = _rebuild_pack_override(pack, require_class=obj)

    if not rebuilt.get("ok"):

        if prev_entry is not None:

            all_effects[effect_id] = prev_entry

        else:

            all_effects.pop(effect_id, None)

        _save_effect_tricks(all_effects)

        return {

            "ok": False,

            "error": rebuilt.get("error") or "Error al compilar SWF para el efecto",

            "entry": entry

        }



    return {

        "ok": True,

        "entry": entry,

        "swf_file": rebuilt.get("swf_file"),

        "message": f"Listo: {base} trucado con acción '{full_act}'",

    }





def delete_effect_trick(effect_id: str) -> Dict[str, Any]:

    all_effects = _load_effect_tricks()

    if effect_id not in all_effects:

        return {"ok": False, "error": "Efecto no encontrado"}

    entry = all_effects.pop(effect_id)

    _save_effect_tricks(all_effects)

    pack = entry.get("pack")

    if pack:

        _rebuild_pack_override(pack)

    return {"ok": True, "message": "Efecto eliminado"}





def list_effect_tricks() -> list[Dict[str, Any]]:

    all_effects = _load_effect_tricks()

    rows = list(all_effects.values())

    rows.sort(key=lambda r: r.get("created_at") or 0, reverse=True)

    return rows







def _known_mambo_bases() -> Set[str]:

    from core.item_catalog import BAG_MAMBO, HOUSE_MAMBO, VISUALIZER_MAMBO, _BASE_MAMBO

    return set(_BASE_MAMBO) | set(VISUALIZER_MAMBO) | set(HOUSE_MAMBO) | set(BAG_MAMBO)





def _extract_extends(content: str) -> Optional[str]:

    m = re.search(r"extends\s+([A-Za-z0-9_]+)", content)

    return m.group(1) if m else None





def _family_ctor_lines(mambo_class: str) -> List[str]:

    from core.item_catalog import BAG_MAMBO, HOUSE_MAMBO, VISUALIZER_MAMBO



    lines: List[str] = []

    if mambo_class in VISUALIZER_MAMBO or mambo_class == "ClothMamboAsset":

        lines.append("wearable = true;")

        lines.append("clothes = {};")

    elif mambo_class in BAG_MAMBO:

        lines.append("uses = 1;")

        lines.append("session = false;")

    elif mambo_class in HOUSE_MAMBO:

        lines.append("sizeW = 1;")

        lines.append("sizeH = 1;")

        lines.append("blocks = false;")

        if mambo_class == "HolderMamboAsset":

            lines.append("attributes.holder = true;")

    return lines





def generate_class_actionscript(class_name: str, symbol: str, mambo_class: str) -> str:

    body = "\n         ".join(_family_ctor_lines(mambo_class)) or "// class change"

    return f"""package

{{

   [Embed(source="/_assets/assets.swf", symbol="{symbol}")]

   public dynamic class {class_name} extends {mambo_class}

   {{

      public function {class_name}()

      {{

         super();

         {body}

         addFrameScript(0,frame1);

      }}

      internal function frame1() : *

      {{

         {body}

      }}

   }}

}}

"""





# Cadena madre→hija por si el donor no se puede leer o el extends viene raro.

MAMBO_PARENTS: Dict[str, str] = {

    "MamboAsset": "MovieClip",

    "ClothMamboAsset": "MamboAsset",

    "PetClothMamboAsset": "ClothMamboAsset",

    "TransportMamboAsset": "MamboAsset",

    "TransportOnMamboAsset": "MamboAsset",

    "EvolveMamboAsset": "MamboAsset",

    "ConsumableMamboAsset": "MamboAsset",

    "UsableMamboAsset": "MamboAsset",

    "GrabbableMamboAsset": "MamboAsset",

    "PetFoodMamboAsset": "MamboAsset",

    "PetCareMamboAsset": "MamboAsset",

    "PetToyMamboAsset": "MamboAsset",

    "NpcMamboAsset": "MamboAsset",

    "OwnedNpcMamboAsset": "NpcMamboAsset",

    "HolderMamboAsset": "MamboAsset",

    "NpcHolderMamboAsset": "HolderMamboAsset",

    "HouseMamboAsset": "MamboAsset",

    "HouseDecorationMamboAsset": "MamboAsset",

    "HomeInteractiveMamboAsset": "MamboAsset",

    "VendorMamboAsset": "MamboAsset",

    "BannerMamboAsset": "MamboAsset",

    "ImageMamboAsset": "MamboAsset",

    "MiniGameMamboAsset": "MamboAsset",

    "PersonalPropertyMamboAsset": "MamboAsset",

}



_FLASH_BUILTINS = {

    "MovieClip", "Sprite", "DisplayObject", "DisplayObjectContainer",

    "EventDispatcher", "Object", "Class",

}





def _minimal_mambo_stub(mambo_class: str, parent: str = "MamboAsset") -> str:

    """

    Stub chico para inyectar (sin override process / sin uint).

    El donor completo suele colgar el cliente → kick por 'inactividad'.

    """

    parent = parent or MAMBO_PARENTS.get(mambo_class) or "MamboAsset"

    if mambo_class == "MamboAsset":

        return """package

{

   import flash.display.MovieClip;



   public class MamboAsset extends MovieClip

   {

      public var blocks:* = true;

      public var sizeW:* = 1;

      public var sizeH:* = 1;

      public var attributes:* = {};

      public var questItem:* = false;



      public function MamboAsset()

      {

         super();

      }



      public function process() : void

      {

      }

   }

}

"""

    if mambo_class == "HolderMamboAsset":

        return f"""package

{{

   public class {mambo_class} extends {parent}

   {{

      public var container:*;

      public var capacity:* = 1;

      public var action:*;



      public function {mambo_class}()

      {{

         super();

         blocks = false;

         attributes.holder = true;

      }}

   }}

}}

"""

    if mambo_class in ("HouseDecorationMamboAsset", "NpcHolderMamboAsset", "OwnedNpcMamboAsset"):

        return f"""package

{{

   public class {mambo_class} extends {parent}

   {{

      public function {mambo_class}()

      {{

         super();

         blocks = false;

      }}

   }}

}}

"""

    return f"""package

{{

   public class {mambo_class} extends {parent}

   {{

      public function {mambo_class}()

      {{

         super();

      }}

   }}

}}

"""





def _sanitize_donor_mambo_source(mambo_class: str, source: str) -> str:

    """Siempre stub liviano: el AS completo del donor suele colgar el cliente."""

    parent = (

        _extract_extends(source)

        or MAMBO_PARENTS.get(mambo_class)

        or "MamboAsset"

    )

    if parent == mambo_class:

        parent = MAMBO_PARENTS.get(mambo_class) or "MamboAsset"

    return _minimal_mambo_stub(mambo_class, parent)





def _rewrite_extends_script(content: str, mambo_class: str) -> Optional[str]:

    if not re.search(r"extends\s+[A-Za-z0-9_]+", content):

        return None

    updated = re.sub(r"extends\s+[A-Za-z0-9_]+", f"extends {mambo_class}", content, count=1)

    # Strip clothes maps when leaving cloth family — avoid dead wear attrs.

    from core.item_catalog import VISUALIZER_MAMBO

    if mambo_class not in VISUALIZER_MAMBO:

        updated = re.sub(r"clothes\s*=\s*\{.*?\};", "/* clothes cleared */", updated, flags=re.S)

        updated = re.sub(r"wearable\s*=\s*true\s*;", "/* wearable cleared */", updated)

    for line in _family_ctor_lines(mambo_class):

        key = line.split("=", 1)[0].strip()

        if key and re.search(rf"\b{re.escape(key)}\s*=", updated):

            continue

        if re.search(r"super\(\)\s*;", updated):

            updated = re.sub(r"(super\(\)\s*;)", rf"\1\n         {line}", updated, count=1)

        else:

            updated = line + "\n" + updated

    return updated





def _donor_has_mambo(scripts_dir: Path, mambo_class: str) -> bool:

    return (scripts_dir / f"{mambo_class}.as").exists()





def _playerglobal_swc() -> Optional[Path]:

    for cand in PLAYERGLOBAL_CANDIDATES:

        if cand.exists():

            return cand

    return None





def _ffdec_classpath_add_as3() -> str:

    lib = ROOT_DIR / "ffdec" / "lib"

    parts = [

        str(ADD_AS3_DIR),

        str(lib / "ffdec_lib.jar"),

        str(lib / "*"),

    ]

    return ";".join(parts)





def _ensure_add_as3_compiled() -> bool:

    class_file = ADD_AS3_DIR / "com" / "naw" / "ffdec" / "AddAs3Classes.class"

    java_file = ADD_AS3_DIR / "com" / "naw" / "ffdec" / "AddAs3Classes.java"

    if class_file.exists():

        return True

    if not java_file.exists():

        return False

    lib = ROOT_DIR / "ffdec" / "lib"

    cp = f"{lib / 'ffdec_lib.jar'};{lib / '*'}"

    res = subprocess.run(

        ["javac", "-source", "8", "-target", "8", "-cp", cp, "-d", str(ADD_AS3_DIR), str(java_file)],

        capture_output=True,

        text=True,

        timeout=120,

    )

    return res.returncode == 0 and class_file.exists()





def _export_scripts_to(temp_dir: Path, src_swf: Path) -> Optional[Path]:

    cmd_export = [

        java_executable(), "-jar", str(FFDEC_JAR),

        "-export", "script", str(temp_dir), str(src_swf),

    ]

    res = subprocess.run(cmd_export, capture_output=True, text=True, timeout=180)

    if res.returncode != 0:

        return None

    scripts_dir = temp_dir / "scripts"

    return scripts_dir if scripts_dir.exists() else None





def _run_ffdec_import(src_swf: Path, out_swf: Path, scripts_dir: Path) -> subprocess.CompletedProcess:

    """importScript with playerglobal so uint/String/MovieClip resolve."""

    cmd = [java_executable(), "-jar", str(FFDEC_JAR)]

    pg = _playerglobal_swc()

    if pg:

        cmd += ["-config", f"playerLibLocation={pg}"]

    cmd += ["-importScript", str(src_swf), str(out_swf), str(scripts_dir)]

    return subprocess.run(cmd, capture_output=True, text=True, timeout=180)





def _fetch_donor_mambo_source(mambo_class: str) -> Optional[str]:

    """Export mambo_class.as from the first donor pack that contains it."""

    donors = list(DONOR_PACKS_BY_MAMBO.get(mambo_class) or [])

    # Fallback: try a few common packs.

    for extra in ("beds", "costumes", "food", "bathroom", "tables", "toys"):

        if extra not in donors:

            donors.append(extra)

    for pack in donors:

        src = ensure_swf_cached(pack)

        if not src or not src.exists():

            continue

        temp_dir = DATA_DIR / f"temp_donor_{pack}_{mambo_class}"

        try:

            if temp_dir.exists():

                shutil.rmtree(temp_dir, ignore_errors=True)

            temp_dir.mkdir(parents=True, exist_ok=True)

            scripts = _export_scripts_to(temp_dir, src)

            if not scripts:

                continue

            as_path = scripts / f"{mambo_class}.as"

            if as_path.exists():

                return as_path.read_text(encoding="utf-8", errors="replace")

        except Exception:

            continue

        finally:

            shutil.rmtree(temp_dir, ignore_errors=True)

    return None





def _resolve_mambo_parent(name: str, source: Optional[str] = None) -> Optional[str]:

    """Padre real a inyectar (ignora MovieClip/builtins de Flash)."""

    parent = None

    if source:

        parent = _extract_extends(source)

    if not parent:

        parent = MAMBO_PARENTS.get(name)

    if not parent or parent in _FLASH_BUILTINS or parent == name:

        return None

    return parent





def _collect_missing_mambo_chain(

    scripts_dir: Path,

    needed: Set[str],

) -> Tuple[List[str], Dict[str, str], Optional[str]]:

    """

    Resuelve bases faltantes + padres (extends).

    Orden final: madre → hija (MamboAsset antes que HolderMamboAsset).

    """

    bases = _known_mambo_bases()

    present = {p.stem for p in scripts_dir.glob("*.as")}

    sources: Dict[str, str] = {}

    depth: Dict[str, int] = {}

    queue: List[str] = sorted(n for n in needed if n not in present)

    seen: Set[str] = set()



    while queue:

        name = queue.pop(0)

        if name in seen or name in present:

            continue

        if name not in bases and name not in MAMBO_PARENTS:

            # Still allow known needed names; skip unknown flash junk.

            if name in _FLASH_BUILTINS:

                continue

        seen.add(name)

        src = _fetch_donor_mambo_source(name)

        if not src:

            # Sin donor: stub con padre conocido (ej. MamboAsset → MovieClip).

            if name not in MAMBO_PARENTS and name not in bases:

                return [], {}, f"No encontré {name} en packs donantes para inyectar"

            src = _minimal_mambo_stub(name, MAMBO_PARENTS.get(name) or "MamboAsset")

        sources[name] = src

        parent = _resolve_mambo_parent(name, src)

        # depth: hijos más profundos primero en la cola; luego ordenamos madre→hija

        depth[name] = depth.get(name, 0)

        if parent and parent not in present and parent not in seen:

            # Padre Mambo (o cadena) hay que crearlo antes.

            if parent in bases or parent in MAMBO_PARENTS or parent.endswith("MamboAsset"):

                queue.append(parent)

                depth[parent] = min(depth.get(parent, 99), depth[name] - 1)



    # Madre primero: MamboAsset (depth bajo) → Holder → NpcHolder…

    # Usamos distancia a raíz MamboAsset / MovieClip.

    def _root_distance(n: str) -> int:

        d = 0

        cur = n

        walked = set()

        while cur and cur not in walked:

            walked.add(cur)

            p = _resolve_mambo_parent(cur, sources.get(cur))

            if not p:

                break

            d += 1

            cur = p

        return d



    ordered = sorted(sources.keys(), key=lambda n: (_root_distance(n), n))

    return ordered, sources, None





def _inject_mambo_bases(working_swf: Path, needed: Set[str]) -> Dict[str, Any]:

    """

    Mirror FFDec GUI: Add empty class(es) into DoABC, then importScript full bodies.

    working_swf is updated in place on success.

    """

    if not needed:

        return {"ok": True, "injected": []}

    if not working_swf.exists():

        return {"ok": False, "error": "SWF de trabajo no existe"}

    unsafe = sorted(m for m in needed if m in UNSAFE_INJECT_BASES)

    if unsafe:

        return {

            "ok": False,

            "error": (

                f"No inyecto {', '.join(unsafe)}: el stub cuelga el MG o abre minijuegos. "

                "Usá NpcMamboAsset (recomendado) si está en el pack."

            ),

            "missing": unsafe,

        }

    if not _ensure_add_as3_compiled():

        return {"ok": False, "error": "Falta el helper AddAs3Classes (tools/ffdec_add_class)"}

    if not _playerglobal_swc():

        return {

            "ok": False,

            "error": (

                "Falta playerglobal.swc (ffdec/flashlib/playerglobal32_0.swc). "

                "Sin eso FFDec no compila uint/String al inyectar bases."

            ),

        }



    work_dir = working_swf.parent / f"{working_swf.stem}_inject"

    if work_dir.exists():

        shutil.rmtree(work_dir, ignore_errors=True)

    work_dir.mkdir(parents=True, exist_ok=True)



    try:

        probe = _export_scripts_to(work_dir / "probe", working_swf)

        if not probe:

            return {"ok": False, "error": "No se pudo leer scripts del SWF para inyectar bases"}



        already = sorted(m for m in needed if _donor_has_mambo(probe, m))

        missing_needed = {m for m in needed if not _donor_has_mambo(probe, m)}

        if not missing_needed:

            return {"ok": True, "injected": [], "already": already}



        ordered, sources, err = _collect_missing_mambo_chain(probe, missing_needed)

        if err:

            return {"ok": False, "error": err}

        if not ordered:

            return {"ok": True, "injected": [], "already": already}



        # Stubs livianos: el AS completo del donante suele tirar la conexión.

        safe_sources = {

            name: _sanitize_donor_mambo_source(name, src)

            for name, src in sources.items()

        }



        empty_swf = work_dir / "with_empty.swf"

        cmd_add = [

            java_executable(), "-cp", _ffdec_classpath_add_as3(), ADD_AS3_CLASS,

            str(working_swf), str(empty_swf), *ordered,

        ]

        res_add = subprocess.run(cmd_add, capture_output=True, text=True, timeout=120)

        if res_add.returncode != 0 or not empty_swf.exists():

            detail = (res_add.stderr or res_add.stdout or "").strip()

            return {"ok": False, "error": f"Add class falló: {detail or 'sin detalle'}"}



        imp_dir = work_dir / "imp_bases"

        imp_dir.mkdir(parents=True, exist_ok=True)

        for name in ordered:

            (imp_dir / f"{name}.as").write_text(safe_sources[name], encoding="utf-8", newline="\n")



        filled = work_dir / "with_bases.swf"

        res_imp = _run_ffdec_import(empty_swf, filled, imp_dir)

        if res_imp.returncode != 0 or not filled.exists():

            detail = (res_imp.stderr or res_imp.stdout or "").strip()

            return {"ok": False, "error": f"Import de base Mambo falló: {detail or 'sin detalle'}"}



        shutil.copy(filled, working_swf)

        return {"ok": True, "injected": ordered, "already": already}

    except Exception as e:

        return {"ok": False, "error": str(e)}

    finally:

        shutil.rmtree(work_dir, ignore_errors=True)





def list_pack_mambo_bases(pack: str) -> List[str]:

    """

    Mambo base class names present in the pack (override if any).

    Uses in-memory ABC parse — no FFDec export (that was ~2s per inspect).

    """

    pack = (pack or "").replace(".swf", "").strip()

    if not pack:

        return []

    try:

        from core import item_catalog

        data = item_catalog.load_pack(pack, prefer_override=True)

        if not data:

            data = item_catalog.load_pack(pack, prefer_override=False)

        if not data:

            return []

        info = item_catalog._class_info_of(pack, data)

        bases = _known_mambo_bases()

        return sorted(name for name in info if name in bases)

    except Exception:

        return []





def _rebuild_pack_override(

    pack: str,

    require_class: Optional[str] = None,

    require_cloth_base: bool = False,

) -> Dict[str, Any]:

    """

    Rebuild data/overrides/{pack}.swf applying:

      1) class_overrides (extends change + minimal attrs)

      2) clothes tricks (may force ClothMamboAsset for those classes)

    """

    pack = pack.replace(".swf", "").strip()

    out_swf = OVERRIDES_DIR / f"{pack}.swf"

    pack_tricks = _load_tricks().get(pack) or {}

    if not isinstance(pack_tricks, dict):

        pack_tricks = {}

    pack_classes = _load_class_overrides().get(pack) or {}

    if not isinstance(pack_classes, dict):

        pack_classes = {}

    pack_effects = {

        v["object"]: v

        for v in _load_effect_tricks().values()

        if v.get("pack") == pack and v.get("object")

    }



    if not pack_tricks and not pack_classes and not pack_effects:

        if out_swf.exists():

            out_swf.unlink(missing_ok=True)

        return {"ok": True, "removed_override": True}



    src_swf = ensure_swf_cached(pack)

    if not src_swf or not src_swf.exists():

        return {"ok": False, "error": f"No se pudo encontrar {pack}.swf"}



    temp_dir = DATA_DIR / "temp_trucar"

    if temp_dir.exists():

        shutil.rmtree(temp_dir, ignore_errors=True)

    temp_dir.mkdir(parents=True, exist_ok=True)



    isolated_input = temp_dir / f"{pack}_src.swf"

    shutil.copy(src_swf, isolated_input)



    try:

        working_swf = isolated_input

        scripts_dir = _export_scripts_to(temp_dir, working_swf)

        if not scripts_dir:

            return {"ok": False, "error": f"Error al decompilar {pack}.swf"}



        if require_class and not (scripts_dir / f"{require_class}.as").exists():

            return {

                "ok": False,

                "error": f"La clase {require_class}.as no existe dentro de {pack}.swf",

            }



        needed_bases: Set[str] = set()

        for entry in pack_classes.values():

            if isinstance(entry, dict) and entry.get("to"):

                needed_bases.add(str(entry["to"]))

        has_clothes = any(_entry_clothes(e) for e in pack_tricks.values())

        if require_cloth_base or has_clothes:

            needed_bases.add("ClothMamboAsset")

        for eff in pack_effects.values():

            eff_inv = str(eff.get("inventory") or eff.get("destination") or "default").lower()

            if eff_inv in ("house", "casa"):

                needed_bases.add("NpcMamboAsset")

            else:

                needed_bases.add("ConsumableMamboAsset")



        injected: List[str] = []

        if needed_bases:

            missing = {m for m in needed_bases if not _donor_has_mambo(scripts_dir, m)}

            if missing:

                inj = _inject_mambo_bases(working_swf, missing)

                if not inj.get("ok"):

                    available = sorted(

                        p.stem for p in scripts_dir.glob("*.as") if p.stem in _known_mambo_bases()

                    )

                    return {

                        "ok": False,

                        "error": inj.get("error") or "No se pudieron inyectar bases Mambo",

                        "available_bases": available,

                        "missing": sorted(missing),

                    }

                injected = list(inj.get("injected") or [])

                # Re-export so subsequent rewrites see the new bases.

                scripts_dir = _export_scripts_to(temp_dir / "after_inject", working_swf)

                if not scripts_dir:

                    return {"ok": False, "error": "Falló re-export luego de inyectar bases Mambo"}



        bases = _known_mambo_bases()



        final_import_dir = temp_dir / "final_import"

        final_import_dir.mkdir(parents=True, exist_ok=True)



        imported = 0

        class_changed = 0



        # Class overrides

        for cls_name, entry in pack_classes.items():

            if not isinstance(entry, dict):

                continue

            mambo_to = str(entry.get("to") or "").strip()

            if not mambo_to:

                continue

            cls_as = scripts_dir / f"{cls_name}.as"

            if not cls_as.exists():

                continue

            # Clothes trick on same class wins later.

            if cls_name in pack_tricks and _entry_clothes(pack_tricks.get(cls_name)):

                continue

            content = cls_as.read_text(encoding="utf-8", errors="replace")

            current_ext = _extract_extends(content) or ""

            # Already the target and looks like a prior clean rewrite → skip reimport

            # (recompilar de más es lo que suele colgar el cliente).

            if current_ext == mambo_to and "sizeW" in content and mambo_to in _known_mambo_bases():

                # Still count as intentional; no bytecode rewrite needed.

                continue

            symbol = _extract_embed_symbol(content)

            # Salir de comida/mochila: regenerar limpio (sacar adds.eat etc.).

            # Si ya es casa/ropa, preferir rewrite mínimo del extends.

            from core.item_catalog import BAG_MAMBO, HOUSE_MAMBO, VISUALIZER_MAMBO

            leaving_bag = current_ext in BAG_MAMBO or current_ext == "ConsumableMamboAsset"

            if symbol and (leaving_bag or mambo_to in HOUSE_MAMBO or mambo_to in VISUALIZER_MAMBO):

                new_as = generate_class_actionscript(cls_name, symbol, mambo_to)

            else:

                new_as = _rewrite_extends_script(content, mambo_to)

            if not new_as:

                continue

            if new_as.strip() == content.strip():

                continue

            (final_import_dir / f"{cls_name}.as").write_text(new_as, encoding="utf-8", newline="\n")

            imported += 1

            class_changed += 1



        # Clothes tricks (force ClothMamboAsset)

        for cls_name, entry in pack_tricks.items():

            cls_clothes = _entry_clothes(entry)

            if not cls_clothes:

                continue

            cls_as = scripts_dir / f"{cls_name}.as"

            if not cls_as.exists():

                continue

            content = cls_as.read_text(encoding="utf-8", errors="replace")

            symbol = _extract_embed_symbol(content)

            if symbol:

                new_as = generate_cloth_actionscript(cls_name, symbol, cls_clothes)

            else:

                new_as = _rewrite_existing_script(content, cls_clothes)

            if not new_as:

                continue

            (final_import_dir / f"{cls_name}.as").write_text(new_as, encoding="utf-8", newline="\n")

            imported += 1

# Effect tricks (Consumable with custom attr_action / uses)
        for cls_name, entry in pack_effects.items():
            cls_as = scripts_dir / f"{cls_name}.as"
            if not cls_as.exists():
                continue
            if cls_name in pack_tricks and _entry_clothes(pack_tricks.get(cls_name)):
                continue
            full_act = entry.get("full_action") or entry.get("action") or ""
            dest = entry.get("inventory") or entry.get("destination") or "default"
            uses = entry.get("uses") or 9999
            try:
                uses_val = max(1, int(uses))
            except (ValueError, TypeError):
                uses_val = 9999

            content = cls_as.read_text(encoding="utf-8", errors="replace")
            symbol = _extract_embed_symbol(content)
            if symbol:
                new_as = generate_effect_actionscript(cls_name, symbol, full_act, dest, uses_val)
            else:
                new_as = _rewrite_effect_script(content, full_act, dest, uses_val)
            if not new_as:
                continue
            (final_import_dir / f"{cls_name}.as").write_text(new_as, encoding="utf-8", newline="\n")
            imported += 1



        if require_class and not (final_import_dir / f"{require_class}.as").exists():

            return {"ok": False, "error": f"No se pudo preparar {require_class} para recompilar"}



        item_imports = [

            p for p in final_import_dir.glob("*.as") if p.stem not in bases

        ]

        if not item_imports:

            return {"ok": False, "error": f"No quedó ninguna clase para recompilar en {pack}"}



        res_import = _run_ffdec_import(working_swf, out_swf, final_import_dir)

        if res_import.returncode != 0:

            return {

                "ok": False,

                "error": f"Error al recompilar SWF: {res_import.stderr or res_import.stdout}",

            }



        return {

            "ok": True,

            "swf_file": str(out_swf),

            "imported": imported,

            "class_changed": class_changed,

            "injected_bases": injected,

        }

    except Exception as e:

        return {"ok": False, "error": str(e)}

    finally:

        shutil.rmtree(temp_dir, ignore_errors=True)





def _recompile_pack(

    pack: str,

    pack_tricks: Dict[str, Any],

    require_class: Optional[str] = None,

) -> Dict[str, Any]:

    """Back-compat wrapper used by clothes trucador."""

    # pack_tricks already saved to disk by caller; rebuild from disk state.

    _ = pack_tricks

    return _rebuild_pack_override(

        pack,

        require_class=require_class,

        require_cloth_base=True,

    )





def cleanup_orphan_overrides() -> List[str]:

    """

    Borra data/overrides/*.swf que ya no tienen truco de ropa ni cambio de clase ni efectos.

    Overrides viejos (ej. toys con Holder inyectado) cuelgan el MG / abren minijuegos.

    """

    tricks = _load_tricks()

    classes = _load_class_overrides()

    effects = _load_effect_tricks()

    eff_packs = {v.get("pack") for v in effects.values() if v.get("pack")}

    removed: List[str] = []

    if not OVERRIDES_DIR.exists():

        return removed

    for swf in list(OVERRIDES_DIR.glob("*.swf")):

        pack = swf.stem

        pack_tricks = tricks.get(pack) if isinstance(tricks.get(pack), dict) else {}

        pack_classes = classes.get(pack) if isinstance(classes.get(pack), dict) else {}

        if pack_tricks or pack_classes or pack in eff_packs:

            continue

        try:

            swf.unlink(missing_ok=True)

            removed.append(swf.name)

        except Exception:

            pass

    return removed





def delete_trick(pack: str, obj_name: str) -> Dict[str, Any]:

    pack = (pack or "").replace(".swf", "").strip()

    obj_name = (obj_name or "").replace(".as", "").strip()

    if obj_name.endswith("_on"):

        obj_name = obj_name[:-3]

    if not pack or not obj_name:

        return {"ok": False, "error": "Falta el pack o el objeto"}



    tricks = _load_tricks()

    pack_tricks = tricks.get(pack) if isinstance(tricks.get(pack), dict) else {}

    had_clothes = isinstance(pack_tricks, dict) and obj_name in pack_tricks

    if had_clothes:

        pack_tricks.pop(obj_name, None)

        if pack_tricks:

            tricks[pack] = pack_tricks

        else:

            tricks.pop(pack, None)

        _save_tricks(tricks)



    all_classes = _load_class_overrides()

    pack_classes = all_classes.get(pack) if isinstance(all_classes.get(pack), dict) else {}

    had_class = isinstance(pack_classes, dict) and obj_name in pack_classes

    if had_class:

        pack_classes = dict(pack_classes)

        pack_classes.pop(obj_name, None)

        if pack_classes:

            all_classes[pack] = pack_classes

        else:

            all_classes.pop(pack, None)

        _save_class_overrides(all_classes)



    if not had_clothes and not had_class:

        return {"ok": False, "error": "Ese truco no está guardado"}



    recompiled = _rebuild_pack_override(pack)

    if not recompiled.get("ok"):

        return recompiled



    class_left = bool((_load_class_overrides().get(pack) or {}))

    clothes_left = bool((_load_tricks().get(pack) or {}))

    return {

        "ok": True,

        "message": f"Se sacó el truco de {pack}.{obj_name}",

        "item": f"{pack}.{obj_name}",

        "pack_empty": not clothes_left and not class_left,

    }





def ensure_swf_cached(swf_name: str) -> Optional[Path]:

    clean_name = swf_name.replace(".swf", "").strip()

    from core import item_catalog

    found = item_catalog.find_pack_swf(clean_name)

    if found and os.path.exists(found):

        return Path(found)

    item_catalog._download_pack(clean_name)

    found = item_catalog.find_pack_swf(clean_name)

    if found and os.path.exists(found):

        return Path(found)

    local_cand = CACHE_DIR / f"{clean_name}.swf"

    return local_cand if local_cand.exists() else None





def _strip_on(name: str) -> str:

    name = (name or "").strip()

    if name.lower().endswith("_on"):

        return name[:-3]

    return name





def _ensure_on(name: str) -> str:

    name = (name or "").strip()

    if not name:

        return ""

    if name.lower().endswith("_on"):

        return name

    return name + "_on"





def normalize_slot(slot: str) -> str:

    raw = (slot or "").strip()

    if raw.startswith("wear_"):

        raw = raw[5:]

    if raw.startswith("attr_"):

        raw = raw[5:]

    return SLOT_ALIASES.get(raw, raw)





def wear_key_for_slot(slot: str) -> str:

    slot = normalize_slot(slot)

    return WEAR_KEY.get(slot, f"wear_{slot}")





def parse_item_ref(raw: Any, default_pack: str = "") -> Tuple[str, str]:

    """Return (pack, leaf_without_on) from pack.item, pack.item_on or item."""

    if isinstance(raw, dict):

        pack = str(raw.get("pack") or "").replace(".swf", "").strip()

        name = _strip_on(str(raw.get("name") or raw.get("item") or "").strip())

        return pack or default_pack, name



    text = str(raw or "").strip()

    if not text:

        return default_pack, ""

    if "." in text:

        pack, name = text.split(".", 1)

        pack = pack.replace(".swf", "").strip()

        return pack, _strip_on(name)

    return default_pack, _strip_on(text)





def clothes_value(pack: str, leaf: str, base_pack: str) -> str:

    """Always pack.item_on — that's the format that actually shows in-game."""

    graphic = _ensure_on(leaf)

    if not graphic:

        return ""

    pack = (pack or base_pack or "").replace(".swf", "").strip()

    if pack:

        return f"{pack}.{graphic}"

    return graphic





def build_clothes_map(

    base_swf: str,

    parts: Optional[Dict[str, Any]] = None,

    parts_info: Optional[Dict[str, Any]] = None,

    body_part: Optional[str] = None,

    target_object: Optional[str] = None,

) -> Dict[str, str]:

    """

    slot → clothes value.



    Individual: one slot pointing at one graphic.

    Multi: several slots packed into the same base item (official disfraz* style).

    Empty string is kept (clears that slot on the avatar).

    """

    base_pack = base_swf.replace(".swf", "").strip()

    clothes_map: Dict[str, str] = {}



    def put(slot: str, info: Any) -> None:

        slot_clean = normalize_slot(slot)

        if not slot_clean or slot_clean in clothes_map:

            return

        if info is None:

            return

        if isinstance(info, str) and info.strip() == "":

            clothes_map[slot_clean] = ""

            return

        pack, leaf = parse_item_ref(info, default_pack=base_pack)

        if not leaf and info != "":

            return

        clothes_map[slot_clean] = clothes_value(pack, leaf, base_pack)



    if parts_info and isinstance(parts_info, dict):

        for slot, info in parts_info.items():

            put(slot, info)



    if parts and isinstance(parts, dict):

        for slot, target in parts.items():

            put(slot, target)



    if body_part and (target_object is not None):

        put(body_part, target_object)



    return clothes_map





def wear_attrs_from_clothes(clothes_map: Dict[str, str]) -> Dict[str, str]:

    """Protocol attrs for inventory.addOptions / AcquireObject."""

    attrs: Dict[str, str] = {}

    for slot, value in clothes_map.items():

        attrs[wear_key_for_slot(slot)] = "" if value is None else str(value)

    return attrs





def _as_string_literal(value: str) -> str:

    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'





def generate_effect_actionscript(

    class_name: str,

    symbol: str,

    full_action: str,

    destination: str = "default",

    uses: int = 9999,

) -> str:

    act_lit = _as_string_literal(full_action)

    dest_lower = (destination or "default").strip().lower()

    is_house = dest_lower in ("house", "casa")



    if is_house:

        return f"""package

{{

   [Embed(source="/_assets/assets.swf", symbol="{symbol}")]

   public dynamic class {class_name} extends NpcMamboAsset

   {{

      public function {class_name}()

      {{

         super();

         sizeW = 1;

         sizeH = 1;

         blocks = false;

         attributes.holder = true;

         attributes.useAction = {act_lit};

         attributes.session = false;

         attributes.sizeW = 1;

         attributes.sizeH = 1;

         addFrameScript(0, frame1);

      }}



      internal function frame1() : *

      {{

         sizeW = 1;

         sizeH = 1;

         blocks = false;

         attributes.holder = true;

         attributes.useAction = {act_lit};

         attributes.session = false;

         attributes.sizeW = 1;

         attributes.sizeH = 1;

      }}



      override public function process() : void

      {{

         attributes.holder = true;

         attributes.useAction = {act_lit};

         attributes.sizeW = 1;

         attributes.sizeH = 1;

         attributes.session = false;

         super.process();

      }}

   }}

}}

"""

    else:

        # Default: Mochila (ConsumableMamboAsset)

        return f"""package

{{

   [Embed(source="/_assets/assets.swf", symbol="{symbol}")]

   public dynamic class {class_name} extends ConsumableMamboAsset

   {{

      public function {class_name}()

      {{

         super();

         uses = {uses};

         session = false;

         adds = {{"action": {act_lit}}};

         attributes.grabbable = true;

         attributes.session = false;

         attributes.uses = {uses};

         attributes.attr_action = {act_lit};

         addFrameScript(0, frame1);

      }}



      internal function frame1() : *

      {{

         uses = {uses};

         session = false;

         adds = {{"action": {act_lit}}};

         attributes.grabbable = true;

         attributes.session = false;

         attributes.uses = {uses};

         attributes.attr_action = {act_lit};

      }}



      override public function process() : void

      {{

         uses = {uses};

         session = false;

         adds = {{"action": {act_lit}}};

         attributes.grabbable = true;

         attributes.session = false;

         attributes.uses = {uses};

         attributes.attr_action = {act_lit};

         super.process();

      }}

   }}

}}

"""





def _rewrite_effect_script(
    content: str,
    full_action: str,
    destination: str = "default",
    uses: int = 9999,
) -> Optional[str]:
    act_lit = _as_string_literal(full_action)
    dest_lower = (destination or "default").strip().lower()
    is_house = dest_lower in ("house", "casa")
    target_base = "NpcMamboAsset" if is_house else "ConsumableMamboAsset"

    rewritten = _rewrite_extends_script(content, target_base)
    if not rewritten:
        return None

    if is_house:
        inject_ctor = (
            f"super();\n"
            f"         sizeW = 1;\n"
            f"         sizeH = 1;\n"
            f"         blocks = false;\n"
            f"         attributes.holder = true;\n"
            f"         attributes.useAction = {act_lit};\n"
            f"         attributes.session = false;\n"
            f"         attributes.sizeW = 1;\n"
            f"         attributes.sizeH = 1;"
        )
    else:
        action_map = '{"action": ' + act_lit + '}'
        inject_ctor = (
            f"super();\n"
            f"         uses = {uses};\n"
            f"         session = false;\n"
            f"         adds = {action_map};\n"
            f"         attributes.grabbable = true;\n"
            f"         attributes.session = false;\n"
            f"         attributes.uses = {uses};\n"
            f"         attributes.attr_action = {act_lit};"
        )

    return re.sub(r"super\(\)\s*;", inject_ctor, rewritten, count=1)


def generate_cloth_actionscript(class_name: str, symbol: str, clothes_map: Dict[str, str]) -> str:

    """Same shape as official items / mg-tool: clothes in ctor and frame1."""

    if clothes_map:

        entries = ",\n            ".join(

            f"{_as_string_literal(k)}:{_as_string_literal(v)}" for k, v in clothes_map.items()

        )

        clothes_block = "{\n            " + entries + "\n         }"

    else:

        clothes_block = "{}"



    return f"""package

{{

   [Embed(source="/_assets/assets.swf", symbol="{symbol}")]

   public dynamic class {class_name} extends ClothMamboAsset

   {{

      public function {class_name}()

      {{

         super();

         wearable = true;

         clothes = {clothes_block};

         addFrameScript(0,frame1);

      }}

      internal function frame1() : *

      {{

         wearable = true;

         clothes = {clothes_block};

      }}

   }}

}}

"""





def _extract_embed_symbol(content: str) -> Optional[str]:

    match = re.search(r'\[Embed\(source="[^"]+",\s*symbol="([^"]+)"\)\]', content)

    if match:

        return match.group(1)

    return None





def _rewrite_existing_script(content: str, clothes_map: Dict[str, str]) -> Optional[str]:

    """Fallback if we cannot rebuild the class from Embed."""

    if clothes_map:

        entries = ",\n            ".join(

            f"{_as_string_literal(k)}:{_as_string_literal(v)}" for k, v in clothes_map.items()

        )

        clothes_block = "{\n            " + entries + "\n         }"

    else:

        clothes_block = "{}"



    assignment = f"clothes = {clothes_block};"

    updated = re.sub(r"clothes\s*=\s*\{.*?\};", assignment, content, count=1, flags=re.S)

    if updated != content:

        if "wearable" not in updated:

            updated = re.sub(r"(super\(\)\s*;)", r"\1\n         wearable = true;", updated, count=1)

        return updated



    if re.search(r"super\(\)\s*;", content):

        inject = f"super();\n         wearable = true;\n         {assignment}"

        return re.sub(r"super\(\)\s*;", inject, content, count=1)

    return None





def trucar_ropa(

    base_swf: str,

    base_object: str,

    body_part: Optional[str] = None,

    target_object: Optional[str] = None,

    parts: Optional[Dict[str, str]] = None,

    parts_info: Optional[Dict[str, Any]] = None,

    qty: int = 1,

) -> Dict[str, Any]:

    base_swf_clean = base_swf.replace(".swf", "").strip()

    base_object = base_object.replace(".as", "").strip()

    if base_object.endswith("_on"):

        base_object = base_object[:-3]

    try:

        qty_n = max(1, min(99, int(qty or 1)))

    except (TypeError, ValueError):

        qty_n = 1



    clothes_map = build_clothes_map(

        base_swf_clean,

        parts=parts,

        parts_info=parts_info,

        body_part=body_part,

        target_object=target_object,

    )

    if not clothes_map:

        return {"ok": False, "error": "No se especificaron partes para el truco de ropa"}



    cleaned_info = _clean_parts_info(parts_info)

    clothes_map, cleaned_info = remap_to_canonical_slots(clothes_map, cleaned_info)

    wear_attrs = wear_attrs_from_clothes(clothes_map)

    item_name = f"{base_swf_clean}.{base_object}"



    src_swf = ensure_swf_cached(base_swf_clean)

    if not src_swf or not src_swf.exists():

        return {"ok": False, "error": f"No se pudo descargar o encontrar el SWF {base_swf_clean}.swf"}



    # Snapshot previous entry so we can roll back if recompile fails.

    tricks = _load_tricks()

    pack_tricks = tricks.setdefault(base_swf_clean, {})

    if not isinstance(pack_tricks, dict):

        pack_tricks = {}

        tricks[base_swf_clean] = pack_tricks

    previous = pack_tricks.get(base_object)

    pack_tricks[base_object] = {

        "clothes": clothes_map,

        "parts_info": cleaned_info,

        "qty": qty_n,

    }

    _save_tricks(tricks)



    rebuilt = _recompile_pack(base_swf_clean, pack_tricks, require_class=base_object)

    if not rebuilt.get("ok"):

        if previous is None:

            pack_tricks.pop(base_object, None)

        else:

            pack_tricks[base_object] = previous

        if pack_tricks:

            tricks[base_swf_clean] = pack_tricks

        else:

            tricks.pop(base_swf_clean, None)

        _save_tricks(tricks)

        return rebuilt



    return {

        "ok": True,

        "swf_file": rebuilt.get("swf_file"),

        "base_swf": base_swf_clean,

        "base_object": base_object,

        "item": item_name,

        "parts": clothes_map,

        "parts_info": cleaned_info,

        "wear_attrs": wear_attrs,

        "qty": qty_n,

        "npc_line": f"inventory.add {qty_n} {item_name}",

        "message": (

            f"Listo: {base_object} quedó trucado "

            f"con {len(clothes_map)} parte{'s' if len(clothes_map) != 1 else ''} · x{qty_n}."

        ),

    }





def cambiar_clase(

    pack: str,

    classes: List[str],

    mambo_class: str,

    qty: int = 1,

) -> Dict[str, Any]:

    """

    Rewrite selected item classes to extend mambo_class.

    Injects missing Mambo bases from a donor pack when needed.

    """

    from core.item_catalog import BAG_MAMBO, HOUSE_MAMBO, VISUALIZER_MAMBO, _BASE_MAMBO



    pack = (pack or "").replace(".swf", "").strip()

    mambo_class = (mambo_class or "").strip()

    try:

        qty_n = max(1, min(99, int(qty or 1)))

    except (TypeError, ValueError):

        qty_n = 1

    allowed = set(VISUALIZER_MAMBO) | set(HOUSE_MAMBO) | set(BAG_MAMBO)

    if not pack:

        return {"ok": False, "error": "Falta el pack"}

    if mambo_class not in allowed:

        return {"ok": False, "error": f"Clase Mambo no soportada: {mambo_class}"}



    clean_classes: List[str] = []

    for raw in classes or []:

        name = str(raw or "").replace(".as", "").strip()

        if not name or name.endswith("_on"):

            continue

        if name in _BASE_MAMBO or name in allowed:

            continue

        if name not in clean_classes:

            clean_classes.append(name)

    if not clean_classes:

        return {"ok": False, "error": "No hay clases válidas para cambiar"}



    src_swf = ensure_swf_cached(pack)

    if not src_swf or not src_swf.exists():

        return {"ok": False, "error": f"No se pudo encontrar {pack}.swf"}



    # Holder/MiniGame inyectados cuelgan el MG o abren jueguitos (Gaturrin, etc.).

    # Si la base pedida no está en el SWF virgen, o es unsafe, preferir NpcMamboAsset.

    remapped_from = ""

    try:

        from core import item_catalog as _ic

        virgin = _ic.load_pack(pack, prefer_override=False) or src_swf.read_bytes()

        virgin_info = _ic.list_class_info(virgin) if virgin else {}

        virgin_bases = {n for n in virgin_info if n in _known_mambo_bases()}

    except Exception:

        virgin_bases = set()

    needs_remap = (

        mambo_class not in virgin_bases

        or mambo_class in UNSAFE_INJECT_BASES

    )

    if needs_remap:

        for alt in ("NpcMamboAsset", "OwnedNpcMamboAsset", "HouseMamboAsset"):

            if alt in virgin_bases and alt in HOUSE_MAMBO and alt != mambo_class:

                remapped_from = mambo_class

                mambo_class = alt

                break

        if mambo_class in UNSAFE_INJECT_BASES and mambo_class not in virgin_bases:

            return {

                "ok": False,

                "error": (

                    f"{mambo_class} no está en {pack}.swf y no se puede inyectar "

                    "(rompe el juego). Probá NpcMamboAsset."

                ),

            }



    # Snapshot for rollback

    all_overrides = _load_class_overrides()

    pack_map = all_overrides.get(pack) if isinstance(all_overrides.get(pack), dict) else {}

    pack_map = dict(pack_map)

    previous_snapshot = {k: pack_map.get(k) for k in clean_classes}



    # If leaving cloth family, drop clothes tricks for these classes so rebuild

    # doesn't force ClothMamboAsset back on them.

    tricks = _load_tricks()

    pack_tricks = tricks.get(pack) if isinstance(tricks.get(pack), dict) else {}

    dropped_clothes: List[str] = []

    if mambo_class not in VISUALIZER_MAMBO and isinstance(pack_tricks, dict):

        for cls in clean_classes:

            if cls in pack_tricks:

                pack_tricks.pop(cls, None)

                dropped_clothes.append(cls)

        if dropped_clothes:

            if pack_tricks:

                tricks[pack] = pack_tricks

            else:

                tricks.pop(pack, None)

            _save_tricks(tricks)



    import time

    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    for cls in clean_classes:

        prev_to = None

        if isinstance(previous_snapshot.get(cls), dict):

            prev_to = previous_snapshot[cls].get("to")

        pack_map[cls] = {

            "from": prev_to or "",

            "to": mambo_class,

            "qty": qty_n,

            "at": now,

        }

    all_overrides[pack] = pack_map

    _save_class_overrides(all_overrides)



    rebuilt = _rebuild_pack_override(pack, require_class=clean_classes[0])

    if not rebuilt.get("ok"):

        # Rollback class map

        for cls in clean_classes:

            prev = previous_snapshot.get(cls)

            if prev is None:

                pack_map.pop(cls, None)

            else:

                pack_map[cls] = prev

        if pack_map:

            all_overrides[pack] = pack_map

        else:

            all_overrides.pop(pack, None)

        _save_class_overrides(all_overrides)

        return rebuilt



    # Soft validation against override SWF when possible

    verified: List[Dict[str, str]] = []

    try:

        from core import item_catalog

        item_catalog.invalidate_pack_cache(pack)

        items = item_catalog.list_pack_items(pack).get("items") or []

        by_name = {it.get("name"): it for it in items if isinstance(it, dict)}

        for cls in clean_classes:

            it = by_name.get(cls) or {}

            verified.append({

                "name": cls,

                "mambo_class": str(it.get("class") or mambo_class),

                "inventory": str(it.get("inventory") or ""),

                "inventory_label": str(it.get("inventory_label") or ""),

            })

    except Exception:

        verified = [{"name": c, "mambo_class": mambo_class} for c in clean_classes]



    inv = (

        "visualizer" if mambo_class in VISUALIZER_MAMBO

        else "house" if mambo_class in HOUSE_MAMBO

        else "default"

    )

    injected = list(rebuilt.get("injected_bases") or [])

    inject_msg = f" (inyecté {', '.join(injected)})" if injected else ""

    remap_msg = (

        f" (pediste {remapped_from}, usé {mambo_class} para no colgar el cliente)"

        if remapped_from else ""

    )

    return {

        "ok": True,

        "pack": pack,

        "mambo_class": mambo_class,

        "remapped_from": remapped_from or None,

        "inventory": inv,

        "changed": clean_classes,

        "count": len(clean_classes),

        "dropped_clothes": dropped_clothes,

        "injected_bases": injected,

        "swf_file": rebuilt.get("swf_file"),

        "verified": verified,

        "items": [f"{pack}.{c}" for c in clean_classes],

        "qty": qty_n,

        "message": (

            f"Listo: {len(clean_classes)} objeto{'s' if len(clean_classes) != 1 else ''} "

            f"-> {mambo_class}{remap_msg}{inject_msg} · x{qty_n}."

        ),

    }

