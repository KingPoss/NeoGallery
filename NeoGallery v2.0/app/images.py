from pathlib import Path

from PIL import Image, ImageSequence


def _resize(frame: Image.Image, width: int) -> Image.Image:
    ratio = width / float(frame.size[0])
    height = max(1, int(frame.size[1] * ratio))
    return frame.resize((width, height), Image.LANCZOS)


def make_thumbnail(src: Path, dest_dir: Path, width: int) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"thumbnail_{src.name}"
    with Image.open(src) as img:
        if img.format == "GIF" and getattr(img, "is_animated", False):
            frames = [_resize(f.copy(), width) for f in ImageSequence.Iterator(img)]
            frames[0].save(dest, save_all=True, append_images=frames[1:], loop=0)
        else:
            _resize(img, width).save(dest)
    return dest
