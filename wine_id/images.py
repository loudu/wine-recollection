import base64
import io
from pathlib import Path

from PIL import Image, ImageOps

# Larger images are downscaled by the API anyway; resizing locally saves upload time.
MAX_EDGE = 1568


def load_image_block(path: str | Path) -> dict:
    """Return a base64 image content block, EXIF-rotated, resized and JPEG-encoded."""
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((MAX_EDGE, MAX_EDGE))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.standard_b64encode(buf.getvalue()).decode("ascii"),
        },
    }


def image_blocks(paths: list[str | Path]) -> list[dict]:
    blocks: list[dict] = []
    for i, path in enumerate(paths, start=1):
        blocks.append({"type": "text", "text": f"Photo {i} ({Path(path).name}):"})
        blocks.append(load_image_block(path))
    return blocks
