"""
Member 5 — Computer Vision Segmentation.

Removes distracting backgrounds from artisan product photos using rembg
(a lightweight U^2-Net / MobileNet-backed model), so listings look
professional even when photographed against a cluttered rural backdrop.
"""
import io
import logging
import os
from typing import List

from PIL import Image
from rembg import remove, new_session

logger = logging.getLogger("vision_service")

# u2netp is the "portable"/lightweight variant — much smaller than full u2net,
# which matters when this may run on modest server hardware serving 2G clients.
# Session (and its model weights) is created lazily on first use rather than
# at import time, so simply importing this module never triggers a network
# download — important since the whole point of this app is to work offline.
_session = None


def _get_session():
    global _session
    if _session is None:
        _session = new_session("u2netp")
    return _session

CLEAN_BACKGROUND_RGBA = (255, 255, 255, 255)  # flatten transparency onto white for e-commerce


def remove_background(input_path: str, output_path: str) -> str:
    """Removes background from a single image and writes a clean, flattened
    JPEG/WebP suitable for a catalog listing. Returns the output path."""
    with open(input_path, "rb") as f:
        input_bytes = f.read()

    try:
        result_bytes = remove(input_bytes, session=_get_session())
    except Exception as exc:
        logger.error("Background removal failed for %s, using original image: %s", input_path, exc)
        # Fail soft: ship the original photo rather than blocking the listing.
        with open(output_path, "wb") as out:
            out.write(input_bytes)
        return output_path

    cutout = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
    flattened = Image.new("RGBA", cutout.size, CLEAN_BACKGROUND_RGBA)
    flattened.paste(cutout, (0, 0), cutout)
    flattened = flattened.convert("RGB")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    flattened.save(output_path, format="WEBP", quality=85)
    return output_path


def process_product_photos(raw_paths: List[str], product_id: str, media_root: str) -> List[str]:
    """Batch-processes every raw photo for a product. Continues past individual
    failures so one bad photo doesn't block the whole listing."""
    processed = []
    for idx, raw_path in enumerate(raw_paths):
        out_path = os.path.join(media_root, "processed", product_id, f"photo_{idx}.webp")
        try:
            processed.append(remove_background(raw_path, out_path))
        except Exception as exc:
            logger.error("Skipping photo %s due to error: %s", raw_path, exc)
    return processed
