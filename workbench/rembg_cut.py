#!/usr/bin/env python3
"""Cut raw sticker images to transparent PNGs with rembg U2Net.

Usage (run with the rembg venv python):
    tools/rembg_venv/bin/python workbench/rembg_cut.py <raw_dir> <out_dir>

Every raw_XX.png (or *.png) in <raw_dir> becomes sticker_XX.png in <out_dir>.
Same cut the pipeline uses (U2Net, local, free); white subjects survive because
it is AI segmentation, not a white flood fill. Exits non-zero when any input
fails to cut or produces an empty image, so the caller never renders with a
missing sticker.
"""
import sys
from pathlib import Path


def main():
    raw_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    from rembg import remove, new_session
    from PIL import Image

    session = new_session("u2net")
    files = sorted(raw_dir.glob("*.png"))
    if not files:
        print("rembg_cut: no PNGs in %s" % raw_dir, file=sys.stderr)
        return 1
    for src in files:
        dest = out_dir / ("sticker_%s.png" % src.stem.split("_")[-1])
        im = Image.open(src).convert("RGB")
        cut = remove(im, session=session)
        cut.save(dest)
        alpha = cut.convert("RGBA").split()[3]
        opaque = sum(1 for a in alpha.getdata() if a > 10)
        if opaque == 0:
            print("rembg_cut: %s cut to an empty image" % src.name, file=sys.stderr)
            return 1
        print("rembg_cut: %s -> %s (%d opaque px)" % (src.name, dest.name, opaque))
    return 0


if __name__ == "__main__":
    sys.exit(main())
