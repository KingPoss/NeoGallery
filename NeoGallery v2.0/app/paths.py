import os
import sys
from pathlib import Path


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(os.getcwd())
    return Path(__file__).resolve().parent.parent


BASE = base_dir()
DATA = BASE / "data"
ASSETS = BASE / "assets"
ART = ASSETS / "art"
THUMBS = ASSETS / "thumbnails"
TAG_COVERS = ASSETS / "tag_covers"
TEMPLATES = BASE / "templates"
CONFIG_FILE = BASE / "config.json"
MEDIA_JSON = DATA / "media.json"
TAGS_JSON = DATA / "tags.json"


def ensure_dirs() -> None:
    for d in (DATA, ASSETS, ART, THUMBS, TAG_COVERS, TEMPLATES):
        d.mkdir(parents=True, exist_ok=True)
