"""Lee el SWF de catálogo (Desktop/assets/food.swf, costumes.swf, …)
como hace inventory.add: instancia la clase del ítem y copia sus attrs.

No hace falta Flash: parsea el ABC (frame1 / ctor) y saca
session, uses, adds.action, adds.effect, wear_*, sizeW, etc.
"""
from __future__ import annotations

import os
import struct
import xml.etree.ElementTree as ET
import zlib

_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
_REPO_ROOT = os.path.abspath(os.path.join(_DATA_DIR, ".."))
CDN_BASE = "https://cdn-ar.mundogaturro.com/juego/assets/"
CACHE_DIR = os.path.join(_DATA_DIR, "swf_cache")

ASSET_DIRS = [
    os.path.join(os.path.expanduser("~"), "Desktop", "assets"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"),
    os.path.join(_REPO_ROOT, "swfs", "assets"),
    CACHE_DIR,
]
ASSETS_XML_URL = "https://asset-viewer-seven.vercel.app/assets/assets.xml"
ASSETS_XML_PATH = os.path.join(_DATA_DIR, "assets.xml")

INV_LABELS = {
    "default": "mochila",
    "visualizer": "ropa puesta",
    "house": "casa",
}

# Props típicas de clips Mambo / ConsumableMamboAsset / ropa
ATTR_KEYS = {
    "session", "uses", "grabbable", "questItem", "blocks", "blockingHint",
    "action", "effect", "sizeW", "sizeH", "size", "clothes", "stackBy",
    "behavior", "flipped", "vehicle", "attr_effect", "wearable", "attr_action",
}
SKIP_KEYS = {
    "attributes", "adds", "name", "parent", "root", "stage", "visible",
    "alpha", "x", "y", "z", "width", "height", "rotation", "scaleX", "scaleY",
    "currentFrame", "totalFrames", "mouseX", "mouseY", "filters", "mask",
    "blendMode", "cacheAsBitmap", "opaqueBackground", "tabEnabled", "buttonMode",
}
CLOTH_PACKS = {
    "costumes", "costume", "clothes", "wears", "wear", "shoes", "hats", "hairs",
    "mouths", "neck", "accesories", "cloth", "arm", "leg", "foot", "glove",
    "grip", "transport", "effect", "medal",
}

# InventoryUtil.acquireObject: el inventario lo decide el tipo de SceneObject,
# que en el SWF es la clase Mambo. No usar grabbable (los NPC de casa también lo tienen).
VISUALIZER_MAMBO = {
    "ClothMamboAsset",
    "PetClothMamboAsset",
    "TransportMamboAsset",
    "TransportOnMamboAsset",
    "EvolveMamboAsset",
    "TransportInventorySceneObject",
}
HOUSE_MAMBO = {
    "NpcMamboAsset",
    "OwnedNpcMamboAsset",
    "NpcHolderMamboAsset",
    "HolderMamboAsset",
    "HouseMamboAsset",
    "HouseDecorationMamboAsset",
    "HomeInteractiveMamboAsset",
    "VendorMamboAsset",
    "BannerMamboAsset",
    "ImageMamboAsset",
    "MiniGameMamboAsset",
    "PersonalPropertyMamboAsset",
    "MamboAsset",
}
BAG_MAMBO = {
    "ConsumableMamboAsset",
    "UsableMamboAsset",
    "GrabbableMamboAsset",
    "PetFoodMamboAsset",
    "PetCareMamboAsset",
    "PetToyMamboAsset",
}


def _u30(buf, p):
    r = 0
    s = 0
    while True:
        b = buf[p]
        p += 1
        r |= (b & 0x7F) << s
        if not (b & 0x80):
            break
        s += 7
        if s > 35:
            raise ValueError("u30")
    return r, p


def _s32(buf, p):
    r = 0
    s = 0
    while True:
        b = buf[p]
        p += 1
        r |= (b & 0x7F) << s
        if not (b & 0x80):
            if b & 0x40 and s < 25:
                r |= -1 << (s + 7)
            break
        s += 7
        if s > 35:
            raise ValueError("s32")
    return r, p


def _swf_payload(data: bytes) -> bytes:
    if len(data) < 8:
        return data
    sig = data[:3]
    body = data[8:]
    if sig == b"CWS":
        return zlib.decompress(body)
    if sig == b"ZWS":
        try:
            import lzma
            return lzma.decompress(body)
        except Exception:
            return data
    return data if sig == b"FWS" else data


def _abc_tags(swf_body: bytes):
    if swf_body[:3] in (b"FWS", b"CWS", b"ZWS"):
        data = swf_body
        i = 8
    else:
        data = b"FWS\x0a" + struct.pack("<I", 8 + len(swf_body)) + swf_body
        i = 8
    nbits = data[i] >> 3
    i += (5 + nbits * 4 + 7) // 8
    i += 4
    out = []
    while i + 2 <= len(data):
        rec = struct.unpack_from("<H", data, i)[0]
        i += 2
        code = rec >> 6
        ln = rec & 0x3F
        if ln == 0x3F:
            if i + 4 > len(data):
                break
            ln = struct.unpack_from("<I", data, i)[0]
            i += 4
        payload = data[i : i + ln]
        i += ln
        if code == 82:
            out.append(payload)
        if code == 0:
            break
    return out


def _iter_swf_tags(swf_body: bytes):
    if swf_body[:3] in (b"FWS", b"CWS", b"ZWS"):
        data = swf_body
        i = 8
    else:
        data = b"FWS\x0a" + struct.pack("<I", 8 + len(swf_body)) + swf_body
        i = 8
    if i >= len(data):
        return
    nbits = data[i] >> 3
    i += (5 + nbits * 4 + 7) // 8
    i += 4
    while i + 2 <= len(data):
        rec = struct.unpack_from("<H", data, i)[0]
        i += 2
        code = rec >> 6
        ln = rec & 0x3F
        if ln == 0x3F:
            if i + 4 > len(data):
                break
            ln = struct.unpack_from("<I", data, i)[0]
            i += 4
        payload = data[i : i + ln]
        i += ln
        yield code, payload
        if code == 0:
            break


def _iter_raw_tags(buf: bytes, start: int = 0):
    """Tags SWF desde un offset (p.ej. cuerpo de DefineSprite, sin RECT)."""
    i = start
    n = len(buf)
    while i + 2 <= n:
        rec = struct.unpack_from("<H", buf, i)[0]
        i += 2
        code = rec >> 6
        ln = rec & 0x3F
        if ln == 0x3F:
            if i + 4 > n:
                break
            ln = struct.unpack_from("<I", buf, i)[0]
            i += 4
        payload = buf[i : i + ln]
        i += ln
        yield code, payload
        if code == 0:
            break


def _parse_abc(tag: bytes):
    payload = tag
    p = 4
    z = payload.find(b"\x00", p)
    if z < 0:
        return None
    p = z + 1
    p += 4
    n, p = _u30(payload, p)
    for _ in range(max(0, n - 1)):
        _, p = _s32(payload, p)
    n, p = _u30(payload, p)
    ints = [0]
    for _ in range(max(0, n - 1)):
        v, p = _u30(payload, p)
        ints.append(v)
    n, p = _u30(payload, p)
    p += 8 * max(0, n - 1)
    n, p = _u30(payload, p)
    strs = [""]
    for _ in range(max(0, n - 1)):
        ln, p = _u30(payload, p)
        s = payload[p : p + ln]
        p += ln
        try:
            strs.append(s.decode("utf-8"))
        except Exception:
            strs.append(s.decode("latin1", "replace"))
    n, p = _u30(payload, p)
    nss = [(0, 0)]
    for _ in range(max(0, n - 1)):
        kind = payload[p]
        p += 1
        name, p = _u30(payload, p)
        nss.append((kind, name))
    n, p = _u30(payload, p)
    for _ in range(max(0, n - 1)):
        c, p = _u30(payload, p)
        for __ in range(c):
            _, p = _u30(payload, p)
    n, p = _u30(payload, p)
    mns = [None]
    for _ in range(max(0, n - 1)):
        kind = payload[p]
        p += 1
        info = {"kind": kind}
        if kind in (0x07, 0x0D):
            ns, p = _u30(payload, p)
            name, p = _u30(payload, p)
            info["ns"] = ns
            info["name"] = name
        elif kind in (0x0F, 0x10):
            name, p = _u30(payload, p)
            info["name"] = name
        elif kind in (0x11, 0x12):
            pass
        elif kind in (0x09, 0x0E):
            name, p = _u30(payload, p)
            nsset, p = _u30(payload, p)
            info["name"] = name
        elif kind in (0x1B, 0x1C):
            _, p = _u30(payload, p)
        elif kind == 0x1D:
            name, p = _u30(payload, p)
            cnt, p = _u30(payload, p)
            for __ in range(cnt):
                _, p = _u30(payload, p)
            info["name"] = name
        else:
            return None
        mns.append(info)

    def mn_leaf(idx):
        if not idx or idx >= len(mns) or mns[idx] is None:
            return ""
        m = mns[idx]
        return strs[m["name"]] if m.get("name") and m["name"] < len(strs) else ""

    n, p = _u30(payload, p)
    for _ in range(n):
        pcount, p = _u30(payload, p)
        _, p = _u30(payload, p)
        for __ in range(pcount):
            _, p = _u30(payload, p)
        _, p = _u30(payload, p)
        flags = payload[p]
        p += 1
        if flags & 0x08:
            opt, p = _u30(payload, p)
            for __ in range(opt):
                _, p = _u30(payload, p)
                p += 1
        if flags & 0x80:
            for __ in range(pcount):
                _, p = _u30(payload, p)
    n, p = _u30(payload, p)
    for _ in range(n):
        _, p = _u30(payload, p)
        ic, p = _u30(payload, p)
        for __ in range(ic):
            _, p = _u30(payload, p)
            _, p = _u30(payload, p)

    def parse_traits(p, count):
        traits = []
        for _ in range(count):
            name, p = _u30(payload, p)
            kindb = payload[p]
            p += 1
            kind = kindb & 0x0F
            attr = kindb >> 4
            t = {"name": name, "kind": kind}
            if kind in (0, 6):
                _, p = _u30(payload, p)
                _, p = _u30(payload, p)
                vindex, p = _u30(payload, p)
                if vindex:
                    p += 1
            elif kind in (1, 2, 3):
                _, p = _u30(payload, p)
                method, p = _u30(payload, p)
                t["method"] = method
            elif kind in (4, 5):
                _, p = _u30(payload, p)
                _, p = _u30(payload, p)
            else:
                raise ValueError(kind)
            if attr & 0x4:
                mc, p = _u30(payload, p)
                for __ in range(mc):
                    _, p = _u30(payload, p)
            traits.append(t)
        return traits, p

    nclass, p = _u30(payload, p)
    instances = []
    for _ in range(nclass):
        name, p = _u30(payload, p)
        super_name, p = _u30(payload, p)
        flags = payload[p]
        p += 1
        if flags & 0x08:
            _, p = _u30(payload, p)
        icount, p = _u30(payload, p)
        for __ in range(icount):
            _, p = _u30(payload, p)
        iinit, p = _u30(payload, p)
        tcount, p = _u30(payload, p)
        traits, p = parse_traits(p, tcount)
        instances.append({"name": name, "super": super_name, "iinit": iinit, "traits": traits})
    class_traits = []
    cinits = []
    for _ in range(nclass):
        cinit, p = _u30(payload, p)
        tcount, p = _u30(payload, p)
        traits, p = parse_traits(p, tcount)
        class_traits.append(traits)
        cinits.append(cinit)
    nscript, p = _u30(payload, p)
    for _ in range(nscript):
        _, p = _u30(payload, p)
        tcount, p = _u30(payload, p)
        _, p = parse_traits(p, tcount)
    nbody, p = _u30(payload, p)
    bodies = {}
    for _ in range(nbody):
        method, p = _u30(payload, p)
        _, p = _u30(payload, p)
        _, p = _u30(payload, p)
        _, p = _u30(payload, p)
        _, p = _u30(payload, p)
        clen, p = _u30(payload, p)
        code = payload[p : p + clen]
        p += clen
        exc, p = _u30(payload, p)
        for __ in range(exc):
            for ___ in range(5):
                _, p = _u30(payload, p)
        tcount, p = _u30(payload, p)
        _, p = parse_traits(p, tcount)
        bodies[method] = code
    return {
        "strs": strs,
        "mn_leaf": mn_leaf,
        "instances": instances,
        "class_traits": class_traits,
        "cinits": cinits,
        "bodies": bodies,
    }


def _scan_attrs(code: bytes, mn_leaf, ints=None):
    """Best-effort: push + setproperty → {key: value}."""
    attrs = {}
    i = 0
    last_str = None
    last_num = None
    last_bool = None
    last_mn = None
    n = len(code)

    def read_u30(j):
        r = 0
        s = 0
        while j < n:
            b = code[j]
            j += 1
            r |= (b & 0x7F) << s
            if not (b & 0x80):
                break
            s += 7
            if s > 35:
                return -1, j
        return r, j

    while i < n:
        op = code[i]
        i += 1
        if op == 0x2C:  # pushstring
            r, i = read_u30(i)
            last_str = r
            last_num = None
            last_bool = None
        elif op == 0x26:  # pushtrue
            last_bool = True
            last_str = None
            last_num = None
        elif op == 0x27:  # pushfalse
            last_bool = False
            last_str = None
            last_num = None
        elif op == 0x24:  # pushbyte
            if i < n:
                last_num = struct.unpack("b", bytes([code[i]]))[0]
                i += 1
            last_str = None
            last_bool = None
        elif op == 0x25:  # pushshort
            r, i = read_u30(i)
            last_num = r
            last_str = None
            last_bool = None
        elif op in (0x2D, 0x2E):  # pushint / pushuint pool
            r, i = read_u30(i)
            last_num = r
            last_str = None
            last_bool = None
        elif op in (0x60, 0x5D, 0x5E, 0x66):  # getlex / findprop / getproperty
            r, i = read_u30(i)
            last_mn = mn_leaf(r)
        elif op in (0x61, 0x68):  # setproperty / initproperty
            r, i = read_u30(i)
            key = mn_leaf(r)
            val = None
            if last_bool is not None:
                val = last_bool
            elif last_str is not None:
                # last_str is pool index; caller patches via closure? we need strs
                val = ("str", last_str)
            elif last_num is not None:
                val = last_num
            if key:
                if last_mn in ("adds", "add") and key:
                    attrs["adds." + key] = val
                    attrs[key] = val
                else:
                    attrs[key] = val
            last_str = last_num = last_bool = None
        elif op in (0x46, 0x4A, 0x4F):
            _, i = read_u30(i)
            _, i = read_u30(i)
    return attrs


def _leaf(mn_idx, abc):
    return abc["mn_leaf"](mn_idx).split(":")[-1]


def _resolve_str_vals(attrs, strs):
    out = {}
    for k, v in attrs.items():
        if isinstance(v, tuple) and v and v[0] == "str":
            idx = v[1]
            if 0 < idx < len(strs):
                out[k] = strs[idx]
            continue
        out[k] = v
    return out


def _class_methods(abc, inst, class_traits, cinit):
    methods = [inst.get("iinit"), cinit]
    for t in inst.get("traits") or []:
        if "method" in t:
            methods.append(t["method"])
    for t in class_traits or []:
        if "method" in t:
            methods.append(t["method"])
    return [m for m in methods if m is not None]


def extract_class_attrs(swf_bytes: bytes, class_names):
    """Attrs of the first matching class (+ parent chain). class_names: iterable of leaf names."""
    want = {str(x) for x in class_names if x}
    data = _swf_payload(swf_bytes)
    tags = _abc_tags(data)
    if not tags:
        # uncompressed payload might already be the file after CWS decompress
        tags = _abc_tags(swf_bytes)
    merged = {}
    for tag in tags:
        try:
            abc = _parse_abc(tag)
        except Exception:
            continue
        if not abc:
            continue
        by_leaf = {}
        for i, inst in enumerate(abc["instances"]):
            leaf = _leaf(inst["name"], abc)
            by_leaf[leaf] = (i, inst)
        # parent first then child
        chain = []
        for name in want:
            if name not in by_leaf:
                continue
            i, inst = by_leaf[name]
            seen = set()
            cur = inst
            idx = i
            stack = []
            while cur is not None and idx not in seen:
                seen.add(idx)
                stack.append((idx, cur))
                sleaf = _leaf(cur["super"], abc)
                if sleaf in by_leaf:
                    idx, cur = by_leaf[sleaf]
                else:
                    break
            chain.extend(reversed(stack))
        for idx, inst in chain:
            for mid in _class_methods(abc, inst, abc["class_traits"][idx], abc["cinits"][idx]):
                code = abc["bodies"].get(mid, b"")
                raw = _scan_attrs(code, abc["mn_leaf"])
                merged.update(_resolve_str_vals(raw, abc["strs"]))
        if merged:
            break
    return merged


def _pack_relpath(pack_name: str) -> str:
    rel = (pack_name or "").replace("\\", "/").strip("/")
    if not rel.lower().endswith(".swf"):
        rel += ".swf"
    return rel


def find_pack_swf(pack_name: str, prefer_override: bool = False):
    fname = _pack_relpath(pack_name)
    parts = fname.split("/")
    # Overrides are for inspect/preview after tricks — never as rebuild source.
    if prefer_override:
        override = os.path.join(_DATA_DIR, "overrides", *parts)
        if os.path.isfile(override):
            return override
    dirs = list(ASSET_DIRS)
    if CACHE_DIR not in dirs:
        dirs.insert(0, CACHE_DIR)
    for d in dirs:
        path = os.path.join(d, *parts)
        if os.path.isfile(path):
            return path
        path2 = os.path.join(d, "assets", *parts)
        if os.path.isfile(path2):
            return path2
    if prefer_override:
        return None
    # Fallback: override only if no original exists.
    override = os.path.join(_DATA_DIR, "overrides", *parts)
    if os.path.isfile(override):
        return override
    return None


_pack_cache = {}
_class_cache = {}


def invalidate_pack_cache(pack_name: str = "") -> None:
    """Drop in-memory SWF/ABC caches so inspect sees a fresh override."""
    pack = (pack_name or "").replace(".swf", "").strip().replace("\\", "/").strip("/")
    if not pack:
        _pack_cache.clear()
        _class_cache.clear()
        return
    _pack_cache.pop(pack, None)
    _class_cache.pop(pack, None)
    for key in list(_pack_cache.keys()):
        if str(key).replace("\\", "/").endswith(pack) or str(key) == pack:
            _pack_cache.pop(key, None)
    for key in list(_class_cache.keys()):
        if str(key).replace("\\", "/").endswith(pack) or str(key) == pack:
            _class_cache.pop(key, None)


def _download_pack(pack_name: str):
    try:
        import urllib.request
        rel = _pack_relpath(pack_name).replace("\\", "/")
        url = CDN_BASE + rel
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if data[:3] in (b"CWS", b"FWS", b"ZWS"):
            dest = os.path.join(CACHE_DIR, *rel.split("/"))
            os.makedirs(os.path.dirname(dest) or CACHE_DIR, exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)
            return data
    except Exception:
        return None
    return None


def load_pack(pack_name: str, prefer_override: bool = False):
    cache_key = f"{pack_name}::ovr" if prefer_override else pack_name
    if cache_key in _pack_cache:
        return _pack_cache[cache_key]
    path = find_pack_swf(pack_name, prefer_override=prefer_override)
    data = None
    if path:
        with open(path, "rb") as f:
            data = f.read()
    if not data and not prefer_override:
        data = _download_pack(pack_name)
    _pack_cache[cache_key] = data
    return data


def list_class_info(swf_bytes: bytes):
    """{classLeaf: superLeaf}"""
    body = _swf_payload(swf_bytes)
    tags = _abc_tags(body) or _abc_tags(swf_bytes)
    info = {}
    for tag in tags:
        try:
            abc = _parse_abc(tag)
        except Exception:
            continue
        if not abc:
            continue
        for inst in abc["instances"]:
            info[_leaf(inst["name"], abc)] = _leaf(inst["super"], abc)
    return info


def _class_info_of(pack_name: str, data: bytes):
    if pack_name not in _class_cache:
        try:
            _class_cache[pack_name] = list_class_info(data)
        except Exception:
            _class_cache[pack_name] = {}
    return _class_cache[pack_name]


def _extends_mambo(leaf, info: dict) -> bool:
    seen = set()
    cur = leaf
    while cur and cur not in seen:
        if "MamboAsset" in cur:
            return True
        seen.add(cur)
        cur = info.get(cur)
    return False


def _mambo_class(leaf, info: dict):
    """ConsumableMamboAsset / ClothMamboAsset / GrabbableMamboAsset / …"""
    seen = set()
    cur = leaf
    while cur and cur not in seen:
        if cur.endswith("MamboAsset"):
            return cur
        seen.add(cur)
        cur = info.get(cur)
    return None


def _pick_mambo_leaf(leaf: str, info: dict) -> str:
    """El _on suele ser Sprite (solo dibujo). La clase con process() es sin _on (ClothMamboAsset, etc.)."""
    base = leaf[:-3] if leaf.endswith("_on") else leaf
    on = base + "_on"
    if _extends_mambo(base, info):
        return base
    if _extends_mambo(on, info):
        return on
    if base in info:
        return base
    if on in info:
        return on
    return leaf


def _interesting(attrs: dict):
    keep = {}
    for k, v in attrs.items():
        if v is None or v == "":
            continue
        kl = str(k)
        if kl in SKIP_KEYS or kl.startswith("adds."):
            if kl.startswith("adds.") and kl[5:] and kl[5:] not in SKIP_KEYS:
                keep[kl[5:]] = v
            continue
        if kl in ATTR_KEYS or kl.startswith("wear_") or kl.startswith("attr_"):
            keep[kl] = v
    return keep


def wear_key_para(item_name: str) -> str:
    category = item_name.split(".")[0] if "." in item_name else item_name
    mapping = {
        "hats3": "wear_hats3", "hats2": "wear_hats2", "hats": "wear_hats",
        "hairs3": "wear_hairs3", "hairs2": "wear_hairs2", "hairs": "wear_hairs",
        "mouths3": "wear_mouths3", "mouths2": "wear_mouths2", "mouths": "wear_mouths",
        "neck3": "wear_neck3", "neck2": "wear_neck2", "neck": "wear_neck",
        "accesories3": "wear_accesories3", "accesories2": "wear_accesories2",
        "accesories": "wear_accesories",
        "clothFront": "wear_clothFront", "clothBack": "wear_clothBack", "cloth": "wear_cloth",
        "armFore": "wear_armFore", "armBack": "wear_armBack", "arm": "wear_arm",
        "gloveFore": "wear_gloveFore", "gloveBack": "wear_gloveBack", "glove": "wear_glove",
        "gripFore": "wear_gripFore", "gripBack": "wear_gripBack", "grip": "wear_grip",
        "leg": "wear_leg", "foot": "wear_foot", "shoes": "wear_foot",
        "transport": "vehicle", "effect": "attr_effect",
        "customization": "wear_customization", "special_ph": "wear_special_ph",
    }
    for k, v in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        if category.startswith(k):
            return v
    return "wear_cloth"


def inv_from_mambo_class(mambo: str | None, item_name: str = "") -> str | None:
    """default=mochila, visualizer=ropa puesta, house=armario de casa."""
    if not mambo:
        return None
    if mambo in VISUALIZER_MAMBO:
        return "visualizer"
    if mambo in HOUSE_MAMBO:
        return "house"
    if mambo in BAG_MAMBO:
        return "default"
    return None


def _inv_from_attrs(item_name: str, attrs: dict) -> str:
    pack = item_name.split(".")[0] if "." in item_name else item_name
    name = item_name or ""
    if attrs.get("vehicle") or any(str(k).startswith("wear_") for k in attrs):
        return "visualizer"
    if name.endswith("_on") or pack.lower() in CLOTH_PACKS:
        return "visualizer"
    if attrs.get("uses") is not None or str(attrs.get("action") or "").startswith("eat."):
        return "default"
    if (
        name.endswith("_so") or name.endswith("_soN") or ".main" in name
        or pack in ("furniture", "house", "wall", "floor", "wallpaper", "poster", "door")
    ):
        return "house"
    return "default"


def heuristica_si_falta(item_name: str, extracted: dict) -> dict:
    """Completa lo que MovieClip.process copiaría (UsableMamboAsset adds → attr_*)."""
    name = (item_name or "").strip()
    pack = name.split(".")[0] if "." in name else name
    out = dict(extracted)
    if pack == "food" or pack.startswith("food"):
        if "uses" not in out:
            out["uses"] = 1
        if "action" not in out:
            out["action"] = "eat." + name
        if "session" not in out:
            out["session"] = True
    # UsableMamboAsset.process: for (k in adds) attributes["attr_"+k] = adds[k]
    if out.get("action") and "attr_action" not in out:
        out["attr_action"] = out["action"]
    if out.get("effect") and "attr_effect" not in out:
        out["attr_effect"] = out["effect"]
    return out


def resolver_item(item_name: str, inventario=None):
    """Nombre = clase Mambo del SWF (no el Sprite _on). Inventario automático por esa clase.

    inventario se ignora: lo decide la clase Mambo (ver inv_from_mambo_class).
    """
    raw_name = (item_name or "").strip()
    if "." not in raw_name:
        return raw_name, "default", {}
    pack, leaf = raw_name.split(".", 1)
    leaf = leaf.split("::")[0]
    data = load_pack(pack)
    info = _class_info_of(pack, data) if data else {}
    resolved_leaf = _pick_mambo_leaf(leaf, info) if info else leaf
    resolved_name = pack + "." + resolved_leaf
    attrs = {}
    if data:
        attrs.update(_interesting(extract_class_attrs(data, [resolved_leaf])))
    attrs = heuristica_si_falta(resolved_name, attrs)
    mambo = _mambo_class(resolved_leaf, info) if info else None
    if mambo:
        attrs["_class"] = mambo
    clothes = attrs.get("clothes")
    if isinstance(clothes, str) and clothes and "." not in clothes:
        attrs["clothes"] = pack + "." + clothes
    graphic = resolved_leaf
    on = (resolved_leaf[:-3] if resolved_leaf.endswith("_on") else resolved_leaf) + "_on"
    if info and on in info:
        graphic = on
    inv = inv_from_mambo_class(mambo, resolved_name) or _inv_from_attrs(resolved_name, attrs)
    is_cloth = inv == "visualizer"
    if is_cloth:
        wk = wear_key_para(resolved_name)
        if not any(str(k).startswith("wear_") for k in attrs):
            # el name es la clase Mambo; wear_* apunta al Sprite gráfico (_on)
            attrs[wk] = pack + "." + graphic
    return resolved_name, inv, attrs


def attrs_desde_catalogo(item_name: str) -> dict:
    _n, _inv, attrs = resolver_item(item_name)
    return attrs


def item_category(mambo: str | None, inv: str) -> str:
    if mambo in ("TransportMamboAsset", "TransportOnMamboAsset", "TransportInventorySceneObject"):
        return "vehicle"
    if inv == "visualizer" or mambo in VISUALIZER_MAMBO:
        return "visualizer"
    if inv == "house" or mambo in HOUSE_MAMBO:
        return "house"
    if inv == "default" or mambo in BAG_MAMBO:
        return "bag"
    return "object"


def _download_assets_xml(force: bool = False) -> bool:
    if os.path.isfile(ASSETS_XML_PATH) and not force:
        return True
    try:
        import urllib.request
        req = urllib.request.Request(ASSETS_XML_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if b"<file" not in data:
            return os.path.isfile(ASSETS_XML_PATH)
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(ASSETS_XML_PATH, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return os.path.isfile(ASSETS_XML_PATH)


def _scan_local_swfs():
    found = []
    seen = set()
    dirs = list(ASSET_DIRS)
    if CACHE_DIR not in dirs:
        dirs.append(CACHE_DIR)
    skip_names = {"preview.swf", "mmo.swf", "mmonuevo.swf"}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, dirnames, files in os.walk(d):
            dirnames[:] = [x for x in dirnames if x not in (".git", "__pycache__")]
            for fn in files:
                if fn.lower() not in skip_names and fn.lower().endswith(".swf"):
                    rel = os.path.relpath(os.path.join(root, fn), d)
                    pack = rel[:-4].replace("\\", "/")
                    if pack and pack not in seen:
                        seen.add(pack)
                        found.append(pack)
    return found


def list_all_packs(refresh: bool = False):
    """Lista SWF del catálogo (assets.xml) + los que haya en disco."""
    _download_assets_xml(force=refresh)
    packs = []
    seen = set()
    if os.path.isfile(ASSETS_XML_PATH):
        try:
            tree = ET.parse(ASSETS_XML_PATH)
            for el in tree.findall(".//file"):
                path = (el.get("path") or "").replace("\\", "/")
                if path.lower().endswith(".swf"):
                    path = path[:-4]
                pack = path.strip("/")
                if pack and pack not in seen:
                    seen.add(pack)
                    packs.append(pack)
        except Exception:
            pass
    for pack in _scan_local_swfs():
        if pack not in seen:
            seen.add(pack)
            packs.append(pack)
    packs.sort(key=lambda p: p.lower())
    out = []
    for pack in packs:
        parts = pack.split("/")
        out.append({
            "pack": pack,
            "name": parts[-1],
            "folder": "/".join(parts[:-1]) if len(parts) > 1 else "",
        })
    return out


_BASE_MAMBO = VISUALIZER_MAMBO | HOUSE_MAMBO | BAG_MAMBO | {
    "MamboAsset",
    "UsableMamboAsset",
    "GrabbableMamboAsset",
}


def _is_item_leaf(leaf: str, info: dict) -> bool:
    if not leaf or leaf.startswith("_"):
        return False
    if leaf.endswith("_on"):
        return False
    if "." in leaf or ":" in leaf or "$" in leaf:
        return False
    if leaf in _BASE_MAMBO or leaf in ("MainTimeline", "DocumentClass", "Item", "Object", "Sprite", "MovieClip"):
        return False
    mambo = _mambo_class(leaf, info)
    if mambo:
        return True
    return _extends_mambo(leaf, info)


def list_pack_items(pack_name: str, prefer_override: bool = True):
    """Clases Mambo de un SWF (sin sprites _on). Uses override when present."""
    pack = (pack_name or "").replace("\\", "/").strip("/")
    if pack.lower().endswith(".swf"):
        pack = pack[:-4]
    if not pack:
        return {"ok": False, "error": "Falta el pack", "pack": "", "items": []}
    data = load_pack(pack, prefer_override=prefer_override)
    if not data:
        data = load_pack(pack, prefer_override=False)
    if not data:
        return {"ok": False, "error": f"No pude bajar {pack}.swf", "pack": pack, "items": []}
    try:
        # Cache stays until invalidate_pack_cache() (after class change / rebuild).
        info = _class_info_of(pack, data)
    except Exception:
        info = {}
    items = []
    seen = set()
    for leaf in info:
        if not _is_item_leaf(leaf, info):
            continue
        resolved = _pick_mambo_leaf(leaf, info)
        if resolved.endswith("_on") or resolved in seen:
            continue
        if not _is_item_leaf(resolved, info) and resolved != leaf:
            continue
        seen.add(resolved)
        mambo = _mambo_class(resolved, info)
        full = pack + "." + resolved
        inv = inv_from_mambo_class(mambo, full) or _inv_from_attrs(full, {})
        cat = item_category(mambo, inv)
        spr = item_sprite_frames(pack, resolved)
        items.append({
            "id": resolved,
            "name": resolved,
            "pack": pack,
            "item": full,
            "class": mambo or "",
            "inventory": inv,
            "inventory_label": INV_LABELS.get(inv, inv),
            "category": cat,
            "so": resolved.endswith("_so") or resolved.endswith("_soN"),
            "frameCount": spr.get("frames") or 1,
            "animated": bool(spr.get("animated")),
        })
    items.sort(key=lambda it: it["name"].lower())
    return {
        "ok": True,
        "pack": pack,
        "cdn": CDN_BASE + pack + ".swf",
        "count": len(items),
        "items": items,
    }


def _jpeg_blob(payload: bytes, with_alpha: bool) -> bytes | None:
    if len(payload) < 4:
        return None
    data = payload[2:]
    if with_alpha:
        if len(data) < 4:
            return None
        off = struct.unpack_from("<I", data, 0)[0]
        data = data[4:4 + off] if off else data[4:]
    idx = data.find(b"\xff\xd8")
    if idx < 0:
        return None
    jpeg = data[idx:]
    end = jpeg.rfind(b"\xff\xd9")
    if end >= 0:
        jpeg = jpeg[: end + 2]
    if len(jpeg) < 32:
        return None
    return jpeg


def _parse_symbol_class(payload: bytes):
    if len(payload) < 2:
        return []
    n = struct.unpack_from("<H", payload, 0)[0]
    p = 2
    out = []
    for _ in range(n):
        if p + 2 > len(payload):
            break
        cid = struct.unpack_from("<H", payload, p)[0]
        p += 2
        z = payload.find(b"\x00", p)
        if z < 0:
            break
        name = payload[p:z].decode("utf-8", "replace")
        p = z + 1
        out.append((cid, name))
    return out


_thumb_cache = {}
_sprite_cache = {}


def _sprite_frame_count(payload: bytes) -> tuple[int, dict]:
    """DefineSprite payload → (frameCount, {n: label})."""
    if len(payload) < 4:
        return 1, {}
    header_n = struct.unpack_from("<H", payload, 2)[0]
    shown = 0
    labels = {}
    pending = []
    for code, pl in _iter_raw_tags(payload, 4):
        if code == 43:
            z = pl.find(b"\x00")
            lab = (pl[:z] if z >= 0 else pl).decode("utf-8", "replace").strip()
            if lab:
                pending.append(lab)
        elif code == 1:
            shown += 1
            if pending:
                labels[shown] = pending[-1] if len(pending) == 1 else ",".join(pending)
                pending = []
        elif code == 0:
            break
    count = header_n or shown or 1
    return int(count), labels


def pack_sprite_info(pack_name: str) -> dict:
    """leaf de SymbolClass → {cid, frames, labels, animated} (DefineSprite, como JPEXS)."""
    pack = (pack_name or "").replace("\\", "/").strip("/")
    if pack in _sprite_cache:
        return _sprite_cache[pack]
    data = load_pack(pack)
    out = {}
    if not data:
        _sprite_cache[pack] = out
        return out
    try:
        body = _swf_payload(data)
        sprites = {}
        names = []
        for code, payload in _iter_swf_tags(body):
            if code == 39 and len(payload) >= 4:
                cid = struct.unpack_from("<H", payload, 0)[0]
                n, labels = _sprite_frame_count(payload)
                sprites[cid] = {"cid": cid, "frames": n, "labels": labels, "animated": n > 1}
            elif code in (76, 56):
                names.extend(_parse_symbol_class(payload))
        for cid, raw_name in names:
            leaf = raw_name.split(".")[-1].split(":")[-1]
            if not leaf:
                continue
            sp = sprites.get(cid) or {"cid": cid, "frames": 1, "labels": {}, "animated": False}
            if leaf not in out or sp["frames"] > out[leaf].get("frames", 0):
                out[leaf] = sp
    except Exception:
        pass
    _sprite_cache[pack] = out
    return out


def item_sprite_frames(pack_name: str, leaf: str) -> dict:
    """Frames del sprite ligado a la clase (o al _on si anima más)."""
    leaf = (leaf or "").split(".")[-1]
    if leaf.endswith("_on"):
        base = leaf[:-3]
        on = leaf
    else:
        base = leaf
        on = leaf + "_on"
    info = pack_sprite_info(pack_name)
    a = info.get(base) or info.get(leaf) or {}
    b = info.get(on) or {}
    pick = a
    if (b.get("frames") or 0) > (a.get("frames") or 0):
        pick = b
    n = int(pick.get("frames") or 1)
    return {
        "cid": pick.get("cid"),
        "frames": n,
        "animated": n > 1,
        "labels": pick.get("labels") or {},
        "leaf": next((k for k, v in info.items() if v is pick), leaf),
    }


def pack_bitmaps(pack_name: str) -> dict:
    """leaf -> JPEG bytes, si el símbolo apunta a un DefineBitsJPEG."""
    pack = (pack_name or "").replace("\\", "/").strip("/")
    if pack in _thumb_cache:
        return _thumb_cache[pack]
    data = load_pack(pack)
    out = {}
    if not data:
        _thumb_cache[pack] = out
        return out
    try:
        body = _swf_payload(data)
        bits = {}
        names = []
        for code, payload in _iter_swf_tags(body):
            if code in (6, 21) and len(payload) >= 4:
                cid = struct.unpack_from("<H", payload, 0)[0]
                jpeg = _jpeg_blob(payload, False)
                if jpeg:
                    bits[cid] = jpeg
            elif code in (35, 90) and len(payload) >= 8:
                cid = struct.unpack_from("<H", payload, 0)[0]
                jpeg = _jpeg_blob(payload, True)
                if jpeg:
                    bits[cid] = jpeg
            elif code == 76:
                names.extend(_parse_symbol_class(payload))
        for cid, raw_name in names:
            jpeg = bits.get(cid)
            if not jpeg:
                continue
            leaf = raw_name.split(".")[-1].split(":")[-1]
            if leaf.endswith("_on"):
                leaf = leaf[:-3]
            if leaf and leaf not in out:
                out[leaf] = jpeg
    except Exception:
        pass
    _thumb_cache[pack] = out
    return out


def item_thumb_jpeg(pack_name: str, leaf: str) -> bytes | None:
    leaf = (leaf or "").split(".")[-1]
    if leaf.endswith("_on"):
        leaf = leaf[:-3]
    bits = pack_bitmaps(pack_name)
    return bits.get(leaf)


def _encode_swf_tag(code: int, payload: bytes) -> bytes:
    ln = len(payload)
    if ln < 0x3F:
        return struct.pack("<H", (code << 6) | ln) + payload
    return struct.pack("<H", (code << 6) | 0x3F) + struct.pack("<I", ln) + payload


def _encode_rect(xmin: int, xmax: int, ymin: int, ymax: int) -> bytes:
    vals = [int(xmin), int(xmax), int(ymin), int(ymax)]
    if vals[0] > vals[1]:
        vals[0], vals[1] = vals[1], vals[0]
    if vals[2] > vals[3]:
        vals[2], vals[3] = vals[3], vals[2]

    def bits_needed(v: int) -> int:
        if v == 0:
            return 1
        return abs(v).bit_length() + 1

    nbits = max(bits_needed(v) for v in vals)
    nbits = max(5, min(31, nbits))
    total_bits = 5 + nbits * 4
    nbytes = (total_bits + 7) // 8
    out = bytearray(nbytes)

    def write_bits(start: int, n: int, val: int) -> None:
        if val < 0:
            val = (1 << n) + val
        for i in range(n):
            if (val >> (n - 1 - i)) & 1:
                pos = start + i
                out[pos // 8] |= 1 << (7 - (pos % 8))

    write_bits(0, 5, nbits)
    off = 5
    for v in vals:
        write_bits(off, nbits, v)
        off += nbits
    return bytes(out)


def _read_bits(buf: bytes, start: int, n: int) -> int:
    v = 0
    for i in range(n):
        pos = start + i
        if pos // 8 >= len(buf):
            break
        v = (v << 1) | ((buf[pos // 8] >> (7 - (pos % 8))) & 1)
    return v


def _read_sbits(buf: bytes, start: int, n: int) -> int:
    if n <= 0:
        return 0
    v = _read_bits(buf, start, n)
    if v & (1 << (n - 1)):
        v -= 1 << n
    return v


def _parse_matrix_tx_ty(buf: bytes, off: int) -> tuple[int, int, int]:
    """→ (tx, ty, bytes_consumed) desde off."""
    data = buf[off:]
    if not data:
        return 0, 0, 0
    bit = 0
    has_scale = _read_bits(data, bit, 1)
    bit += 1
    if has_scale:
        n = _read_bits(data, bit, 5)
        bit += 5 + n * 2
    has_rot = _read_bits(data, bit, 1)
    bit += 1
    if has_rot:
        n = _read_bits(data, bit, 5)
        bit += 5 + n * 2
    n = _read_bits(data, bit, 5)
    bit += 5
    tx = _read_sbits(data, bit, n)
    bit += n
    ty = _read_sbits(data, bit, n)
    bit += n
    return tx, ty, (bit + 7) // 8


def _place_tx_ty(code: int, pl: bytes) -> tuple[int | None, int | None, int | None]:
    """PlaceObject2/3 → (depth, tx, ty) si hay matrix."""
    if code not in (26, 70) or not pl:
        return None, None, None
    flags = pl[0]
    p = 2 if code == 70 else 1
    if p + 2 > len(pl):
        return None, None, None
    depth = struct.unpack_from("<H", pl, p)[0]
    p += 2
    if flags & 2:
        p += 2
    if not (flags & 4) or p >= len(pl):
        return depth, None, None
    tx, ty, _ = _parse_matrix_tx_ty(pl, p)
    return depth, tx, ty


def _sprite_content_rect(payload: bytes) -> tuple[int, int, int, int]:
    """AABB aprox. de los PlaceObject del sprite (incluye Y negativa)."""
    depths: dict[int, tuple[int, int]] = {}
    for code, pl in _iter_raw_tags(payload, 4):
        if code == 0:
            break
        if code == 28 and len(pl) >= 2:
            depths.pop(struct.unpack_from("<H", pl, 0)[0], None)
            continue
        if code == 5 and len(pl) >= 4:
            depths.pop(struct.unpack_from("<H", pl, 2)[0], None)
            continue
        depth, tx, ty = _place_tx_ty(code, pl)
        if depth is None:
            continue
        prev = depths.get(depth, (0, 0))
        depths[depth] = (
            prev[0] if tx is None else tx,
            prev[1] if ty is None else ty,
        )
    if not depths:
        return -2000, 2000, -2000, 2000
    txs = [p[0] for p in depths.values()]
    tys = [p[1] for p in depths.values()]
    pad = 1600
    return min(txs) - pad, max(txs) + pad, min(tys) - pad, max(tys) + pad


def _freeze_define_sprite(payload: bytes, frame: int) -> bytes:
    """Deja el DefineSprite en un solo ShowFrame, con los PlaceObject acumulados hasta `frame`."""
    if len(payload) < 4:
        return payload
    sid = struct.unpack_from("<H", payload, 0)[0]
    want = max(1, int(frame or 1))
    out = bytearray()
    shown = 0
    for code, pl in _iter_raw_tags(payload, 4):
        if code == 0:
            break
        if code == 1:
            shown += 1
            if shown >= want:
                break
            continue
        out += _encode_swf_tag(code, pl)
    out += _encode_swf_tag(1, b"")
    out += _encode_swf_tag(0, b"")
    return struct.pack("<HH", sid, 1) + bytes(out)


_frozen_cache: dict[tuple, bytes] = {}


def frozen_item_swf(pack_name: str, leaf: str, frame: int = 1) -> bytes | None:
    """SWF de 1 frame: el sprite del ítem congelado en `frame`, puesto en el stage."""
    pack = (pack_name or "").replace("\\", "/").strip("/")
    leaf = (leaf or "").split(".")[-1]
    try:
        frame = max(1, int(frame or 1))
    except (TypeError, ValueError):
        frame = 1
    key = (pack, leaf, frame)
    if key in _frozen_cache:
        return _frozen_cache[key]
    info = item_sprite_frames(pack, leaf)
    cid = info.get("cid")
    nframes = int(info.get("frames") or 1)
    if not cid:
        return None
    frame = min(frame, max(1, nframes))
    data = load_pack(pack)
    if not data:
        return None
    body = _swf_payload(data)
    if len(body) < 16:
        return None
    nbits = body[0] >> 3
    rect_len = (5 + nbits * 4 + 7) // 8
    if rect_len < 1 or rect_len + 4 > len(body):
        return None
    fps = struct.unpack_from("<H", body, rect_len)[0]
    tag_start = rect_len + 4
    tags: list[tuple[int, bytes]] = []
    frozen_pl = None
    for code, pl in _iter_raw_tags(body, tag_start):
        if code == 0:
            break
        # sin timeline original, ABC, fondo opaco ni metadata de escena
        if code in (1, 9, 72, 76, 82, 86):
            continue
        if code == 69 and len(pl) >= 4:
            flags = struct.unpack_from("<I", pl, 0)[0] & ~0x08
            pl = struct.pack("<I", flags)
        if code == 39 and len(pl) >= 2 and struct.unpack_from("<H", pl, 0)[0] == cid:
            pl = _freeze_define_sprite(pl, frame)
            frozen_pl = pl
        tags.append((code, pl))
    if not frozen_pl:
        return None
    xmin, xmax, ymin, ymax = _sprite_content_rect(frozen_pl)
    rect = _encode_rect(xmin, xmax, ymin, ymax)
    export = struct.pack("<HH", 1, int(cid)) + leaf.encode("utf-8", "replace") + b"\x00"
    tags.append((56, export))
    po2 = struct.pack("<BHH", 0x06, 1, int(cid)) + b"\x00"
    tags.append((26, po2))
    tags.append((1, b""))
    out = bytearray()
    out += b"FWS"
    out += bytes([10])
    out += b"\x00\x00\x00\x00"
    out += rect
    out += struct.pack("<HH", fps, 1)
    for code, pl in tags:
        out += _encode_swf_tag(code, pl)
    out += _encode_swf_tag(0, b"")
    struct.pack_into("<I", out, 4, len(out))
    blob = bytes(out)
    _frozen_cache[key] = blob
    return blob
