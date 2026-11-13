"""
app.py - Main entry point and REST API for naw-tool.
Serves the web UI and provides full automation for Mundo Gaturro modding and tricking.
"""

import os
import sys
from pathlib import Path
from flask import Flask, jsonify, request, render_template, send_from_directory, Response
from core import item_catalog

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from core.proxy_engine import engine as proxy_engine
from core import game_launcher
from core import payload_builder
from core import swf_analyzer
from core import catalog_db
from core import trucador
from core import asset_library
from core import mmo_dump
from core import theme_tags
from core import thumb_store
from core import image_search

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static")
)
app.config["JSON_SORT_KEYS"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = True
# Import de thumbs_index.zip (~100–200 MB)
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024
app.jinja_env.auto_reload = True

FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


@app.route("/")
def index():
    # Prefer the Electron/React build when present; fall back to legacy HTML UI.
    dist_index = FRONTEND_DIST / "index.html"
    if dist_index.exists():
        return send_from_directory(str(FRONTEND_DIST), "index.html")
    return render_template("index.html")


@app.route("/proxy.pac")
@app.route("/mg-proxy.pac")
def serve_proxy_pac():
    from core.proxy_engine import _build_pac
    body = _build_pac("127.0.0.1", proxy_engine.port)
    resp = Response(body, mimetype="application/x-ns-proxy-autoconfig")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "root": str(BASE_DIR)})


@app.route("/api/status", methods=["GET"])
def api_status():
    proxy_st = proxy_engine.get_status()
    game_running = game_launcher.is_game_running()
    game_exe = game_launcher.get_game_executable_path()
    tricks_counts = trucador.get_tricks_counts()
    
    return jsonify({
        "ok": True,
        "proxy": proxy_st,
        "game": {
            "running": game_running,
            "executable_found": bool(game_exe),
            "executable_path": str(game_exe) if game_exe else ""
        },
        "payload": proxy_engine.get_payload(),
        "payload_b64": payload_builder.encode_payload_b64(proxy_engine.get_payload()),
        "recent_logs": proxy_engine.get_logs(30),
        "body_parts": swf_analyzer.PARTES_CUERPO,
        "tricks_count": tricks_counts["total"],
        "tricks_counts": tricks_counts
    })


@app.route("/api/proxy/start", methods=["POST"])
def api_proxy_start():
    ok = proxy_engine.start()
    err = None
    if not ok:
        err = proxy_engine.last_error or "No se pudo iniciar el proxy. Revisá Logs."
    return jsonify({"ok": ok, "error": err, "status": proxy_engine.get_status()})


@app.route("/api/proxy/stop", methods=["POST"])
def api_proxy_stop():
    ok = proxy_engine.stop()
    return jsonify({"ok": ok, "status": proxy_engine.get_status(),
                    "error": None if ok else "El proxy se detuvo, pero no se pudo restaurar la configuración de red. Revisá Logs."})


@app.route("/api/game/launch", methods=["POST"])
def api_game_launch():
    req = request.get_json(silent=True) or {}
    clean_cache = req.get("clean_cache", True)

    if clean_cache:
        game_launcher.clean_game_cache()

    st = proxy_engine.get_status()
    pac_url = st.get("pac_url") if st.get("running") and st.get("system_proxy_enabled") else None
    ok = game_launcher.launch_game(proxy_pac_url=pac_url)
    if ok and pac_url:
        proxy_engine.log(f"Juego lanzado con --proxy-pac-url={pac_url}", "DIAG")
    elif ok:
        proxy_engine.log("Juego lanzado SIN PAC explícito (proxy apagado o PAC no aplicado)", "WARN")
    return jsonify({"ok": ok, "message": "Juego iniciado" if ok else "No se encontro el ejecutable de Mundo Gaturro"})


@app.route("/api/game/kill", methods=["POST"])
def api_game_kill():
    ok = game_launcher.kill_game()
    return jsonify({"ok": ok})


@app.route("/api/game/clean-cache", methods=["POST"])
def api_game_clean_cache():
    ok = game_launcher.clean_game_cache()
    return jsonify({"ok": ok})


def _payload_items_from_tricks(tricks=None):
    """Build Lola inventory.add rows from clothes tricks + class changes."""
    rows = tricks if tricks is not None else trucador.list_lola_items()
    parsed = []
    for t in rows or []:
        item = (t.get("item") or "").strip()
        pack = (t.get("pack") or "").strip()
        obj = (t.get("object") or "").strip()
        if not item and pack and obj:
            item = f"{pack}.{obj}"
        if not item or "." not in item:
            continue
        swf, leaf = item.split(".", 1)
        try:
            qty = max(1, min(99, int(t.get("qty") or 1)))
        except (TypeError, ValueError):
            qty = 1
        entry = {
            "swf": swf.replace(".swf", "").strip(),
            "item": leaf.strip(),
            "name": item,
            "qty": qty,
        }
        if t.get("kind") != "effect" and (t.get("options") or t.get("custom_attrs")):
            entry["options"] = t.get("options") or t.get("custom_attrs")
        parsed.append(entry)
    return parsed


def sync_lola_with_saved_tricks(reason: str = "sync"):
    """Replace stale Lola payload with exactly the saved tricks (or empty)."""
    parsed = _payload_items_from_tricks()
    script = payload_builder.build_npc_payload(parsed)
    proxy_engine.set_payload(script)
    names = ", ".join(f'{p["qty"]}x {p["name"]}' for p in parsed) if parsed else "(ninguno)"
    proxy_engine.log(f"Lola sync ({reason}): {names}", "TRUCO")
    return parsed, script


@app.route("/api/quick-start", methods=["POST"])
def api_quick_start():
    """
    1-Click Master Automation:
    1. Keeps the current Lola action unless explicit items/raw_payload are supplied
    2. Ensures proxy is running and configured in Windows
    3. Kills previous game instance
    4. Purges Electron cache (preserving cookies)
    5. Launches Mundo Gaturro
    """
    req = request.get_json(silent=True) or {}
    items = req.get("items")
    raw_payload = req.get("raw_payload")

    if items and isinstance(items, list) and len(items) > 0:
        script = payload_builder.build_npc_payload(items)
        proxy_engine.set_payload(script)
    elif raw_payload:
        proxy_engine.set_payload(raw_payload)
    else:
        # Opening/restarting the game must never choose a different Lola action.
        # Save/queue endpoints already update Lola explicitly.
        current = proxy_engine.get_payload().strip()
        if not current:
            proxy_engine.set_payload(payload_builder.build_npc_payload([]))
        proxy_engine.log("Quick-start mantiene exactamente la acción activa de Lola", "BEHAVIOR")

    # Tirar overrides huérfanos (sin truco) que ensucian el PAC.
    removed = trucador.cleanup_orphan_overrides()
    if removed:
        proxy_engine.refresh_pac()
        proxy_engine.log(
            f"Overrides viejos borrados (ya no tenían truco): {', '.join(removed)}",
            "INFO",
        )

    # 1. Start proxy (como GitHub)
    if not proxy_engine.get_status().get("running"):
        proxy_started = proxy_engine.start()
        if not proxy_started:
            return jsonify({"ok": False, "error": proxy_engine.last_error or "No se pudo iniciar el proxy. Revisá Logs."})

    st = proxy_engine.get_status()
    if not st.get("system_proxy_enabled"):
        return jsonify({
            "ok": False,
            "error": "Proxy up pero el PAC de Windows no quedó aplicado. Mirá Logs.",
            "status": st,
        })

    # 2. Restart game: matar → caché completa (como GitHub) → launch con PAC
    game_launcher.wait_game_dead(6.0)
    game_launcher.clean_game_cache(light=False)
    pac_url = st.get("pac_url") or None
    launched = game_launcher.launch_game(proxy_pac_url=pac_url)

    st2 = proxy_engine.get_status()
    proxy_engine.log(
        f"Quick-Start OK · PAC={pac_url} · juego={'sí' if launched else 'NO'} · "
        f"items={st2.get('payload_summary', {}).get('item_count', 0)}. "
        f"Al hablar con Lola tiene que aparecer [INTERCEPTADO] en Logs.",
        "MASTER",
    )

    return jsonify({
        "ok": True,
        "proxy_running": True,
        "game_launched": launched,
        "pac_url": pac_url,
        "status": st2,
        "message": (
            "Listo: proxy + PAC + juego. Lola conserva la acción que activaste. "
            "Hablá con ella y mirá Logs: [MG-HIT] / [INTERCEPTADO]."
        ),
    })


@app.route("/api/swfs", methods=["GET"])
def api_swfs():
    q = request.args.get("q", "").lower().strip()
    category = request.args.get("category", "").lower().strip()
    theme = request.args.get("theme", "").lower().strip()
    all_swfs = swf_analyzer.list_available_swfs()

    results = []
    for s in all_swfs:
        name = s["name"]
        cat = catalog_db.categorize_swf(name)
        s["category"] = cat
        s["themes"] = theme_tags.detect_themes(name)

        if category and category != "todos" and cat != category:
            continue
        if theme and theme != "todos" and not theme_tags.pack_matches_theme(name, theme):
            continue
        if q and q not in name.lower():
            continue

        results.append(s)

    return jsonify({
        "ok": True,
        "total": len(results),
        "theme": theme or None,
        "swfs": results
    })


@app.route("/api/themes", methods=["GET"])
def api_themes():
    """Lista temas con cuántos packs coinciden (por nombre)."""
    all_swfs = swf_analyzer.list_available_swfs()
    names = [s.get("name") or "" for s in all_swfs]
    return jsonify({
        "ok": True,
        "themes": theme_tags.list_themes(names),
        "total_packs": len(names),
    })


@app.route("/api/assets/thumb", methods=["GET"])
def api_assets_thumb():
    pack = (request.args.get("pack") or "").strip()
    name = (request.args.get("name") or request.args.get("item") or "").strip()
    if not pack or not name:
        return Response(status=204)
    # Prefer Flash-persisted PNG corpus when available.
    cached = thumb_store.read_png(pack, name)
    if cached:
        return Response(cached, mimetype="image/png")
    jpeg = item_catalog.item_thumb_jpeg(pack, name)
    if not jpeg:
        return Response(status=204)
    return Response(jpeg, mimetype="image/jpeg")


@app.route("/api/thumbs/file", methods=["GET"])
def api_thumbs_file():
    pack = (request.args.get("pack") or "").strip()
    name = (request.args.get("name") or request.args.get("item") or "").strip()
    if not pack or not name:
        return Response(status=404)
    png = thumb_store.read_png(pack, name)
    if not png:
        return Response(status=404)
    resp = Response(png, mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/thumbs/stats", methods=["GET"])
def api_thumbs_stats():
    return jsonify(image_search.index_stats())


@app.route("/api/thumbs/coverage", methods=["GET"])
def api_thumbs_coverage():
    all_swfs = swf_analyzer.list_available_swfs()
    names = [s.get("name") or "" for s in all_swfs]
    include_stale = str(request.args.get("include_stale") or "").strip().lower() in (
        "1", "true", "yes", "hd",
    )
    return jsonify(thumb_store.coverage(names, include_stale=include_stale))


@app.route("/api/thumbs/export", methods=["POST"])
def api_thumbs_export():
    """Arranca export async de data/thumbs_index.zip (poll /api/thumbs/export/status)."""
    try:
        feat_ver = int(getattr(image_search, "FEAT_VER", 5) or 5)
    except (TypeError, ValueError):
        feat_ver = 5
    res = thumb_store.start_export_async(feat_ver=feat_ver)
    if not res.get("ok"):
        return jsonify(res), 409
    return jsonify({**res, "job": thumb_store.export_job_snapshot()})


@app.route("/api/thumbs/export/status", methods=["GET"])
def api_thumbs_export_status():
    return jsonify({"ok": True, "job": thumb_store.export_job_snapshot()})


@app.route("/api/thumbs/export/file", methods=["GET"])
def api_thumbs_export_file():
    path = thumb_store.export_zip_path()
    if not path.exists():
        return jsonify({"ok": False, "error": "Todavía no hay zip. Tocá Exportar índice."}), 404
    return send_from_directory(str(path.parent), path.name, as_attachment=True)


@app.route("/api/thumbs/import", methods=["POST"])
def api_thumbs_import():
    """Sube un thumbs_index.zip y lo fusiona sobre data/thumb_cache."""
    f = request.files.get("file") or request.files.get("zip")
    if not f or not getattr(f, "filename", None):
        return jsonify({"ok": False, "error": "Falta el archivo .zip"}), 400
    name = str(f.filename or "").lower()
    if not name.endswith(".zip"):
        return jsonify({"ok": False, "error": "Tiene que ser un .zip"}), 400

    import tempfile
    from pathlib import Path as _Path

    tmp = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix="naw_thumbs_", suffix=".zip")
        tmp = _Path(tmp_name)
        with open(fd, "wb") as out:
            while True:
                chunk = f.stream.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        res = thumb_store.import_index_zip(tmp)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

    if not res.get("ok"):
        return jsonify(res), 400

    # Recargar índice CLIP en background con los thumbs nuevos
    try:
        image_search.invalidate(delete_files=False)
        image_search.warm_index_background()
    except Exception:
        pass
    return jsonify(res)


@app.route("/api/thumbs/ingest", methods=["POST"])
def api_thumbs_ingest():
    data = request.get_json(silent=True) or {}
    pack = (data.get("pack") or "").strip()
    name = (data.get("name") or data.get("item") or "").strip()
    png = data.get("png") or data.get("thumb") or data.get("image") or ""
    if not pack or not name or not png:
        return jsonify({"ok": False, "error": "pack, name y png requeridos"}), 400
    res = thumb_store.save_data_url(pack, name, png, source="flash")
    if not res.get("ok"):
        return jsonify(res), 400
    try:
        raw = thumb_store.read_png(pack, name)
        if raw:
            image_search.add_or_update(pack, name, raw)
    except Exception:
        pass
    return jsonify(res)


@app.route("/api/thumbs/ingest-batch", methods=["POST"])
def api_thumbs_ingest_batch():
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        return jsonify({"ok": False, "error": "items vacío"}), 400
    batch = []
    for row in items[:80]:
        if not isinstance(row, dict):
            continue
        pack = (row.get("pack") or "").strip()
        name = (row.get("name") or row.get("item") or "").strip()
        png = row.get("png") or row.get("thumb") or row.get("image") or ""
        batch.append((pack, name, png))
    saved = thumb_store.save_data_urls(batch)
    for pack, name in saved:
        try:
            raw = thumb_store.read_png(pack, name)
            if raw:
                image_search.add_or_update(pack, name, raw)
        except Exception:
            pass
    return jsonify({"ok": True, "saved": len(saved), "errors": len(items[:80]) - len(saved), **thumb_store.stats()})


@app.route("/api/thumbs/reindex", methods=["POST"])
def api_thumbs_reindex():
    """Rebuild en background para no colgar la UI."""
    import threading

    def _run():
        try:
            image_search.rebuild_index(force=True)
        except Exception as exc:
            print(f"[thumbs/reindex] {exc}")

    if image_search.get_build_progress().get("running"):
        return jsonify({"ok": True, "started": False, "build": image_search.get_build_progress()})
    threading.Thread(target=_run, name="clip-reindex", daemon=True).start()
    return jsonify({"ok": True, "started": True, "message": "Reindexando en background…"})


@app.route("/api/image/remove-background", methods=["POST"])
def api_remove_background():
    """
    Elimina automáticamente el fondo de una imagen (captura / crop).
    Acepta JSON { "data_url": "...", "mode": "smart" | "ai" } o multipart file.
    Devuelve { "ok": True, "data_url": "data:image/png;base64,..." }.
    """
    from PIL import Image
    import base64
    import io

    png_bytes = None
    mode = "smart"

    if request.files.get("file"):
        png_bytes = request.files["file"].read()
        mode = (request.form.get("mode") or "smart").strip().lower()
    else:
        data = request.get_json(silent=True) or {}
        mode = (data.get("mode") or "smart").strip().lower()
        raw = data.get("data_url") or data.get("png") or data.get("image") or ""
        if isinstance(raw, str) and raw:
            s = raw.strip()
            if "," in s and s.lower().startswith("data:"):
                s = s.split(",", 1)[1]
            try:
                png_bytes = base64.b64decode(s, validate=False)
            except Exception:
                png_bytes = None

    if not png_bytes:
        return jsonify({"ok": False, "error": "Falta la imagen"}), 400

    try:
        from core import bg_remove

        pil_img = Image.open(io.BytesIO(png_bytes))
        result = bg_remove.remove_background(pil_img, mode=mode)
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return jsonify({
            "ok": True,
            "data_url": f"data:image/png;base64,{b64}",
            "mode": mode,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/search/by-image", methods=["POST"])
def api_search_by_image():
    """
    Busca objetos parecidos a una imagen.
    Acepta multipart `file`, o JSON {png/data_url, theme, top_k, exclude_pack, exclude_name}.
    """
    theme = ""
    top_k = 40
    exclude = None
    png_bytes = None

    if request.files.get("file"):
        f = request.files["file"]
        png_bytes = f.read()
        theme = (request.form.get("theme") or "").strip().lower()
        try:
            top_k = int(request.form.get("top_k") or 40)
        except (TypeError, ValueError):
            top_k = 40
        ep = (request.form.get("exclude_pack") or "").strip()
        en = (request.form.get("exclude_name") or "").strip()
        if ep and en:
            exclude = (ep, en)
    else:
        data = request.get_json(silent=True) or {}
        theme = (data.get("theme") or "").strip().lower()
        try:
            top_k = int(data.get("top_k") or 40)
        except (TypeError, ValueError):
            top_k = 40
        ep = (data.get("exclude_pack") or "").strip()
        en = (data.get("exclude_name") or "").strip()
        if ep and en:
            exclude = (ep, en)
        raw = data.get("png") or data.get("thumb") or data.get("image") or data.get("data_url") or ""
        if isinstance(raw, str) and raw:
            import base64
            s = raw.strip()
            if "," in s and s.lower().startswith("data:"):
                s = s.split(",", 1)[1]
            try:
                png_bytes = base64.b64decode(s, validate=False)
            except Exception:
                png_bytes = None

    if not png_bytes:
        return jsonify({"ok": False, "error": "Falta la imagen"}), 400

    try:
        hits = image_search.search_bytes(
            png_bytes,
            top_k=top_k,
            theme=theme,
            exclude=exclude,
        )
    except RuntimeError as e:
        # Índice todavía cargando — no colgar la UI
        return jsonify({
            "ok": False,
            "loading": True,
            "error": str(e),
            "build": image_search.get_build_progress(),
        }), 503
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    indexed = 0
    try:
        indexed = int(image_search.index_stats().get("indexed") or 0)
    except Exception:
        pass
    return jsonify({
        "ok": True,
        "total": len(hits),
        "indexed": indexed,
        "hits": hits,
    })


@app.route("/api/search/by-keyword", methods=["GET"])
def api_search_by_keyword():
    """Busca objetos (no archivos SWF) por palabra / tema. Ej: ?q=halloween"""
    from core import keyword_search

    q = (request.args.get("q") or request.args.get("query") or "").strip()
    theme = (request.args.get("theme") or "").strip().lower()
    try:
        limit = int(request.args.get("limit") or 80)
    except (TypeError, ValueError):
        limit = 80
    if len(q) < 2:
        return jsonify({"ok": True, "total": 0, "hits": [], "q": q})
    try:
        hits = keyword_search.search_by_keyword(q, theme=theme, limit=limit)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({
        "ok": True,
        "total": len(hits),
        "q": q,
        "theme": theme or None,
        "hits": hits,
    })


@app.route("/api/assets/frame.swf", methods=["GET"])
def api_assets_frame_swf():
    pack = (request.args.get("pack") or "").strip()
    name = (request.args.get("name") or request.args.get("item") or "").strip()
    if not pack or not name:
        return Response(status=404)
    try:
        frame = int(request.args.get("frame") or 1)
    except (TypeError, ValueError):
        frame = 1
    blob = item_catalog.frozen_item_swf(pack, name, frame)
    if not blob:
        return Response(status=404)
    resp = Response(blob, mimetype="application/x-shockwave-flash")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/ruffle/<path:filename>")
def serve_ruffle_files(filename):
    ruffle_dir = BASE_DIR / "static" / "ruffle"
    return send_from_directory(str(ruffle_dir), filename)


@app.route("/<filename>.wasm")
def serve_wasm_root(filename):
    ruffle_dir = BASE_DIR / "static" / "ruffle"
    return send_from_directory(str(ruffle_dir), f"{filename}.wasm")


@app.route("/core.ruffle.<hash_val>.js")
def serve_ruffle_hash_js(hash_val):
    ruffle_dir = BASE_DIR / "static" / "ruffle"
    return send_from_directory(str(ruffle_dir), f"core.ruffle.{hash_val}.js")


@app.route("/preview.swf")
def serve_preview_swf():
    ruffle_dir = BASE_DIR / "static" / "ruffle"
    resp = send_from_directory(str(ruffle_dir), "preview.swf", mimetype="application/x-shockwave-flash")
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.route("/anim_preview.swf")
def serve_anim_preview_swf():
    ruffle_dir = BASE_DIR / "static" / "ruffle"
    resp = send_from_directory(str(ruffle_dir), "anim_preview.swf", mimetype="application/x-shockwave-flash")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/assets/<path:filename>")
def serve_assets_swf(filename):
    # Vite UI bundles (index-*.js / *.css) live in frontend/dist/assets.
    ui_asset = FRONTEND_DIST / "assets" / filename
    if ui_asset.exists() and ui_asset.is_file():
        return send_from_directory(str(ui_asset.parent), ui_asset.name)

    clean = filename.replace(".swf", "").strip()
    path = trucador.ensure_swf_cached(clean)
    if path and path.exists():
        resp = send_from_directory(str(path.parent), path.name, mimetype="application/x-shockwave-flash")
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
    return Response(status=404)


@app.route("/api/swf/inspect", methods=["GET"])
def api_swf_inspect():
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Parametro 'name' requerido"})
    res = swf_analyzer.inspect_swf(name)
    return jsonify(res)


@app.route("/api/payload/set", methods=["POST"])
def api_payload_set():
    req = request.get_json(silent=True) or {}
    items = req.get("items")
    raw = req.get("raw")
    
    if items and isinstance(items, list):
        script = payload_builder.build_npc_payload(items)
    elif raw:
        script = raw
    else:
        return jsonify({"ok": False, "error": "Se requieren 'items' o 'raw'"})

    proxy_engine.set_payload(script)
    return jsonify({
        "ok": True,
        "payload": script,
        "payload_b64": payload_builder.encode_payload_b64(script)
    })


@app.route("/api/payload/get", methods=["GET"])
def api_payload_get():
    p = proxy_engine.get_payload()
    return jsonify({
        "ok": True,
        "payload": p,
        "payload_b64": payload_builder.encode_payload_b64(p),
        "active": payload_builder.describe_active_payload(p)
    })


@app.route("/api/trucar/list", methods=["GET"])
def api_trucar_list():
    tricks = trucador.list_tricks()
    class_changes = trucador.list_class_changes()
    effects = trucador.list_effect_tricks()
    return jsonify({
        "ok": True,
        "count": len(tricks),
        "tricks": tricks,
        "class_changes": class_changes,
        "class_count": len(class_changes),
        "effects": effects,
        "effects_count": len(effects),
    })


@app.route("/api/trucar/clases", methods=["GET"])
def api_trucar_clases():
    return jsonify({"ok": True, **trucador.list_mambo_targets()})


@app.route("/api/trucar/clase", methods=["POST"])
def api_trucar_clase():
    """Change MamboAsset superclass for one or many classes in a pack."""
    req = request.get_json(silent=True) or {}
    pack = (req.get("pack") or "").strip()
    mambo_class = (req.get("mambo_class") or req.get("class") or "").strip()
    classes = req.get("classes") or []
    if isinstance(classes, str):
        classes = [classes]
    queue_lola = bool(req.get("queue_lola", True))
    try:
        qty = max(1, min(99, int(req.get("qty") or 1)))
    except (TypeError, ValueError):
        qty = 1

    res = trucador.cambiar_clase(pack, list(classes), mambo_class, qty=qty)
    if not res.get("ok"):
        proxy_engine.log(f"[CLASE-ERROR] {res.get('error')}", "ERROR")
        return jsonify(res)

    proxy_engine.refresh_pac()
    changed = res.get("changed") or []
    applied = res.get("mambo_class") or mambo_class
    remap = res.get("remapped_from")
    remap_note = f" (pediste {remap})" if remap else ""
    proxy_engine.log(
        f"[CLASE] {pack}: {', '.join(changed)} -> {applied}{remap_note} · x{qty}",
        "TRUCO",
    )

    if queue_lola and res.get("items"):
        parsed = []
        for item in res["items"]:
            if not item or "." not in item:
                continue
            swf, leaf = item.split(".", 1)
            parsed.append({"swf": swf, "item": leaf, "name": item, "qty": qty})
        if parsed:
            script = payload_builder.build_npc_payload(parsed)
            proxy_engine.set_payload(script)
            res["lola_synced"] = True
            res["lola_count"] = len(parsed)
            names = ", ".join(f"{p['qty']}x {p['name']}" for p in parsed)
            proxy_engine.log(f"Lola sync (class-change): {names}", "TRUCO")

    return jsonify(res)


@app.route("/api/trucar/<pack>/<obj_name>", methods=["DELETE"])
def api_trucar_delete(pack, obj_name):
    res = trucador.delete_trick(pack, obj_name)
    if res.get("ok"):
        proxy_engine.refresh_pac()
        proxy_engine.log(f"Truco eliminado: {pack}.{obj_name}", "TRUCO")
        sync_lola_with_saved_tricks("delete-trick")
    return jsonify(res)


@app.route("/api/trucar/queue", methods=["POST"])
def api_trucar_queue():
    """Put one or many tricked items into Lola's give list."""
    req = request.get_json(silent=True) or {}
    items = req.get("items")
    if not items:
        item = (req.get("item") or "").strip()
        if item:
            items = [item]
    if not items or not isinstance(items, list):
        return jsonify({"ok": False, "error": "Pasá al menos un objeto"})

    parsed = []
    for raw in items:
        name = str(raw or "").strip()
        if not name or "." not in name:
            continue
        swf, leaf = name.split(".", 1)
        swf = swf.replace(".swf", "").strip()
        leaf = leaf.replace(".as", "").strip()
        if leaf.endswith("_on"):
            leaf = leaf[:-3]
        if swf and leaf:
            parsed.append({"swf": swf, "item": leaf, "name": f"{swf}.{leaf}", "qty": 1})

    if not parsed:
        return jsonify({"ok": False, "error": "Ningún objeto válido"})

    new_script = payload_builder.build_npc_payload(parsed)
    proxy_engine.set_payload(new_script)
    names = ", ".join(p["name"] for p in parsed)
    proxy_engine.log(f"Lola listo con trucos: {names}", "TRUCO")
    return jsonify({
        "ok": True,
        "count": len(parsed),
        "message": f"Listo para Lola: {len(parsed)} objeto{'s' if len(parsed) != 1 else ''}.",
        "payload": new_script,
    })


@app.route("/api/trucar/ropa", methods=["POST"])
def api_trucar_ropa():
    req = request.get_json(silent=True) or {}
    base_swf = req.get("base_swf", "").strip()
    base_obj = req.get("base_object", "").strip()
    body_part = req.get("body_part", "").strip()
    target_obj = req.get("target_object", "").strip()
    parts = req.get("parts")
    parts_info = req.get("parts_info")
    auto_queue = req.get("auto_queue", True)
    try:
        qty = max(1, min(99, int(req.get("qty") or 1)))
    except (TypeError, ValueError):
        qty = 1

    if not base_swf or not base_obj:
        return jsonify({"ok": False, "error": "Faltan el SWF base o el objeto base"})

    if not parts and not (body_part and target_obj):
        return jsonify({"ok": False, "error": "Debes especificar al menos un objeto a poner"})

    res = trucador.trucar_ropa(
        base_swf,
        base_obj,
        body_part=body_part,
        target_object=target_obj,
        parts=parts,
        parts_info=parts_info,
        qty=qty,
    )
    if not res.get("ok"):
        return jsonify(res)

    proxy_engine.refresh_pac()
    proxy_engine.log(f"Truco aplicado: {base_swf}.{base_obj} -> {res.get('parts')}", "TRUCO")

    # Keep Lola aligned with ALL saved tricks (not yesterday's leftovers / only last one).
    if auto_queue:
        parsed, _script = sync_lola_with_saved_tricks("save-trick")
        res["lola_synced"] = True
        res["lola_count"] = len(parsed)
    else:
        # Even without auto_queue, refresh Lola to the full saved set so old payload dies.
        parsed, _script = sync_lola_with_saved_tricks("save-trick-silent")
        res["lola_synced"] = True
        res["lola_count"] = len(parsed)

    return jsonify(res)




@app.route("/api/actions", methods=["GET"])
def api_actions():
    actions_file = BASE_DIR / "data" / "actions.json"
    actions = []
    if actions_file.exists():
        try:
            import json
            actions = json.loads(actions_file.read_text(encoding="utf-8"))
        except Exception:
            actions = []
    return jsonify({
        "ok": True,
        "count": len(actions),
        "actions": actions
    })


@app.route("/api/effects", methods=["GET"])
def api_effects_list():
    effects = trucador.list_effect_tricks()
    return jsonify({
        "ok": True,
        "count": len(effects),
        "effects": effects
    })


@app.route("/api/effects/save", methods=["POST"])
def api_effects_save():
    req = request.get_json(silent=True) or {}
    base_item = (req.get("base_item") or "food.banana").strip()
    action = (req.get("action") or "kick").strip()
    sub_item = (req.get("sub_item") or "").strip()
    destination = (req.get("destination") or "default").strip()
    try:
        uses = int(req.get("uses") or 9999)
    except (ValueError, TypeError):
        uses = 9999
    try:
        qty = max(1, min(99, int(req.get("qty") or 1)))
    except (ValueError, TypeError):
        qty = 1
    auto_on = bool(req.get("auto_on", True))
    queue_lola = bool(req.get("queue_lola", True))

    res_save = trucador.save_effect_trick(
        base_item=base_item,
        action=action,
        sub_item=sub_item,
        destination=destination,
        uses=uses,
        qty=qty,
        auto_on=auto_on
    )
    if not res_save.get("ok"):
        return jsonify(res_save), 400

    entry = res_save.get("entry") or res_save
    proxy_engine.refresh_pac()
    proxy_engine.log(f"Efecto trucado: {base_item} -> {entry['full_action']} ({destination})", "TRUCO")

    res = {
        "ok": True,
        "message": f"Listo: {base_item} trucado con acción '{entry['full_action']}'.",
        "effect": entry,
        "swf_file": res_save.get("swf_file"),
    }

    if queue_lola:
        parsed, _script = sync_lola_with_saved_tricks("save-effect")
        res["lola_synced"] = True
        res["lola_count"] = len(parsed)
    else:
        parsed, _script = sync_lola_with_saved_tricks("save-effect-silent")
        res["lola_synced"] = True
        res["lola_count"] = len(parsed)

    return jsonify(res)


@app.route("/api/effects/delete", methods=["POST"])
def api_effects_delete():
    req = request.get_json(silent=True) or {}
    effect_id = (req.get("id") or "").strip()
    if not effect_id:
        return jsonify({"ok": False, "error": "Falta id de efecto"}), 400

    deleted = trucador.delete_effect_trick(effect_id)
    ok_del = deleted.get("ok") if isinstance(deleted, dict) else deleted
    if ok_del:
        proxy_engine.refresh_pac()
        parsed, _ = sync_lola_with_saved_tricks("delete-effect")
        proxy_engine.log(f"Efecto eliminado: {effect_id}", "TRUCO")
        return jsonify({"ok": True, "message": "Efecto eliminado.", "lola_count": len(parsed)})
    return jsonify({"ok": False, "error": "No se encontró el efecto"}), 404


@app.route("/api/effects/queue-lola", methods=["POST"])
def api_effects_queue_lola():
    parsed, _script = sync_lola_with_saved_tricks("queue-effects")
    return jsonify({
        "ok": True,
        "message": f"Listo para Lola: {len(parsed)} objetos en cola.",
        "lola_count": len(parsed)
    })

@app.route("/api/tiendas", methods=["GET"])
@app.route("/api/behaviors", methods=["GET"])
def api_tiendas():
    q = request.args.get("q", "")
    btype = request.args.get("type", "")
    
    # Obtener todas las coincidencias para q (sin filtro de tipo) para calcular los contadores globales
    all_query_matches = catalog_db.search_behaviors(q, "")
    counts = {
        "all": len(all_query_matches),
        "catalog": 0,
        "vendor": 0,
        "npc": 0,
        "portal": 0,
        "banner": 0,
    }
    for item in all_query_matches:
        t = (item.get("type") or "catalog").lower()
        if t in counts:
            counts[t] += 1
        else:
            counts[t] = 1

    if btype and btype != "all":
        behaviors = [b for b in all_query_matches if (b.get("type") or "").lower() == btype.lower()]
    else:
        behaviors = all_query_matches

    return jsonify({
        "ok": True,
        "count": len(behaviors),
        "total": len(all_query_matches),
        "counts": counts,
        "behaviors": behaviors,
        "tiendas": behaviors,
    })


@app.route("/api/tiendas/activate", methods=["POST"])
@app.route("/api/behaviors/activate", methods=["POST"])
def api_tiendas_activate():
    """
    Activa un catálogo o un behavior completo en Lola con sintaxis válida de MG.
    """
    req = request.get_json(silent=True) or {}
    catalog_name = (req.get("catalog") or "").strip()
    behavior_name = (req.get("behavior") or "").strip()
    custom_script = (req.get("script") or "").strip()

    if behavior_name:
        all_b = catalog_db.load_behaviors()
        matched = next((b for b in all_b if b.get("behavior") == behavior_name or b.get("id") == behavior_name), None)
        if matched:
            try:
                npc_script, label = payload_builder.adapt_behavior_script_for_lola(matched)
            except ValueError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 400
        elif custom_script:
            npc_script = custom_script
            label = f"Behavior '{behavior_name}' (Custom)"
        elif catalog_name:
            npc_script = payload_builder.build_catalog_payload(catalog_name)
            label = f"Catálogo '{catalog_name}'"
        else:
            return jsonify({"ok": False, "error": f"No se encontró script para behavior: {behavior_name}"}), 404
    elif catalog_name:
        npc_script = payload_builder.build_catalog_payload(catalog_name)
        label = f"Catálogo '{catalog_name}'"
    elif custom_script:
        npc_script = custom_script
        label = "Script personalizado"
    else:
        return jsonify({"ok": False, "error": "Falta parámetro 'catalog', 'behavior' o 'script'"}), 400

    proxy_engine.set_payload(npc_script)
    proxy_engine.log(f"{label} activado en Lola", "BEHAVIOR")
    return jsonify({
        "ok": True,
        "message": f"{label} preparado. Abrí MG aplicado para recargar el NPC y después hablá con Lola. No modifica ni guarda tu look en edición.",
        "script": npc_script,
    })


@app.route("/api/overrides", methods=["GET"])
def api_overrides():
    overrides_dir = BASE_DIR / "data" / "overrides"
    files = []
    if overrides_dir.exists():
        for f in overrides_dir.glob("*.swf"):
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "path": str(f)
            })
    return jsonify({"ok": True, "overrides": files})


@app.route("/api/overrides/<filename>", methods=["DELETE"])
def api_delete_override(filename):
    file_path = BASE_DIR / "data" / "overrides" / filename
    if file_path.exists():
        try:
            file_path.unlink()
            trucador.clear_pack_tricks(filename)
            proxy_engine.refresh_pac()
            proxy_engine.log(f"Archivo modificado eliminado: {filename}", "CLEAN")
            return jsonify({"ok": True, "message": "Archivo modificado eliminado"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})
    return jsonify({"ok": False, "error": "Archivo no encontrado"})


@app.route("/api/logs", methods=["GET"])
def api_logs():
    st = proxy_engine.get_status()
    return jsonify({
        "ok": True,
        "logs": proxy_engine.get_logs(120),
        "health": st.get("health"),
        "stats": st.get("stats"),
        "payload_summary": st.get("payload_summary"),
    })


@app.route("/api/library/status", methods=["GET"])
def api_library_status():
    try:
        data = asset_library.review_library()
        data["job"] = asset_library.job_snapshot()
        data["game_running"] = game_launcher.is_game_running()
        return jsonify(data)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.route("/api/library/review", methods=["POST"])
def api_library_review():
    try:
        data = asset_library.review_library()
        data["job"] = asset_library.job_snapshot()
        data["game_running"] = game_launcher.is_game_running()
        return jsonify(data)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.route("/api/library/download", methods=["POST"])
def api_library_download():
    return jsonify(asset_library.start_download_async())


@app.route("/api/library/zip", methods=["POST"])
def api_library_zip():
    return jsonify(asset_library.start_zip_async())


@app.route("/api/library/job", methods=["GET"])
def api_library_job():
    return jsonify({"ok": True, **asset_library.job_snapshot()})


@app.route("/api/library/dump-mmo", methods=["POST"])
def api_library_dump_mmo():
    if asset_library.job_snapshot().get("running"):
        return jsonify({"ok": False, "error": "Esperá que termine lo que está corriendo."})
    if not game_launcher.is_game_running():
        return jsonify({
            "ok": False,
            "error": "Abrí Mundo Gaturro, entrá a un mundo y después tocá Sacar del juego.",
        })

    def _run():
        asset_library._set_job(
            running=True, kind="dump", done=0, total=1,
            message="Buscando el archivo del juego en la memoria...", result=None
        )
        try:
            res = mmo_dump.dump_mmo_from_game()
            if res.get("ok"):
                seed_upd = asset_library.refresh_catalog_seed_from_mmo()
                res["seed_updated"] = bool(seed_upd.get("ok"))
                res["seed_count"] = seed_upd.get("count")
                review = asset_library.review_library()
                res["catalog"] = review.get("catalog", 0)
                res["missing"] = review.get("missing", 0)
                res["by_category"] = review.get("by_category")
                res["catalog_healthy"] = review.get("catalog_healthy")
                asset_library._set_job(
                    running=False,
                    message=(
                        f"Listo, saqué el MMO. Catálogo: {res['catalog']} "
                        f"(faltan {res['missing']})."
                    ),
                    result=res,
                )
            else:
                asset_library._set_job(running=False, message=res.get("error") or "No se pudo.", result=res)
        except Exception as exc:
            asset_library._set_job(
                running=False, message="No se pudo sacar el archivo.",
                result={"ok": False, "error": str(exc)}
            )

    import threading
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/library/zip/file")
def api_library_zip_file():
    path = asset_library.zip_path()
    if not path.exists():
        return jsonify({"ok": False, "error": "Todavía no hay zip."}), 404
    return send_from_directory(str(path.parent), path.name, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5500))
    # PAC por Flask (:5500) — el helper :18081 se trababa y el MG quedaba DIRECT.
    proxy_engine.ui_port = port
    print(f"Iniciando naw-tool en http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
