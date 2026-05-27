import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import requests

from . import config, installer, paths, storage


@dataclass
class SyncReport:
    pulled: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


# ---------- detection ----------

def _site_info(key: str) -> dict | None:
    try:
        r = requests.get(
            "https://neocities.org/api/info",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        return r.json().get("info") or {}
    except requests.RequestException:
        return None


def _site_files(key: str) -> list[dict]:
    try:
        r = requests.get(
            "https://neocities.org/api/list",
            headers={"Authorization": f"Bearer {key}"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("files", [])
    except (requests.RequestException, ValueError):
        return []


def _public_base() -> tuple[str | None, str]:
    """returns (domain, gallery_dir) -- domain falls back to <sitename>.neocities.org."""
    key = config.get().neocities.api_key
    if not key:
        return None, ""
    info = _site_info(key) or {}
    sitename = info.get("sitename") or ""
    domain = (info.get("domain") or "").strip() or (f"{sitename}.neocities.org" if sitename else "")
    gallery = (config.get().neocities.gallery_dir or "").strip("/")
    return domain, gallery


def detect_remote_install() -> dict:
    """find NeoGallery.html on the user's site, infer the install layout from it."""
    key = config.get().neocities.api_key
    if not key:
        return {"found": False}
    art_name = config.get().art_html_name
    files = _site_files(key)
    paths_set = {f["path"].lstrip("/"): f for f in files if not f.get("is_directory")}

    # find any NeoGallery.html on the site
    matches = [p for p in paths_set if p.endswith("/" + art_name) or p == art_name]
    if not matches:
        return {"found": False}
    # prefer the shallowest match (closest to root)
    chosen = sorted(matches, key=lambda p: p.count("/"))[0]
    gallery_dir = chosen[: -len(art_name)].rstrip("/")

    # derive the rest from the v2 install convention
    suggested = {
        "gallery_dir": gallery_dir,
        "tag_dir": gallery_dir,
        "json_dir": f"{gallery_dir}/json" if gallery_dir else "json",
        "art_dir": f"{gallery_dir}/assets/media" if gallery_dir else "assets/media",
        "thumb_dir": f"{gallery_dir}/assets/thumbnails" if gallery_dir else "assets/thumbnails",
    }
    return {
        "found": True,
        "suggested_dirs": suggested,
        "art_html_path": chosen,
        "files": paths_set,
    }


def _fetch_remote_posts(json_dir: str) -> list[dict] | None:
    media_name = config.get().media_json_name
    url = _abs_url(f"{json_dir}/{media_name}" if json_dir else media_name)
    if not url:
        return None
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("posts", [])
    except (requests.RequestException, ValueError):
        return None
    return None


def remote_state() -> dict:
    """cheap stats for the launch drift check."""
    key = config.get().neocities.api_key
    if not key:
        return {"ok": False, "message": "No API key set", "detected": False, "in_sync": True}
    info = _site_info(key)
    if info is None:
        return {"ok": False, "message": "Couldn't reach Neocities", "detected": False, "in_sync": True}

    sitename = info.get("sitename") or ""
    domain = (info.get("domain") or "").strip() or (f"{sitename}.neocities.org" if sitename else "")

    detection = detect_remote_install()
    detected = detection.get("found", False)
    suggested = detection.get("suggested_dirs") if detected else None

    json_dir = (config.get().neocities.json_dir or "").strip("/")
    remote_posts = _fetch_remote_posts(json_dir)
    if remote_posts is None and detected:
        # fall back to the detected json_dir if the configured one didn't pan out
        remote_posts = _fetch_remote_posts(suggested["json_dir"])

    local_count = len(storage.load_media())
    remote_count = len(remote_posts) if remote_posts is not None else 0
    return {
        "ok": True,
        "sitename": sitename,
        "domain": domain,
        "local_posts": local_count,
        "remote_posts": remote_count,
        "in_sync": local_count == remote_count,
        "detected": detected,
        "suggested_dirs": suggested,
    }


# ---------- pull ----------

def _abs_url(rel: str) -> str:
    """build a fetchable URL for a path relative to the gallery_dir (or site root)."""
    domain, gallery = _public_base()
    if not domain:
        return ""
    rel = (rel or "").lstrip("/")
    if gallery and not rel.startswith(gallery + "/"):
        full = f"https://{domain}/{gallery}/{rel}"
    else:
        full = f"https://{domain}/{rel}"
    return full


def _download_file(url: str, dest: Path, progress_cb: Callable | None, label: str) -> str:
    """download one file. returns 'pulled', 'skipped', or 'error:<msg>'."""
    if dest.exists() and dest.stat().st_size > 0:
        if progress_cb:
            progress_cb(label, "skipped", "already present")
        return "skipped"
    if progress_cb:
        progress_cb(label, "uploading", "")  # reuse the same status name for spinner CSS
    try:
        r = requests.get(url, timeout=60, stream=True)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if chunk:
                    f.write(chunk)
        if progress_cb:
            progress_cb(label, "uploaded", "")
        return "pulled"
    except requests.RequestException as e:
        msg = str(e)
        if progress_cb:
            progress_cb(label, "error", msg)
        return f"error:{msg}"


def sync_from_neocities(progress_cb: Callable | None = None) -> SyncReport:
    report = SyncReport()
    cfg = config.get()
    key = cfg.neocities.api_key
    if not key:
        report.errors.append({"file": "(setup)", "error": "Neocities API key missing"})
        return report

    json_dir = (cfg.neocities.json_dir or "").strip("/")

    # 1) media.json
    media_url = _abs_url(f"{json_dir}/{cfg.media_json_name}" if json_dir else cfg.media_json_name)
    media_label = f"{json_dir}/{cfg.media_json_name}" if json_dir else cfg.media_json_name
    if progress_cb:
        progress_cb(media_label, "uploading", "")
    try:
        r = requests.get(media_url, timeout=15)
        r.raise_for_status()
        data = r.json()
        posts = data.get("posts", data) if isinstance(data, dict) else data
        if not isinstance(posts, list):
            raise ValueError("media.json did not contain a posts array")
        storage.save_media(posts)
        report.pulled.append(media_label)
        if progress_cb:
            progress_cb(media_label, "uploaded", "")
    except Exception as e:
        report.errors.append({"file": media_label, "error": str(e)})
        if progress_cb:
            progress_cb(media_label, "error", str(e))
        return report

    # 2) tags.json
    tags_url = _abs_url(f"{json_dir}/{cfg.tag_list_json_name}" if json_dir else cfg.tag_list_json_name)
    tags_label = f"{json_dir}/{cfg.tag_list_json_name}" if json_dir else cfg.tag_list_json_name
    if progress_cb:
        progress_cb(tags_label, "uploading", "")
    try:
        r = requests.get(tags_url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                storage.save_tags(data)
        report.pulled.append(tags_label)
        if progress_cb:
            progress_cb(tags_label, "uploaded", "")
    except Exception as e:
        report.errors.append({"file": tags_label, "error": str(e)})
        if progress_cb:
            progress_cb(tags_label, "error", str(e))

    # 3) art + thumbs (neocities-hosted only)
    for entry in storage.load_media():
        full_src = entry.get("fullSrc") or ""
        thumb_src = entry.get("thumbnailSrc") or ""
        if not full_src or "catbox.moe" in full_src or full_src.startswith("http"):
            # catbox URL or any absolute URL we don't own -- leave it alone
            report.skipped.append(full_src or "(unknown)")
            continue
        for src, dest_dir in ((full_src, paths.ART), (thumb_src, paths.THUMBS)):
            if not src or "catbox.moe" in src or src.startswith("http"):
                continue
            name = Path(src).name
            label = src
            result = _download_file(_abs_url(src), dest_dir / name, progress_cb, label)
            if result == "pulled":
                report.pulled.append(label)
            elif result == "skipped":
                report.skipped.append(label)
            else:
                report.errors.append({"file": label, "error": result.split(":", 1)[1]})

    # 4) tag covers
    for tag in storage.load_tags():
        cover = tag.get("coverPhoto")
        if not cover or cover.startswith("http"):
            continue
        name = Path(cover).name
        label = cover
        result = _download_file(_abs_url(cover), paths.TAG_COVERS / name, progress_cb, label)
        if result == "pulled":
            report.pulled.append(label)
        elif result == "skipped":
            report.skipped.append(label)
        else:
            report.errors.append({"file": label, "error": result.split(":", 1)[1]})

    # 5) custom throbber if it's not already bundled
    loader_rel = cfg.loading_image or ""
    if loader_rel and loader_rel.startswith("assets/loaders/"):
        bundled = installer.SITE_TEMPLATE / loader_rel
        if not bundled.exists():
            label = loader_rel
            result = _download_file(_abs_url(loader_rel), bundled, progress_cb, label)
            if result == "pulled":
                report.pulled.append(label)
            elif result == "skipped":
                report.skipped.append(label)
            else:
                report.errors.append({"file": label, "error": result.split(":", 1)[1]})

    return report
