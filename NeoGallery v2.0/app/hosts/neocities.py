from pathlib import Path

import neocities
import requests

from .. import config
from .base import ImageHost, Kind, UploadResult


class NeocitiesHost(ImageHost):
    id = "neocities"
    display_name = "Neocities"

    def __init__(self) -> None:
        self._api = None

    def _client(self):
        # lazy so config edits in the UI take effect without restart
        key = config.get().neocities.api_key
        if not key:
            self._api = None
            return None
        if self._api is None or getattr(self._api, "_api_key", None) != key:
            self._api = neocities.NeoCities(api_key=key)
            self._api._api_key = key
        return self._api

    def is_configured(self) -> bool:
        return bool(config.get().neocities.api_key)

    def supports(self, kind: Kind) -> bool:
        return True  # neocities is the site host, it can take anything

    def _remote_for(self, kind: Kind, name: str) -> str:
        n = config.get().neocities
        if kind == "art":
            return f"{n.art_dir}/{name}"
        if kind == "thumbnail":
            return f"{n.thumb_dir}/{name}"
        if kind == "tag_cover":
            return f"{n.thumb_dir}/tag_covers/{name}"
        if kind == "json":
            return f"{n.json_dir}/{name}"
        if kind == "html":
            prefix = n.tag_dir if name.endswith(".html") and name != config.get().art_html_name else n.gallery_dir
            return f"{prefix}/{name}" if prefix else name
        return name

    def upload(self, local: Path, *, kind: Kind, dest_name: str | None = None) -> UploadResult:
        client = self._client()
        if client is None:
            raise RuntimeError("Neocities API key not configured")
        remote = self._remote_for(kind, dest_name or local.name)
        try:
            client.upload((str(local), remote))
        except requests.HTTPError as e:
            raise RuntimeError(f"Neocities upload failed: {e}") from e
        # NeoGallery.html lives inside gallery_dir; visitor-facing URLs in media/tag JSON
        # need to be relative to it, otherwise the browser doubles the prefix
        gallery = (config.get().neocities.gallery_dir or "").strip("/")
        visitor = remote
        if gallery and visitor.startswith(gallery + "/"):
            visitor = visitor[len(gallery) + 1:]
        return UploadResult(url=visitor, remote_id=remote, host_id=self.id)

    def delete(self, remote_id: str) -> None:
        client = self._client()
        if client is None:
            return
        try:
            client.delete(remote_id)
        except requests.HTTPError as e:
            # log and move on; don't blow up the UI for a missing remote file
            print(f"[neocities] delete failed for {remote_id}: {e}")
