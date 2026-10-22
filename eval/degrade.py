"""Damage clean label photos to build test cases with a known answer.

    python eval/degrade.py photo_propre.jpg --out eval/dataset/photos --variants 3

Each variant combines a few random damages: water stains, tears, fading,
mould spots, blur. Use a fixed --seed to make the dataset reproducible.
"""

import argparse
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


def water_stain(img: Image.Image, rng: random.Random) -> Image.Image:
    """Water washes the ink out inside the stain and leaves a brown tide line at its edge."""
    w, h = img.size
    cx, cy = rng.uniform(0.1, 0.9) * w, rng.uniform(0.1, 0.9) * h
    r = rng.uniform(0.15, 0.35) * min(w, h)
    pts = [(cx + r * rng.uniform(0.75, 1.15) * math.cos(a), cy + r * rng.uniform(0.75, 1.15) * math.sin(a))
           for a in (2 * math.pi * i / 24 for i in range(24))]

    inside = Image.new("L", img.size, 0)
    ImageDraw.Draw(inside).polygon(pts, fill=int(rng.uniform(170, 235)))
    inside = inside.filter(ImageFilter.GaussianBlur(r * 0.06))
    stained_paper = Image.new("RGB", img.size, (205, 180, 135))
    img = Image.composite(stained_paper, img, inside)

    rim = Image.new("L", img.size, 0)
    ImageDraw.Draw(rim).line([*pts, pts[0]], fill=200, width=max(2, int(r * 0.04)))
    rim = rim.filter(ImageFilter.GaussianBlur(r * 0.02))
    return Image.composite(Image.new("RGB", img.size, (120, 80, 40)), img, rim)


def tear(img: Image.Image, rng: random.Random) -> Image.Image:
    """Remove a ragged piece of label, revealing glass-coloured background."""
    w, h = img.size
    img = img.copy()
    draw = ImageDraw.Draw(img)
    edge = rng.choice(["top", "bottom", "left", "right"])
    depth = rng.uniform(0.15, 0.45)
    span = rng.uniform(0.3, 0.7)
    start = rng.uniform(0, 1 - span)
    steps = 14
    pts = []
    for i in range(steps + 1):
        t = start + span * i / steps
        d = depth * rng.uniform(0.3, 1.0) if 0 < i < steps else 0
        if edge == "top":
            pts.append((t * w, d * h))
        elif edge == "bottom":
            pts.append((t * w, h - d * h))
        elif edge == "left":
            pts.append((d * w, t * h))
        else:
            pts.append((w - d * w, t * h))
    glass = (rng.randint(20, 50), rng.randint(40, 70), rng.randint(20, 40))
    draw.polygon(pts, fill=glass)
    return img


def fade(img: Image.Image, rng: random.Random) -> Image.Image:
    img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.35, 0.65))
    img = ImageEnhance.Color(img).enhance(rng.uniform(0.3, 0.7))
    tint = Image.new("RGB", img.size, (230, 210, 160))
    return Image.blend(img, tint, rng.uniform(0.15, 0.35))


def mould(img: Image.Image, rng: random.Random) -> Image.Image:
    w, h = img.size
    img = img.copy()
    draw = ImageDraw.Draw(img)
    cx, cy = rng.uniform(0, w), rng.uniform(0, h)
    spread = rng.uniform(0.1, 0.25) * min(w, h)
    for _ in range(rng.randint(150, 400)):
        x, y = rng.gauss(cx, spread), rng.gauss(cy, spread)
        r = rng.uniform(1, 0.012 * min(w, h))
        shade = rng.randint(30, 90)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(shade, shade + 10, shade))
    return img


def blur(img: Image.Image, rng: random.Random) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(rng.uniform(1.0, 2.5)))


DAMAGES = {"stain": water_stain, "tear": tear, "fade": fade, "mould": mould, "blur": blur}


def degrade(img: Image.Image, rng: random.Random, n_damages: int) -> tuple[Image.Image, list[str]]:
    names = rng.sample(sorted(DAMAGES), k=min(n_damages, len(DAMAGES)))
    for name in names:
        img = DAMAGES[name](img, rng)
    return img, names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=Path("eval/dataset/photos"))
    parser.add_argument("--variants", type=int, default=3)
    parser.add_argument("--damages", type=int, default=2, help="Nombre de dégâts combinés par variante.")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    for path in args.images:
        with Image.open(path) as src:
            clean = src.convert("RGB")
        for v in range(1, args.variants + 1):
            damaged, names = degrade(clean, rng, args.damages)
            target = args.out / f"{path.stem}_abime{v}.jpg"
            damaged.save(target, quality=90)
            print(f"{target}  ({', '.join(names)})")


if __name__ == "__main__":
    main()
