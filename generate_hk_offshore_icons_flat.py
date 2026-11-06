#!/usr/bin/env python3
"""Generate 7 HK offshore MG icons, unified flat style, Seedream 5.0 Pro.
New dirs, old files untouched. Stops on 429/404. Usage: python3 ... [--only 00]"""
import json, os, subprocess, sys, time, urllib.request, argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent
RAW = BASE / "cutouts" / "hk_offshore_mg_flat_raw"
RAW.mkdir(parents=True, exist_ok=True)
MODEL = "doubao-seedream-5-0-pro-260628"
STYLE = "flat 2D vector illustration, thick clean outlines, solid flat colors only, no gradients, no shadows, no 3D rendering, no photorealism, no realistic textures, minimalist MG animation style, consistent color palette of deep navy blue, teal, warm mustard yellow and soft coral, pure white background, no words, no watermark, single subject filling most of the frame"
PROMPTS = [
    ("00", "A cheerful foreign businessman in a dark suit holding a small globe"),
    ("01", "A modern office tower building with a small purple bauhinia flower emblem near the top"),
    ("02", "A modern factory building with chimneys and one large gear beside it"),
    ("03", "A classic bank building with columns and one large gold coin with a dollar symbol in front"),
    ("04", "A paper document sheet with a large green checkmark tick and a pen beside it"),
    ("05", "A large red shipping container box on a cargo ship"),
    ("06", "An official paper document with a round red approval stamp and one large golden circular badge showing the single letter S"),
]
ap = argparse.ArgumentParser()
ap.add_argument("--only", default="")
a = ap.parse_args()
ok = 0
for idx, subj in PROMPTS:
    if a.only and idx != a.only:
        continue
    prompt = f"{subj}, {STYLE}"
    out = RAW / f"raw_{idx}.png"
    if out.exists() and out.stat().st_size > 50000 and not a.only:
        print(f"{idx} SKIP already exists {out.stat().st_size} bytes", flush=True)
        ok += 1
        continue
    body = json.dumps({"model": MODEL, "prompt": prompt, "size": "1024x1024",
                       "response_format": "url", "watermark": False}).encode()
    req = urllib.request.Request("https://ark.cn-beijing.volces.com/api/v3/images/generations",
                                 data=body, headers={"Content-Type": "application/json"}, method="POST")
    _key = os.environ.get("ARK_API_KEY", "")
    if not _key:
        print("ARK_API_KEY is not set. Get a key at the Volcano Ark console, then: export ARK_API_KEY=<key>", file=sys.stderr)
        sys.exit(2)
    req.add_header("Authorization", "Bearer " + _key)
    try:
        with urllib.request.build_opener().open(req, timeout=180) as r:
            data = json.load(r)
    except Exception as e:
        print(f"{idx} API FAILED: {e}", flush=True)
        print("STOP: do not blind-retry rate-limit/activation errors", flush=True)
        sys.exit(2)
    url = data["data"][0]["url"]
    print(f"{idx} url host: {urllib.request.urlparse(url).netloc}", flush=True)
    r = subprocess.run(["curl", "-L", "--retry", "3", "--retry-delay", "2", "-o", str(out), url],
                       capture_output=True, text=True)
    if r.returncode != 0 or not out.exists() or out.stat().st_size < 20000:
        print(f"{idx} DOWNLOAD FAILED rc={r.returncode} size={out.stat().st_size if out.exists() else 0}", flush=True)
        sys.exit(3)
    try:
        from PIL import Image
        im = Image.open(out); im.verify()
        print(f"{idx} OK -> {out} ({out.stat().st_size} bytes)", flush=True)
        ok += 1
    except Exception as e:
        print(f"{idx} IMAGE INVALID: {e}", flush=True)
        sys.exit(3)
    time.sleep(3)
print(f"done {ok}")
