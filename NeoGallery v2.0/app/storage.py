import json
from pathlib import Path

from . import paths


def _load(path: Path) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _save(data: list, path: Path) -> None:
    paths.ensure_dirs()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_media() -> list[dict]:
    return _load(paths.MEDIA_JSON)


def save_media(items: list[dict]) -> None:
    _save(items, paths.MEDIA_JSON)


def load_tags() -> list[dict]:
    raw = _load(paths.TAGS_JSON)
    # v1 sometimes stored bare strings; normalize
    out = []
    for t in raw:
        if isinstance(t, str):
            out.append({"name": t, "coverPhoto": ""})
        elif isinstance(t, dict) and t.get("name"):
            out.append({
                "name": t["name"],
                "coverPhoto": t.get("coverPhoto", ""),
                "metaDesc": t.get("metaDesc", ""),
                "pageTitle": t.get("pageTitle", t["name"]),
                "linkTitle": t.get("linkTitle", t["name"]),
            })
    return out


def save_tags(tags: list[dict]) -> None:
    _save(tags, paths.TAGS_JSON)


def import_v1_data() -> tuple[int, int]:
    """copy media.json/tag_list.json + assets from the v1 folder, if present.
    returns (media_count, tags_count). idempotent-ish: only runs when v2 is empty."""
    v1 = paths.BASE.parent / "NeoGallery v1.0" / "static" / "assets"
    if not v1.exists():
        return (0, 0)

    if not paths.MEDIA_JSON.exists():
        for name in ("media.json", "allArt.json"):
            src = v1 / "json" / name
            if src.exists():
                save_media(json.loads(src.read_text(encoding="utf-8")))
                break

    if not paths.TAGS_JSON.exists():
        src = v1 / "json" / "tag_list.json"
        if src.exists():
            save_tags(json.loads(src.read_text(encoding="utf-8")))

    # mirror local asset folders so thumbnails/art still resolve
    for sub, dst in (("art", paths.ART), ("thumbnails", paths.THUMBS), ("tag_covers", paths.TAG_COVERS)):
        src_dir = v1 / sub
        if not src_dir.exists():
            continue
        for f in src_dir.iterdir():
            if f.is_file() and not (dst / f.name).exists():
                (dst / f.name).write_bytes(f.read_bytes())

    return (len(load_media()), len(load_tags()))
