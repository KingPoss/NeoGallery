import json as _json
import queue
import tempfile
import threading
import webbrowser
from dataclasses import asdict
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from . import config, gallery_service, installer, paths, storage, sync, tag_service
from .hosts import registry


def create_app() -> Flask:
    paths.ensure_dirs()
    static = paths.BASE / "static"
    app = Flask(__name__, static_folder=str(static), static_url_path="/static")

    # ---------- static + local file serving ----------
    @app.route("/")
    def index():
        return send_from_directory(str(static), "index.html")

    def _no_cache(resp):
        # local files get rewritten when thumbnails regenerate; force a revalidation
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp

    @app.route("/local/art/<path:name>")
    def local_art(name):
        return _no_cache(send_from_directory(str(paths.ART), name))

    @app.route("/local/thumbs/<path:name>")
    def local_thumb(name):
        return _no_cache(send_from_directory(str(paths.THUMBS), name))

    @app.route("/local/tag_covers/<path:name>")
    def local_cover(name):
        return _no_cache(send_from_directory(str(paths.TAG_COVERS), name))

    # ---------- media ----------
    @app.get("/api/media")
    def list_media():
        return jsonify(storage.load_media())

    @app.post("/api/media")
    def upload_media():
        files = request.files.getlist("files")
        meta_raw = request.form.get("meta", "[]")
        try:
            meta = _json.loads(meta_raw)
        except _json.JSONDecodeError:
            meta = []
        if not files:
            return jsonify({"error": "no files"}), 400

        tmp = Path(tempfile.gettempdir()) / "neogallery_uploads"
        tmp.mkdir(exist_ok=True)
        items = []
        for i, f in enumerate(files):
            target = tmp / (f.filename or f"upload_{i}")
            f.save(target)
            m = meta[i] if i < len(meta) else {}
            items.append({
                "path": target,
                "title": m.get("title", ""),
                "description": m.get("description", ""),
                "tags": m.get("tags", []) or [],
            })
        added = gallery_service.add_art(items)
        return jsonify({"added": added, "count": len(added)})

    @app.patch("/api/media")
    def edit_media():
        data = request.get_json(force=True)
        gallery_service.edit_art(
            data["fullSrc"],
            title=data.get("title", ""),
            description=data.get("description", ""),
            tags=data.get("tags", []) or [],
        )
        return jsonify({"ok": True})

    @app.delete("/api/media")
    def delete_media():
        data = request.get_json(force=True)
        media = storage.load_media()
        entry = next((e for e in media if e.get("fullSrc") == data.get("fullSrc")), None)
        if not entry:
            return jsonify({"error": "not found"}), 404
        gallery_service.delete_art(entry)
        return jsonify({"ok": True})

    @app.post("/api/media/reorder")
    def reorder():
        data = request.get_json(force=True)
        gallery_service.reorder(data.get("order", []))
        return jsonify({"ok": True})

    @app.post("/api/media/regenerate-thumbs")
    def regen():
        n = gallery_service.regenerate_thumbnails()
        return jsonify({"regenerated": n})

    @app.get("/api/media/regenerate-thumbs/stream")
    def regen_stream():
        q: queue.Queue = queue.Queue()

        def cb(p):
            q.put({
                "file": p.filename,
                "status": "uploaded" if p.status == "done" else p.status,
                "note": p.error or "",
                "index": p.index,
                "total": p.total,
            })

        def runner():
            try:
                count = gallery_service.regenerate_thumbnails(on_progress=cb)
                q.put({"done": True, "count": count})
            except Exception as e:
                q.put({"done": True, "fatal": str(e)})

        threading.Thread(target=runner, daemon=True).start()

        def stream():
            while True:
                evt = q.get()
                yield f"data: {_json.dumps(evt)}\n\n"
                if evt.get("done"):
                    return

        return Response(stream(), mimetype="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    # ---------- tags ----------
    @app.get("/api/tags")
    def list_tags():
        return jsonify(storage.load_tags())

    @app.post("/api/tags")
    def create_tag():
        data = request.form
        cover = request.files.get("cover")
        cover_path = None
        if cover and cover.filename:
            tmp = Path(tempfile.gettempdir()) / "neogallery_covers"
            tmp.mkdir(exist_ok=True)
            cover_path = tmp / cover.filename
            cover.save(cover_path)
        try:
            tag = tag_service.create_tag(
                data.get("name", ""),
                data.get("metaDesc", ""),
                data.get("pageTitle", "") or data.get("name", ""),
                data.get("linkTitle", "") or data.get("name", ""),
                cover_path,
            )
            return jsonify(tag)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.put("/api/tags/<name>")
    def edit_tag(name):
        data = request.form
        cover = request.files.get("cover")
        cover_path = None
        if cover and cover.filename:
            tmp = Path(tempfile.gettempdir()) / "neogallery_covers"
            tmp.mkdir(exist_ok=True)
            cover_path = tmp / cover.filename
            cover.save(cover_path)
        try:
            tag = tag_service.edit_tag(
                name,
                new_name=data.get("name", name),
                meta_desc=data.get("metaDesc", ""),
                page_title=data.get("pageTitle", "") or data.get("name", name),
                link_title=data.get("linkTitle", "") or data.get("name", name),
                cover_src=cover_path,
            )
            return jsonify(tag)
        except (KeyError, ValueError) as e:
            return jsonify({"error": str(e)}), 400

    @app.delete("/api/tags/<name>")
    def remove_tag(name):
        try:
            tag_service.delete_tag(name)
            return jsonify({"ok": True})
        except KeyError as e:
            return jsonify({"error": str(e)}), 404

    # ---------- settings ----------
    @app.get("/api/settings")
    def get_settings():
        cfg = config.get()
        return jsonify({
            "config": asdict(cfg),
            "hosts": [{"id": h.id, "name": h.display_name} for h in registry.all_hosts()],
        })

    @app.put("/api/settings")
    def put_settings():
        data = request.get_json(force=True)
        cfg = config.get()
        for k, v in (data or {}).items():
            if k in ("neocities", "catbox") and isinstance(v, dict):
                sub = getattr(cfg, k)
                for sk, sv in v.items():
                    if hasattr(sub, sk):
                        setattr(sub, sk, sv)
            elif hasattr(cfg, k):
                setattr(cfg, k, v)
        config.commit()
        return jsonify({"ok": True})

    @app.post("/api/import-v1")
    def import_v1():
        m, t = storage.import_v1_data()
        return jsonify({"media": m, "tags": t})

    # ---------- onboarding ----------
    @app.get("/api/onboarding/status")
    def onboarding_status():
        return jsonify({"completed": config.get().onboarding_completed})

    @app.post("/api/onboarding/complete")
    def onboarding_complete():
        config.get().onboarding_completed = True
        config.commit()
        # seed the built-in 'random' tag if it isn't already there
        tags = storage.load_tags()
        if not any(t.get("name") == "random" for t in tags):
            tags.append({"name": "random"})
            storage.save_tags(tags)
        return jsonify({"ok": True})

    @app.post("/api/onboarding/reset")
    def onboarding_reset():
        config.get().onboarding_completed = False
        config.commit()
        return jsonify({"ok": True})

    @app.post("/api/neocities/test")
    def neocities_test():
        # accept optional API key to test before saving
        data = request.get_json(silent=True) or {}
        new_key = data.get("apiKey")
        if new_key is not None:
            config.get().neocities.api_key = new_key
            config.commit()
        ok, msg = installer.test_neocities_connection()
        return jsonify({"ok": ok, "message": msg})

    @app.get("/api/neocities/info")
    def neocities_info():
        # sitename + (optional) custom domain for the wizard's verify step
        import requests as _r
        key = config.get().neocities.api_key
        if not key:
            return jsonify({"ok": False, "message": "No API key set"}), 400
        try:
            r = _r.get(
                "https://neocities.org/api/info",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            if r.status_code != 200:
                return jsonify({"ok": False, "message": f"Neocities returned {r.status_code}"}), 200
            info = r.json().get("info", {})
            sitename = info.get("sitename", "(unknown)")
            # neocities returns "" or null when no custom domain is set
            domain = (info.get("domain") or "").strip() or f"{sitename}.neocities.org"
            return jsonify({"ok": True, "sitename": sitename, "domain": domain})
        except _r.RequestException as e:
            return jsonify({"ok": False, "message": str(e)}), 200

    @app.post("/api/site/install")
    def site_install():
        report = installer.install_site_template()
        return jsonify({
            "uploaded": report.uploaded,
            "skipped": report.skipped,
            "errors": report.errors,
        })

    @app.get("/api/site/loader-preview")
    def site_loader_preview():
        # serve a single bundled-template file by relative path, scoped to assets/loaders/
        rel = (request.args.get("path") or "").lstrip("/")
        if not rel.startswith("assets/loaders/"):
            return jsonify({"error": "out of scope"}), 400
        full = installer.SITE_TEMPLATE / rel
        if not full.is_file():
            return jsonify({"error": "not found"}), 404
        return send_from_directory(str(full.parent), full.name)

    @app.get("/api/site/loaders")
    def site_loaders():
        # presets bundled in site_template, plus any custom ones the user has uploaded
        loaders_dir = installer.SITE_TEMPLATE / "assets" / "loaders"
        items = []
        if loaders_dir.exists():
            for f in sorted(loaders_dir.iterdir()):
                if f.is_file():
                    items.append({"path": f"assets/loaders/{f.name}", "name": f.stem})
        return jsonify({"loaders": items})

    @app.post("/api/site/loader/upload")
    def site_loader_upload():
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"error": "no file"}), 400
        loaders_dir = installer.SITE_TEMPLATE / "assets" / "loaders"
        loaders_dir.mkdir(parents=True, exist_ok=True)
        # prefix custom uploads so they're easy to spot/delete
        safe = "".join(c for c in f.filename if c.isalnum() or c in "._-").lstrip(".")
        if not safe:
            safe = "loader.gif"
        target = loaders_dir / f"custom-{safe}"
        f.save(target)
        return jsonify({"path": f"assets/loaders/{target.name}", "name": target.stem})

    @app.post("/api/site/republish")
    def site_republish():
        report = installer.republish_site()
        return jsonify({
            "uploaded": report.uploaded,
            "skipped": report.skipped,
            "errors": report.errors,
        })

    @app.get("/api/site/republish/stream")
    def site_republish_stream():
        q: queue.Queue = queue.Queue()

        def cb(file: str, status: str, note: str = "") -> None:
            q.put({"file": file, "status": status, "note": note})

        def runner():
            try:
                report = installer.republish_site(progress_cb=cb)
                q.put({"done": True, "summary": {
                    "uploaded": len(report.uploaded),
                    "errors": len(report.errors),
                }})
            except Exception as e:
                q.put({"done": True, "fatal": str(e)})

        threading.Thread(target=runner, daemon=True).start()

        def stream():
            while True:
                evt = q.get()
                yield f"data: {_json.dumps(evt)}\n\n"
                if evt.get("done"):
                    return

        return Response(stream(), mimetype="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    @app.get("/api/sync/state")
    def sync_state():
        return jsonify(sync.remote_state())

    @app.get("/api/sync/stream")
    def sync_stream():
        q: queue.Queue = queue.Queue()

        def cb(file: str, status: str, note: str = "") -> None:
            q.put({"file": file, "status": status, "note": note})

        def runner():
            try:
                report = sync.sync_from_neocities(progress_cb=cb)
                q.put({"done": True, "summary": {
                    "pulled": len(report.pulled),
                    "skipped": len(report.skipped),
                    "errors": len(report.errors),
                }})
            except Exception as e:
                q.put({"done": True, "fatal": str(e)})

        threading.Thread(target=runner, daemon=True).start()

        def stream():
            while True:
                evt = q.get()
                yield f"data: {_json.dumps(evt)}\n\n"
                if evt.get("done"):
                    return

        return Response(stream(), mimetype="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    @app.get("/api/site/republish/last")
    def site_republish_last():
        # last result from in-process memory (cleared on app restart) -- used by Settings
        # to restore a feed when the user navigates back after a mid-flight republish
        r = installer.last_republish_report
        if r is None:
            return jsonify({"present": False})
        return jsonify({
            "present": True,
            "uploaded": r.uploaded,
            "skipped": r.skipped,
            "errors": r.errors,
        })

    @app.get("/api/site/install/stream")
    def site_install_stream():
        # SSE: per-file progress so the wizard can show a live feed
        q: queue.Queue = queue.Queue()

        def cb(file: str, status: str, note: str = "") -> None:
            q.put({"file": file, "status": status, "note": note})

        def runner():
            try:
                report = installer.install_site_template(progress_cb=cb)
                q.put({"done": True, "summary": {
                    "uploaded": len(report.uploaded),
                    "skipped": len(report.skipped),
                    "errors": len(report.errors),
                }})
            except Exception as e:
                q.put({"done": True, "fatal": str(e)})

        threading.Thread(target=runner, daemon=True).start()

        def stream():
            while True:
                evt = q.get()
                yield f"data: {_json.dumps(evt)}\n\n"
                if evt.get("done"):
                    return

        return Response(stream(), mimetype="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    @app.post("/api/open")
    def open_external():
        # opens a URL in the system default browser (otherwise pywebview hijacks the click)
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            return jsonify({"ok": False, "error": "invalid url"}), 400
        try:
            webbrowser.open(url, new=2)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    return app
