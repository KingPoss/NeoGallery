import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import paths


@dataclass
class NeocitiesConfig:
    api_key: str = ""
    # everything lives under /NG/ so we don't trample folders the user already has
    art_dir: str = "NeoGallery/assets/media"
    thumb_dir: str = "NeoGallery/assets/thumbnails"
    json_dir: str = "NeoGallery/json"
    tag_dir: str = "NeoGallery"
    gallery_dir: str = "NeoGallery"


@dataclass
class CatboxConfig:
    # leave blank for anonymous uploads
    userhash: str = ""


@dataclass
class AppConfig:
    active_image_host: str = "neocities"
    thumb_width: int = 150
    per_page: int = 20
    dark_mode: bool = False
    media_json_name: str = "media.json"
    tag_list_json_name: str = "tags.json"
    art_html_name: str = "NeoGallery.html"
    show_in_random: str = "all"
    onboarding_completed: bool = False
    # visitor-side gallery options
    use_thumbnails: bool = True
    full_image_display_width: int = 400          # used when use_thumbnails is False
    loading_image: str = "assets/loaders/hourglass.gif"   # relative to gallery_dir; "" disables
    show_loader: bool = True
    # snapshot of gallery settings as of the last successful republish, used to
    # show a "pending changes" indicator in the settings UI
    last_applied_gallery_state: dict = field(default_factory=dict)
    neocities: NeocitiesConfig = field(default_factory=NeocitiesConfig)
    catbox: CatboxConfig = field(default_factory=CatboxConfig)


def _from_dict(d: dict) -> AppConfig:
    def _filter(cls, raw):
        return {k: v for k, v in (raw or {}).items() if k in cls.__dataclass_fields__}
    neo = NeocitiesConfig(**_filter(NeocitiesConfig, d.pop("neocities", {})))
    cat = CatboxConfig(**_filter(CatboxConfig, d.pop("catbox", {})))
    cfg = AppConfig(**_filter(AppConfig, d))
    cfg.neocities = neo
    cfg.catbox = cat
    return cfg


def load() -> AppConfig:
    paths.ensure_dirs()
    if paths.CONFIG_FILE.exists():
        try:
            return _from_dict(json.loads(paths.CONFIG_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError):
            pass
    cfg = _maybe_migrate_from_v1() or AppConfig()
    save(cfg)
    return cfg


def save(cfg: AppConfig) -> None:
    paths.CONFIG_FILE.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")


def _maybe_migrate_from_v1() -> AppConfig | None:
    # only pull the API key -- v2 owns dirs/filenames now, we don't want stale v1 paths
    # leaking back in every time config.json is reset
    env = Path(paths.BASE).parent / "NeoGallery v1.0" / ".env"
    if not env.exists():
        return None
    api_key = ""
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("NEOCITIES_API_KEY="):
            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
    if not api_key:
        return None
    cfg = AppConfig()
    cfg.neocities.api_key = api_key
    return cfg


_cache: AppConfig | None = None


def get() -> AppConfig:
    global _cache
    if _cache is None:
        _cache = load()
    return _cache


def commit() -> None:
    if _cache is not None:
        save(_cache)
