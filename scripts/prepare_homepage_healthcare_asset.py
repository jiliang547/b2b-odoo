"""Encode the approved generated photo for the homepage; no creative image edits."""
import argparse
from pathlib import Path

from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / "custom_addons/b2b_website/static/src/img/homepage/healthcare.webp"
    with Image.open(args.source) as source:
        image = source.convert("RGB")
        image.thumbnail((1000, 1000))
        image.save(target, "WEBP", quality=86, method=6)
    print("Healthcare asset:", target, "bytes:", target.stat().st_size)


if __name__ == "__main__":
    main()
