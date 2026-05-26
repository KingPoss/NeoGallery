from pathlib import Path

import requests

from .. import config
from .base import ImageHost, Kind, UploadResult

API = "https://catbox.moe/user/api.php"


class CatboxHost(ImageHost):
    id = "catbox"
    display_name = "Catbox"

    def is_configured(self) -> bool:
        return True  # anonymous uploads work fine

    def supports(self, kind: Kind) -> bool:
        # catbox only hosts files; site assets (HTML/JSON) must live on the gallery host
        return kind in ("art", "thumbnail", "tag_cover")

    def upload(self, local: Path, *, kind: Kind, dest_name: str | None = None) -> UploadResult:
        data = {"reqtype": "fileupload", "userhash": config.get().catbox.userhash or ""}
        with open(local, "rb") as f:
            r = requests.post(API, data=data, files={"fileToUpload": (dest_name or local.name, f)}, timeout=120)
        r.raise_for_status()
        url = r.text.strip()
        if not url.startswith("http"):
            raise RuntimeError(f"Catbox upload failed: {url}")
        remote_id = url.rsplit("/", 1)[-1]  # filename used by catbox delete API
        return UploadResult(url=url, remote_id=remote_id, host_id=self.id)

    def delete(self, remote_id: str) -> None:
        userhash = config.get().catbox.userhash
        if not userhash:
            # anonymous uploads can't be deleted via the API; just drop the reference
            return
        try:
            r = requests.post(API, data={
                "reqtype": "deletefiles",
                "userhash": userhash,
                "files": remote_id,
            }, timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"[catbox] delete failed for {remote_id}: {e}")
