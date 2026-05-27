import re
from pathlib import Path

from . import config, images, paths, storage
from .hosts import registry

# built-in tags that don't get a real tag page (visitor JS handles them client-side)
SYSTEM_TAGS = {"random"}


def _bundled_templates() -> Path:
    return paths.BASE / "site_template"


def _template(name: str) -> Path:
    # cached templates/ copy wins, else fall through to the bundled set.
    # v1's templates use absolute /css paths that break on nested/custom-domain installs.
    v2 = paths.TEMPLATES / name
    if v2.exists():
        return v2
    src = _bundled_templates() / name
    if src.exists():
        v2.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return v2


def _tag_path(filename: str) -> str:
    n = config.get().neocities
    return f"{n.tag_dir}/{filename}" if n.tag_dir else filename


def _section_snippet(tag_name: str, link_title: str) -> str:
    # mirror v1's default snippet; gives a clickable row on art.html
    n = config.get().neocities
    tag_dir = n.tag_dir or ""
    prefix = f"{tag_dir}/" if tag_dir else ""
    return (
        f'<tr><td>\n'
        f'<a href="/{prefix}{tag_name}.html"><p class="headers">{link_title}</p></a>\n'
        f'</td></tr>'
    )


def _process_cover(tag_name: str, src_path: Path) -> str:
    cfg = config.get()
    safe = "".join(c for c in src_path.name if c.isalnum() or c in "._-") or "cover"
    final_name = f"cover_{tag_name}_{safe}"
    # thumbnail the cover so it's web-sized
    tmp = paths.TAG_COVERS / f".tmp_{final_name}"
    tmp.write_bytes(src_path.read_bytes())
    thumb = images.make_thumbnail(tmp, paths.TAG_COVERS, cfg.thumb_width)
    final = paths.TAG_COVERS / final_name
    if final.exists():
        final.unlink()
    thumb.rename(final)
    tmp.unlink(missing_ok=True)
    return final_name


def _upload_cover(final_name: str) -> str:
    site = registry.site_host()
    res = site.upload(paths.TAG_COVERS / final_name, kind="tag_cover", dest_name=final_name)
    return res.url


def gallery_loader_html() -> str:
    cfg = config.get()
    if not cfg.show_loader or not cfg.loading_image:
        return ""
    return (
        '    <div class="galleryLoader">\n'
        '        <div>\n'
        f'        <img src="{cfg.loading_image}" alt="Loading...">\n'
        '        <p>Loading...</p>\n'
        '        </div>\n'
        '    </div>'
    )


def modal_loader_html() -> str:
    cfg = config.get()
    if not cfg.show_loader or not cfg.loading_image:
        return ""
    return f'    <img id="loadingPlaceholder" class="loading" src="{cfg.loading_image}">'


_GALLERY_LOADER_RE = re.compile(r'<div\s+class="galleryLoader"[\s\S]*?</div>\s*</div>', re.IGNORECASE)
_MODAL_LOADER_RE = re.compile(r'<img[^>]*\bid="loadingPlaceholder"[^>]*>(?:\s*</img>)?', re.IGNORECASE)


def _render_for_upload(local: Path) -> Path:
    """render loader substitutions into a tempfile so the cached copy stays as authored."""
    import tempfile
    text = local.read_text(encoding="utf-8")
    rendered = apply_loader_substitutions(text)
    if rendered == text:
        return local
    tmp = Path(tempfile.gettempdir()) / f"_ng_push_{local.name}"
    tmp.write_text(rendered, encoding="utf-8")
    return tmp


def apply_loader_substitutions(text: str) -> str:
    # runs on raw templates and on already-rendered pages we re-push with a fresh loader
    g = gallery_loader_html()
    m = modal_loader_html()
    text = _GALLERY_LOADER_RE.sub(lambda _: g, text)
    text = _MODAL_LOADER_RE.sub(lambda _: m, text)
    text = text.replace("__GALLERY_LOADER__", g)
    text = text.replace("__MODAL_LOADER__", m)
    return text


def _render_tag_html(tag: dict, cover_url: str) -> str:
    template = _template("tagTemplate.html")
    if not template.exists():
        # bare fallback if v1 template wasn't available
        return (
            f'<!DOCTYPE html><html><head>'
            f'<meta name="description" content="{tag.get("metaDesc","")}">'
            f'<title>{tag.get("pageTitle", tag["name"])}</title></head>'
            f'<body><div class="gallery" data-tag="{tag["name"]}"></div></body></html>'
        )
    text = template.read_text(encoding="utf-8")
    rendered = (
        text
        .replace("__DATA_TAG__", tag["name"])
        .replace("__META_DESC__", tag.get("metaDesc", ""))
        .replace("__PAGE_TITLE__", tag.get("pageTitle", tag["name"]))
        .replace("__COVER_PHOTO__", cover_url)
        .replace("__NEOCITIES_GALLERY_DIR__", config.get().neocities.gallery_dir or "")
        .replace("__GALLERY_PAGE__", config.get().art_html_name)
    )
    return apply_loader_substitutions(rendered)


def _append_section_to_art(tag_name: str, link_title: str) -> None:
    art = _template(config.get().art_html_name)
    if not art.exists():
        return
    content = art.read_text(encoding="utf-8")
    last_end = content.rfind("<!--END-->")
    insert_at = last_end + len("<!--END-->") if last_end != -1 else len(content)
    block = f"\n<!--{tag_name}-->\n{_section_snippet(tag_name, link_title)}\n<!--END-->\n"
    art.write_text(content[:insert_at] + block + content[insert_at:], encoding="utf-8")


def _remove_section_from_art(tag_name: str) -> None:
    art = _template(config.get().art_html_name)
    if not art.exists():
        return
    content = art.read_text(encoding="utf-8")
    pattern = rf'\n?<!--{re.escape(tag_name)}-->.*?<!--END-->\n?'
    new_content = re.sub(pattern, "", content, flags=re.DOTALL)
    art.write_text(new_content, encoding="utf-8")


def _replace_section_in_art(old: str, new: str, link_title: str) -> None:
    art = _template(config.get().art_html_name)
    if not art.exists():
        return
    content = art.read_text(encoding="utf-8")
    block = f"<!--{new}-->\n{_section_snippet(new, link_title)}\n<!--END-->"
    pattern = rf'<!--{re.escape(old)}-->.*?<!--END-->'
    art.write_text(re.sub(pattern, block, content, flags=re.DOTALL), encoding="utf-8")


def _push_site_files(extra: list[tuple[Path, str, str]] = None) -> None:
    site = registry.site_host()
    if not site.is_configured():
        return
    art = _template(config.get().art_html_name)
    if art.exists():
        site.upload(_render_for_upload(art), kind="html", dest_name=config.get().art_html_name)
    site.upload(paths.TAGS_JSON, kind="json", dest_name=config.get().tag_list_json_name)
    for local, kind, dest_name in (extra or []):
        if local.exists():
            site.upload(local, kind=kind, dest_name=dest_name)


def create_tag(name: str, meta_desc: str, page_title: str, link_title: str, cover_src: Path | None) -> dict:
    tags = storage.load_tags()
    if any(t["name"] == name for t in tags):
        raise ValueError(f"Tag '{name}' already exists")

    # system tags like 'random' don't get a tag page, navigation entry, or cover photo
    if name in SYSTEM_TAGS:
        tag = {"name": name}
        tags.append(tag)
        storage.save_tags(tags)
        site = registry.site_host()
        if site.is_configured():
            site.upload(paths.TAGS_JSON, kind="json", dest_name=config.get().tag_list_json_name)
        return tag

    cover_url = ""
    cover_local_name = ""
    if cover_src and cover_src.exists():
        cover_local_name = _process_cover(name, cover_src)
        cover_url = _upload_cover(cover_local_name)

    tag = {
        "name": name,
        "coverPhoto": cover_url,
        "metaDesc": meta_desc,
        "pageTitle": page_title,
        "linkTitle": link_title,
    }
    tags.append(tag)
    storage.save_tags(tags)

    html = _render_tag_html(tag, cover_url)
    tag_page = paths.TEMPLATES / f"{name}.html"
    tag_page.write_text(html, encoding="utf-8")
    _append_section_to_art(name, link_title)
    _push_site_files(extra=[(tag_page, "html", f"{name}.html")])
    return tag


def edit_tag(old_name: str, *, new_name: str, meta_desc: str, page_title: str, link_title: str, cover_src: Path | None) -> dict:
    tags = storage.load_tags()
    idx = next((i for i, t in enumerate(tags) if t["name"] == old_name), -1)
    if idx == -1:
        raise KeyError(f"Tag '{old_name}' not found")
    if new_name != old_name and any(t["name"] == new_name for t in tags):
        raise ValueError(f"Tag '{new_name}' already exists")

    existing = tags[idx]
    cover_url = existing.get("coverPhoto", "")
    if cover_src and cover_src.exists():
        if existing.get("coverPhoto"):
            old_cover = paths.TAG_COVERS / Path(existing["coverPhoto"]).name
            old_cover.unlink(missing_ok=True)
        cover_local_name = _process_cover(new_name, cover_src)
        cover_url = _upload_cover(cover_local_name)

    tag = {
        "name": new_name,
        "coverPhoto": cover_url,
        "metaDesc": meta_desc,
        "pageTitle": page_title,
        "linkTitle": link_title,
    }
    tags[idx] = tag
    storage.save_tags(tags)

    # rename tag html file if renamed
    old_html = paths.TEMPLATES / f"{old_name}.html"
    new_html = paths.TEMPLATES / f"{new_name}.html"
    if old_name != new_name and old_html.exists():
        old_html.unlink()
    new_html.write_text(_render_tag_html(tag, cover_url), encoding="utf-8")
    _replace_section_in_art(old_name, new_name, link_title)

    # rename tag inside every art entry
    if old_name != new_name:
        media = storage.load_media()
        for e in media:
            if old_name in e.get("tags", []):
                e["tags"] = [new_name if t == old_name else t for t in e["tags"]]
        storage.save_media(media)

    _push_site_files(extra=[(new_html, "html", f"{new_name}.html")])

    # clean up old remote tag page + push fresh media.json if renamed
    site = registry.site_host()
    if old_name != new_name and site.is_configured():
        site.delete(_tag_path(f"{old_name}.html"))
        site.upload(paths.MEDIA_JSON, kind="json", dest_name=config.get().media_json_name)
    return tag


def delete_tag(name: str) -> None:
    tags = storage.load_tags()
    target = next((t for t in tags if t["name"] == name), None)
    if not target:
        raise KeyError(f"Tag '{name}' not found")

    tags = [t for t in tags if t["name"] != name]
    storage.save_tags(tags)

    # strip the tag from every post regardless of system/regular
    media = storage.load_media()
    for e in media:
        if name in e.get("tags", []):
            e["tags"] = [t for t in e["tags"] if t != name]
    storage.save_media(media)

    site = registry.site_host()

    if name in SYSTEM_TAGS:
        # no HTML, no nav entry, no cover -- just push the updated JSON files
        if site.is_configured():
            site.upload(paths.TAGS_JSON, kind="json", dest_name=config.get().tag_list_json_name)
            site.upload(paths.MEDIA_JSON, kind="json", dest_name=config.get().media_json_name)
        return

    local_page = paths.TEMPLATES / f"{name}.html"
    local_page.unlink(missing_ok=True)
    if target.get("coverPhoto"):
        (paths.TAG_COVERS / Path(target["coverPhoto"]).name).unlink(missing_ok=True)

    _remove_section_from_art(name)

    _push_site_files()
    if site.is_configured():
        site.delete(_tag_path(f"{name}.html"))
        if target.get("coverPhoto"):
            site.delete(target["coverPhoto"])
        site.upload(paths.MEDIA_JSON, kind="json", dest_name=config.get().media_json_name)
