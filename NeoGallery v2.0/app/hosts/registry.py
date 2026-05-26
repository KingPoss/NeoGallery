from .. import config
from .base import ImageHost
from .catbox import CatboxHost
from .neocities import NeocitiesHost

_neocities = NeocitiesHost()
_catbox = CatboxHost()

_all: dict[str, ImageHost] = {
    _neocities.id: _neocities,
    _catbox.id: _catbox,
}


def all_hosts() -> list[ImageHost]:
    return list(_all.values())


def get(host_id: str) -> ImageHost:
    if host_id not in _all:
        raise KeyError(f"Unknown host: {host_id}")
    return _all[host_id]


def active_image_host() -> ImageHost:
    return get(config.get().active_image_host)


def site_host() -> NeocitiesHost:
    # the gallery itself lives on neocities; HTML/JSON always go here
    return _neocities


def lookup_by_url(url: str) -> str:
    if "catbox.moe" in url:
        return "catbox"
    return "neocities"
