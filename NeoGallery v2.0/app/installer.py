import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import requests

from . import config, paths
from .hosts import registry


SITE_TEMPLATE = paths.BASE / "site_template"


@dataclass
class InstallReport:
    uploaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


# module scope so Settings can show the last republish errors after a navigation
last_republish_report: InstallReport | None = None


def _snapshot_gallery_state() -> dict:
    cfg = config.get()
    return {
        "use_thumbnails": cfg.use_thumbnails,
        "thumb_width": cfg.thumb_width,
        "full_image_display_width": cfg.full_image_display_width,
        "loading_image": cfg.loading_image,
        "show_loader": cfg.show_loader,
    }


def test_neocities_connection() -> tuple[bool, str]:
    key = config.get().neocities.api_key
    if not key:
        return (False, "No API key set")
    try:
        r = requests.get(
            "https://neocities.org/api/info",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10,
        )
        if r.status_code == 200:
            info = r.json().get("info", {})
            name = info.get("sitename") or "your site"
            return (True, f"Connected to {name}")
        if r.status_code == 401:
            return (False, "Invalid API key")
        return (False, f"Neocities returned {r.status_code}")
    except requests.RequestException as e:
        return (False, f"Connection failed: {e}")


# template path  ->  remote path builder (cfg -> str)
def _remote_path_for(rel: str) -> str:
    n = config.get().neocities
    gallery = (n.gallery_dir or "").strip("/")
    json_dir = (n.json_dir or "").strip("/")

    if rel == "NeoGallery.html":
        return f"{gallery}/NeoGallery.html" if gallery else "NeoGallery.html"
    if rel == "tagTemplate.html":
        return ""  # local-only, never uploaded
    if rel.startswith("css/") or rel.startswith("js/") or rel.startswith("assets/"):
        return f"{gallery}/{rel}" if gallery else rel
    if rel == "json/media.json":
        return f"{json_dir}/media.json" if json_dir else "media.json"
    if rel == "json/tags.json":
        return f"{json_dir}/tags.json" if json_dir else "tags.json"
    return rel


def _walk_template() -> list[tuple[Path, str]]:
    out = []
    if not SITE_TEMPLATE.exists():
        return out
    for f in sorted(SITE_TEMPLATE.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(SITE_TEMPLATE).as_posix()
        remote = _remote_path_for(rel)
        if not remote:
            continue
        out.append((f, remote))
    return out


def _remote_inventory() -> set[str]:
    key = config.get().neocities.api_key
    if not key:
        return set()
    try:
        r = requests.get(
            "https://neocities.org/api/list",
            headers={"Authorization": f"Bearer {key}"},
            timeout=15,
        )
        r.raise_for_status()
        files = r.json().get("files", [])
        return {f["path"].lstrip("/") for f in files if not f.get("is_directory")}
    except (requests.RequestException, ValueError, KeyError):
        return set()  # if listing fails, treat as empty (we'll upload everything)


def install_site_template(progress_cb: Callable[[str, str, str], None] | None = None) -> InstallReport:
    report = InstallReport()
    key = config.get().neocities.api_key
    if not key:
        report.errors.append({"file": "(setup)", "error": "Neocities API key missing"})
        return report

    try:
        existing = _remote_inventory()
    except Exception as e:
        report.errors.append({"file": "(listing site)", "error": f"Couldn't list your site: {e}"})
        return report

    plan = _walk_template()

    for local, remote in plan:
        normalized = remote.lstrip("/")
        if normalized in existing:
            report.skipped.append(remote)
            if progress_cb:
                progress_cb(remote, "skipped", "already exists")
            continue
        if progress_cb:
            progress_cb(remote, "uploading", "")
        try:
            upload_src = _render_if_template(local)
            _raw_upload(upload_src, remote, key)
        except requests.Timeout:
            msg = "timed out after 60s"
            report.errors.append({"file": remote, "error": msg})
            if progress_cb: progress_cb(remote, "error", msg)
            continue
        except requests.HTTPError as e:
            body = (e.response.text or "")[:200] if e.response is not None else ""
            msg = f"HTTP {e.response.status_code if e.response is not None else '?'}: {body or str(e)}"
            report.errors.append({"file": remote, "error": msg})
            if progress_cb: progress_cb(remote, "error", msg)
            continue
        except requests.RequestException as e:
            msg = f"network error: {e}"
            report.errors.append({"file": remote, "error": msg})
            if progress_cb: progress_cb(remote, "error", msg)
            continue
        except Exception as e:
            report.errors.append({"file": remote, "error": str(e)})
            if progress_cb: progress_cb(remote, "error", str(e))
            continue

        report.uploaded.append(remote)
        if progress_cb:
            progress_cb(remote, "uploaded", "")

    # treat a clean wizard install as the baseline for "what's applied"
    if not report.errors:
        config.get().last_applied_gallery_state = _snapshot_gallery_state()
        config.commit()

    return report


def republish_site(progress_cb: Callable[[str, str, str], None] | None = None) -> InstallReport:
    """force-upload NeoGallery.html, tag pages, loader, and media.json (overwrites remote)."""
    global last_republish_report
    from . import storage, tag_service
    report = InstallReport()
    key = config.get().neocities.api_key
    if not key:
        report.errors.append({"file": "(setup)", "error": "Neocities API key missing"})
        last_republish_report = report
        return report

    n = config.get().neocities
    gallery = (n.gallery_dir or "").strip("/")
    tag_dir = (n.tag_dir or "").strip("/")
    json_dir = (n.json_dir or "").strip("/")

    def _try(remote: str, src: Path) -> None:
        if progress_cb:
            progress_cb(remote, "uploading", "")
        try:
            _raw_upload(src, remote, key)
            report.uploaded.append(remote)
            if progress_cb:
                progress_cb(remote, "uploaded", "")
        except Exception as e:
            report.errors.append({"file": remote, "error": str(e)})
            if progress_cb:
                progress_cb(remote, "error", str(e))

    # 1) gallery index -- render then upload
    art_local = SITE_TEMPLATE / "NeoGallery.html"
    if art_local.exists():
        rendered = _render_if_template(art_local)
        target = f"{gallery}/NeoGallery.html" if gallery else "NeoGallery.html"
        _try(target, rendered)

    # 2) per-tag pages
    for tag in storage.load_tags():
        if tag["name"] in tag_service.SYSTEM_TAGS:
            continue
        html = tag_service._render_tag_html(tag, tag.get("coverPhoto", ""))
        tmp = Path(tempfile.gettempdir()) / f"_ng_tag_{tag['name']}.html"
        tmp.write_text(html, encoding="utf-8")
        target = f"{tag_dir}/{tag['name']}.html" if tag_dir else f"{tag['name']}.html"
        _try(target, tmp)

    # 3) loader asset (cheap -- just always push the active one so renames/uploads land)
    if config.get().loading_image:
        loader_local = SITE_TEMPLATE / config.get().loading_image
        if loader_local.exists():
            target = f"{gallery}/{config.get().loading_image}" if gallery else config.get().loading_image
            _try(target, loader_local)

    # 4) media.json -- refresh embedded config block
    if paths.MEDIA_JSON.exists():
        target = f"{json_dir}/{config.get().media_json_name}" if json_dir else config.get().media_json_name
        _try(target, paths.MEDIA_JSON)

    last_republish_report = report
    # only snapshot on clean run; any error keeps the pending indicator up
    if not report.errors:
        config.get().last_applied_gallery_state = _snapshot_gallery_state()
        config.commit()

    return report


def _render_if_template(local: Path) -> Path:
    """apply loader substitutions if local lives in site_template/, else pass through."""
    if local.suffix.lower() != ".html":
        return local
    try:
        local.relative_to(SITE_TEMPLATE)
    except ValueError:
        return local
    # lazy import: avoid a top-level cycle with tag_service
    from . import tag_service
    text = local.read_text(encoding="utf-8")
    rendered = tag_service.apply_loader_substitutions(text)
    if rendered == text:
        return local
    tmp = Path(tempfile.gettempdir()) / f"_ng_render_{local.name}"
    tmp.write_text(rendered, encoding="utf-8")
    return tmp


def _raw_upload(local: Path, remote: str, api_key: str) -> None:
    target = remote.lstrip("/")
    with open(local, "rb") as f:
        r = requests.post(
            "https://neocities.org/api/upload",
            headers={"Authorization": f"Bearer {api_key}"},
            files={target: (local.name, f)},
            timeout=60,
        )
    r.raise_for_status()
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if body.get("result") and body["result"] != "success":
        raise RuntimeError(body.get("message") or "upload reported failure")
