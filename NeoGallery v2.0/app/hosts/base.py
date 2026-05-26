from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Kind = Literal["art", "thumbnail", "tag_cover", "json", "html"]


@dataclass
class UploadResult:
    url: str         # goes into media.json / tag HTML
    remote_id: str   # opaque token used for delete()
    host_id: str     # "neocities" / "catbox" / ...


class ImageHost(ABC):
    id: str = ""
    display_name: str = ""

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def supports(self, kind: Kind) -> bool: ...

    @abstractmethod
    def upload(self, local: Path, *, kind: Kind, dest_name: str | None = None) -> UploadResult: ...

    @abstractmethod
    def delete(self, remote_id: str) -> None: ...
