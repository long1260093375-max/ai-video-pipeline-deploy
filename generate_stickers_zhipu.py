#!/usr/bin/env python3
"""Generate cartoon cutout stickers with Zhipu (智谱) image API, no VPN needed.

Default model is cogview-3-flash, which Zhipu lists as a free image model.
Upgrade with --model cogview-4 (0.06 yuan/call, official price) if the free
model's style/consistency is not good enough.

How it works (one call per sticker, not one sheet):
  1. Read a prompts JSON file: [{"key": "票都买了", "prompt": "..."}, ...]
  2. POST https://open.bigmodel.cn/api/paas/v4/images/generations
     with {"model": ..., "prompt": ..., "size": "1024x1024"}
  3. Download data[0].url immediately (URLs expire) to cutouts/zhipu_raw/
  4. Remove the pure-white background (flood fill from the edges) and drop
     isolated fragments, saving a transparent PNG per sticker to
     cutouts/stickers_zhipu/sticker_XX.png — the same naming the v6 render
     script expects, so you can point STICKER_DIR at it or copy it over
     cutouts/stickers/ once you like the result.

API key:
  Never paste the key into chat or into this file. Set it on the machine
  that runs the pipeline and the script reads it from the environment:
      export ZHIPU_API_KEY="your-key-here"   # from bigmodel.cn console -> API Keys
  On Windows (run.bat style):  set ZHIPU_API_KEY=your-key-here

Test with one sticker first before a full episode:
      python3 generate_stickers_zhipu.py --prompts cutouts/prompts_chenmo.json --only 2
      python3 generate_stickers_zhipu.py --prompts cutouts/prompts_chenmo.json --dry-run
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
API_URL = "https://open.bigmodel.cn/api/paas/v4/images/generations"
# Style presets (2026-11-04): the user does NOT have to supply a style.
# Pick one with --style; the default stays the approved cute-flat look.
# Every preset keeps "single subject, white background, no text, no border"
# so the white-background cut step still produces a clean transparent PNG.
STYLES = {
    "cute_flat": ("Cute flat cartoon sticker, thick clean outline, soft pastel colors, "
                  "single subject centered, on a pure white background, no text, no words, "
                  "no border, no shadow, no other objects."),
    "minimal_icon": ("Minimal flat vector icon, clean geometric shapes, bold solid colors, "
                     "simple and modern, single subject centered, on a pure white background, "
                     "no text, no words, no border, no shadow, no other objects."),
    "clay_3d": ("Soft 3D clay render sticker, rounded matte clay shapes, gentle pastel colors, "
                "cute and tactile, single subject centered, on a pure white background, "
                "no text, no words, no border, no shadow, no other objects."),
    "watercolor": ("Soft watercolor illustration, light color washes, gentle hand-painted edges, "
                   "single subject centered, on a pure white background, "
                   "no text, no words, no border, no shadow, no other objects."),
}
STYLE = STYLES["cute_flat"]

def fail(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)

def call_zhipu(api_key, prompt, model, size, retries=2):
    body = json.dumps({"model": model, "prompt": prompt, "size": size}).encode("utf-8")
    last_err = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            API_URL, data=body,
            headers={"Authorization": "Bearer " + api_key,
                     "Content-Type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            url = data["data"][0]["url"]
            return url
        except Exception as e:  # noqa: BLE001 - report and retry once
            last_err = e
            print("  attempt %d failed: %s" % (attempt + 1, e))
            if attempt < retries:
                time.sleep(5)
    fail("Zhipu API call failed after %d attempts: %s" % (retries + 1, last_err))

def download(url, dest):
    urllib.request.urlretrieve(url, str(dest))
    return dest

def cut_white_background(src_path, dest_path):
    """Flood-fill near-white from the edges, then drop isolated fragments."""
    from PIL import Image
    import numpy as np
    im = Image.open(src_path).convert("RGBA")
    arr = np.array(im)
    h, w = arr.shape[:2]
    # Near-white pixels are background candidates.
    white = (arr[:, :, 0] > 235) & (arr[:, :, 1] > 235) & (arr[:, :, 2] > 235)
    # Flood fill from the border through white pixels only.
    from collections import deque
    bg = np.zeros((h, w), dtype=bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if white[y, x] and not bg[y, x]:
                bg[y, x] = True; q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if white[y, x] and not bg[y, x]:
                bg[y, x] = True; q.append((y, x))
    while q:
        y, x = q.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and white[ny, nx] and not bg[ny, nx]:
                bg[ny, nx] = True; q.append((ny, nx))
    alpha = arr[:, :, 3].copy()
    alpha[bg] = 0
    # Drop isolated fragments (keeps the main subject + close details).
    try:
        from scipy import ndimage
        mask = alpha > 10
        labels, n = ndimage.label(mask)
        if n > 1:
            sizes = ndimage.sum(mask, labels, range(1, n + 1))
            largest = int(np.argmax(sizes)) + 1
            dilated = ndimage.binary_dilation(labels == largest, iterations=12)
            keep = labels == largest
            for i, sz in enumerate(sizes, start=1):
                if i != largest and sz > 0.02 * sizes[largest - 1] and np.any(dilated & (labels == i)):
                    keep |= (labels == i)
            alpha[~keep] = 0
    except ImportError:
        pass  # scipy is optional; flood fill alone already removes the white bg
    arr[:, :, 3] = alpha
    # Crop to content with a small margin.
    ys, xs = np.where(alpha > 10)
    if len(xs):
        y0, y1 = max(0, ys.min() - 8), min(h, ys.max() + 9)
        x0, x1 = max(0, xs.min() - 8), min(w, xs.max() + 9)
        arr = arr[y0:y1, x0:x1]
    Image.fromarray(arr, "RGBA").save(dest_path)
    return dest_path

def main():
    ap = argparse.ArgumentParser(description="Generate stickers via Zhipu API")
    ap.add_argument("--prompts", default=str(BASE / "cutouts" / "prompts_chenmo.json"))
    ap.add_argument("--model", default="cogview-3-flash",
                    help="cogview-3-flash (free) or cogview-4 (0.06 yuan/call)")
    ap.add_argument("--size", default="1024x1024")
    ap.add_argument("--out-dir", default=str(BASE / "cutouts" / "stickers_zhipu"))
    ap.add_argument("--raw-dir", default=str(BASE / "cutouts" / "zhipu_raw"))
    ap.add_argument("--only", type=int, default=None, help="generate only this index (0-based)")
    ap.add_argument("--dry-run", action="store_true", help="print prompts, call nothing")
    ap.add_argument("--style", default="cute_flat", choices=list(STYLES),
                    help="sticker style preset (default: cute_flat)")
    ap.add_argument("--template", default="", help="style template under templates/ (overrides --style with the template's image_style)")
    args = ap.parse_args()
    global STYLE
    if args.template:
        from template import load_template
        STYLE = load_template(args.template)["image_style"]
    else:
        STYLE = STYLES[args.style]

    prompts = json.loads(Path(args.prompts).read_text(encoding="utf-8"))
    if args.only is not None:
        prompts = [prompts[args.only]]
        start = args.only
    else:
        start = 0
    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = Path(args.raw_dir); raw_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        for i, p in enumerate(prompts, start=start):
            print("%02d %s :: %s" % (i, p["key"], STYLE + " " + p["prompt"]))
        return

    api_key = os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        fail("ZHIPU_API_KEY is not set. Get a key at bigmodel.cn console -> API Keys, "
             "then: export ZHIPU_API_KEY=\"your-key\"  (do not paste it into chat)")
    for i, p in enumerate(prompts, start=start):
        full_prompt = STYLE + " " + p["prompt"]
        print("[%02d] %s ..." % (i, p["key"]))
        url = call_zhipu(api_key, full_prompt, args.model, args.size)
        raw = raw_dir / ("raw_%02d.png" % i)
        download(url, raw)
        dest = out_dir / ("sticker_%02d.png" % i)
        cut_white_background(raw, dest)
        print("     -> %s" % dest)
    print("Done: %d stickers in %s (raw images in %s)" % (len(prompts), out_dir, raw_dir))

if __name__ == "__main__":
    main()
