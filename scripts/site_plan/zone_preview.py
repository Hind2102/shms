"""Render the reporting zones of shms/config/site_zones.json over the site image, for the owner's review.

    python scripts/site_plan/zone_preview.py docs/screenshots/v170_zone_preview.png

Every zone is drawn with its code and listed in a legend below the image. Roads are outside all zones.
"""

from __future__ import annotations

import sys

from PIL import Image, ImageDraw, ImageFont

from shms import site_layout
from shms.settings import PACKAGE_DIR

PALETTE = [
    (230, 25, 75),
    (60, 180, 75),
    (0, 130, 200),
    (245, 130, 48),
    (145, 30, 180),
    (0, 170, 170),
    (240, 50, 230),
    (150, 190, 0),
    (255, 105, 150),
    (0, 128, 128),
    (170, 110, 40),
    (128, 0, 0),
    (0, 0, 128),
    (128, 128, 0),
    (90, 90, 200),
    (220, 180, 0),
]


def font(size: int):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def main(out: str) -> None:
    im = Image.open(PACKAGE_DIR / "static" / "site_map" / "al_taweelah_map.webp").convert("RGBA")
    w, h = im.size
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    zones = list(site_layout.REPORTING.values())
    for z, col in zip(zones, PALETTE, strict=False):
        d.polygon(z.points, fill=col + (60,), outline=col + (255,), width=4)
        cx, cy = z.centre
        bb = d.textbbox((cx, cy), z.code, font=font(20), anchor="mm")
        d.rectangle(
            (bb[0] - 5, bb[1] - 4, bb[2] + 5, bb[3] + 4), fill=(255, 255, 255, 240), outline=col + (255,), width=3
        )
        d.text((cx, cy), z.code, font=font(20), fill=(0, 0, 0, 255), anchor="mm")
    rows = -(-len(zones) // 3)
    canvas = Image.new("RGB", (w, h + 60 + rows * 36 + 30), "white")
    canvas.paste(Image.alpha_composite(im, layer).convert("RGB"), (0, 0))
    d2 = ImageDraw.Draw(canvas)
    d2.text(
        (20, h + 12),
        f"{len(zones)} reporting zones on the Al Taweelah illustrative image (approved 2026-11-27; "
        "polygons in image pixels)",
        font=font(20),
        fill=(0, 0, 0),
    )
    for i, (z, col) in enumerate(zip(zones, PALETTE, strict=False)):
        x, y = 20 + (i // rows) * (w // 3), h + 50 + (i % rows) * 36
        d2.rectangle((x, y, x + 26, y + 26), fill=col, outline=(0, 0, 0))
        d2.text((x + 36, y + 2), f"{z.code}  {z.name}", font=font(18), fill=(0, 0, 0))
    d2.text(
        (20, canvas.height - 26),
        "Roads are outside all zones. Illustrative concept image – not a verified site plot plan.",
        font=font(16),
        fill=(60, 60, 60),
    )
    canvas.save(out)
    print(out, canvas.size)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots/v170_zone_preview.png")
