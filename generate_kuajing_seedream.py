#!/usr/bin/env python3
"""Generate 14 cross-border e-commerce icon stickers with Seedream 5.0 Pro,
download with curl retry (urlretrieve truncates), then cut the white
background with the pipeline's flood-fill cut step."""
import json, os, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_stickers_zhipu import cut_white_background
import urllib.request

BASE = Path(__file__).resolve().parent
RAW = BASE / "cutouts" / "seedream_raw_kuajing"
OUT = BASE / "cutouts" / "stickers_kuajing_seedream"
RAW.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--template", default="coral-bay", help="style template under templates/ (default coral-bay)")
_template = _ap.parse_args().template
from template import load_template
STYLE = load_template(_template)["image_style"]
PROMPTS = [
    "A smartphone with a small shopping bag floating above it",
    "A parcel box beside a small medicine bottle",
    "A globe with a small parcel sliding across it",
    "A warehouse shelf stacked with parcel boxes",
    "A delivery truck crossing a dotted border line",
    "A blue octopus holding a magnifying glass over an open parcel box, sea creature customs inspector",
    "An open parcel box with a looping return arrow",
    "A stack of gold coins beside a parcel box and a tiny blank receipt",
    "A price tag hanging on a small parcel box",
    "A phone case sitting on a small weighing scale",
    "A blue octopus tentacle and a green turtle flipper shaking hands above a parcel box, sea creatures",
    "A calculator beside a parcel box and a return arrow",
    "A green turtle taking a small step onto stacked parcel boxes, sea creature",
    "An open ledger book with gold coins and a small parcel box",
]

for i, subj in enumerate(PROMPTS):
    prompt = f"{subj}, {STYLE}"
    body = json.dumps({"model": "doubao-seedream-5-0-pro-260628", "prompt": prompt, "size": "1024x1024", "response_format": "url", "watermark": False}).encode()
    req = urllib.request.Request("https://ark.cn-beijing.volces.com/api/v3/images/generations", data=body, headers={"Content-Type": "application/json"}, method="POST")
    _key = os.environ.get("ARK_API_KEY", "")
    if not _key:
        print("ARK_API_KEY is not set. Get a key at the Volcano Ark console, then: export ARK_API_KEY=<key>", file=sys.stderr)
        sys.exit(2)
    req.add_header("Authorization", "Bearer " + _key)
    try:
        with urllib.request.build_opener().open(req, timeout=180) as r:
            data = json.load(r)
    except Exception as e:
        print(f"{i:02d} API FAILED: {e}", flush=True)
        continue
    url = data["data"][0]["url"]
    raw = RAW / f"raw_{i:02d}.jpg"
    subprocess.run(["curl", "-L", "--retry", "3", "--retry-delay", "2", "-o", str(raw), url], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    dest = OUT / f"sticker_{i:02d}.png"
    try:
        cut_white_background(str(raw), str(dest))
        print(f"{i:02d} OK -> {dest} ({dest.stat().st_size} bytes)", flush=True)
    except Exception as e:
        print(f"{i:02d} CUT FAILED: {e}", flush=True)
print("done")
