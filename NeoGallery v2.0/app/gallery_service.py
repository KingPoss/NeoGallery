from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import config, images, paths, storage
from .hosts import registry


@dataclass
class UploadProgress:
    filename: str
    index: int
    total: int
    status: str   # "uploading" / "done" / "error"
    error: str = ""


def _safe_name(name: str) -> str:
    keep = "._- "
    cleaned = "".join(c for c in name if c.isalnum() or c in keep).strip().replace(" ", "_")
    return cleaned or "file"


def _push_media_json() -> None:
    site = registry.site_host()
    if not site.is_configured():
        return
    site.upload(paths.MEDIA_JSON, kind="json", dest_name=config.get().media_json_name)


def add_art(
    items: list[dict],
    on_progress: Callable[[UploadProgress], None] | None = None,
) -> list[dict]:
    """items: [{path: Path, title: str, description: str, tags: list[str]}]"""
    cfg = config.get()
    image_host = registry.active_image_host()
    site = registry.site_host()
    media = storage.load_media()
    added: list[dict] = []

    total = len(items)
    for i, it in enumerate(items):
        src: Path = it["path"]
        name = _safe_name(src.name)
        if on_progress:
            on_progress(UploadProgress(name, i + 1, total, "uploading"))
        try:
            art_local = paths.ART / name
            if src.resolve() != art_local.resolve():
                art_local.write_bytes(src.read_bytes())

            art_up = image_host.upload(art_local, kind="art", dest_name=name)

            if cfg.use_thumbnails:
                thumb_local = images.make_thumbnail(art_local, paths.THUMBS, cfg.thumb_width)
                thumb_up = image_host.upload(thumb_local, kind="thumbnail", dest_name=thumb_local.name)
                thumb_url, thumb_remote = thumb_up.url, thumb_up.remote_id
            else:
                # no thumbnails — point the visitor at the full image
                thumb_url, thumb_remote = art_up.url, art_up.remote_id

            entry = {
                "thumbnailSrc": thumb_url,
                "fullSrc": art_up.url,
                "title": it.get("title", "") or "",
                "description": it.get("description", "") or "",
                "tags": list(it.get("tags", []) or []),
                "host": image_host.id,
                "remoteIds": {"art": art_up.remote_id, "thumbnail": thumb_remote},
            }
            media.append(entry)
            added.append(entry)
            if on_progress:
                on_progress(UploadProgress(name, i + 1, total, "done"))
        except Exception as e:
            if on_progress:
                on_progress(UploadProgress(name, i + 1, total, "error", str(e)))

    storage.save_media(media)
    if added and site.is_configured():
        _push_media_json()
    return added


def delete_art(entry: dict) -> None:
    media = storage.load_media()
    media = [e for e in media if e.get("fullSrc") != entry.get("fullSrc")]
    storage.save_media(media)

    host_id = entry.get("host") or registry.lookup_by_url(entry.get("fullSrc", ""))
    try:
        host = registry.get(host_id)
    except KeyError:
        host = None
    remotes = entry.get("remoteIds") or {}
    if host:
        for key in ("art", "thumbnail"):
            rid = remotes.get(key)
            if rid:
                host.delete(rid)
            elif host_id == "neocities":
                # legacy entries from v1 stored the URL itself as the remote path
                url = entry.get("fullSrc") if key == "art" else entry.get("thumbnailSrc")
                if url and not url.startswith("http"):
                    host.delete(url)

    # local cache cleanup
    for key, folder in (("fullSrc", paths.ART), ("thumbnailSrc", paths.THUMBS)):
        url = entry.get(key, "")
        name = Path(url).name
        if name:
            (folder / name).unlink(missing_ok=True)

    _push_media_json()


def edit_art(original_full_src: str, *, title: str, description: str, tags: list[str]) -> None:
    media = storage.load_media()
    for e in media:
        if e.get("fullSrc") == original_full_src:
            e["title"] = title
            e["description"] = description
            e["tags"] = list(tags)
            break
    storage.save_media(media)
    _push_media_json()


def reorder(new_full_src_order: list[str]) -> None:
    media = storage.load_media()
    by_src = {e.get("fullSrc"): e for e in media}
    ordered = [by_src[s] for s in new_full_src_order if s in by_src]
    # append anything that wasn't in the new order (defensive)
    for e in media:
        if e.get("fullSrc") not in new_full_src_order:
            ordered.append(e)
    storage.save_media(ordered)
    _push_media_json()


def regenerate_thumbnails(on_progress: Callable[[UploadProgress], None] | None = None) -> int:
    cfg = config.get()
    # nothing to do when thumbnails are disabled site-wide
    if not cfg.use_thumbnails:
        return 0
    media = storage.load_media()
    total = len(media)
    done = 0
    for i, entry in enumerate(media):
        host_id = entry.get("host") or registry.lookup_by_url(entry.get("fullSrc", ""))
        try:
            host = registry.get(host_id)
        except KeyError:
            continue
        art_name = Path(entry.get("fullSrc", "")).name
        art_local = paths.ART / art_name
        if not art_local.exists():
            continue
        try:
            if on_progress:
                on_progress(UploadProgress(art_name, i + 1, total, "uploading"))
            thumb_local = images.make_thumbnail(art_local, paths.THUMBS, cfg.thumb_width)
            up = host.upload(thumb_local, kind="thumbnail", dest_name=thumb_local.name)
            entry["thumbnailSrc"] = up.url
            entry.setdefault("remoteIds", {})["thumbnail"] = up.remote_id
            done += 1
            if on_progress:
                on_progress(UploadProgress(art_name, i + 1, total, "done"))
        except Exception as e:
            if on_progress:
                on_progress(UploadProgress(art_name, i + 1, total, "error", str(e)))

    storage.save_media(media)
    _push_media_json()
    return done
