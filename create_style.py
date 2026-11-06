#!/usr/bin/env python3
"""Create a new style template locally (no Muse needed).

A style template is a folder `templates/<name>/` with:
    style.yaml      name, image style words, model, subtitle/voice defaults
    world_bible.md  the fixed cast (characters) and places, in your own words
    background.png  1344x768 town/scene background (used by --background ai)
    characters/     fixed character/location stickers, transparent PNGs

Usage:
    # 1. Copy the example spec and edit it (style words, characters, places):
    cp templates/_example_spec.json my_style_spec.json
    # 2. Generate everything (Seedream by default, ~¥0.06/image):
    python3 create_style.py --name my-style --spec my_style_spec.json
    #    ...or with Zhipu CogView-4 instead:
    python3 create_style.py --name my-style --spec my_style_spec.json --engine zhipu
    # 3. Use it:
    python3 make_cutout_from_script_v13.py ... --template my-style --background ai

Keys come from the environment (never written to a file):
    ARK_API_KEY      for --engine seedream (Volcano Ark console)
    ZHIPU_API_KEY    for --engine zhipu   (bigmodel.cn console -> API Keys)

Spec format (see templates/_example_spec.json):
    {
      "style": "<style words appended to every image prompt>",
      "background_prompt": "<prompt for the 1344x768 town background>",
      "world_bible": "<free text: who the characters are, where the story happens>",
      "items": [
        {"name": "momo", "label": "墨墨 章鱼老师",
         "prompt": "a small round-headed blue octopus teacher wearing round glasses and a yellow scarf"}
      ]
    }
Each item becomes one transparent sticker in characters/<name>.png.
The background is generated once and resized to 1344x768 (not cut).
Re-running is safe: existing images are skipped unless --force is given.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

BG_W, BG_H = 1344, 768


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)


def ark_key():
    key = os.environ.get("ARK_API_KEY", "")
    if not key:
        fail("ARK_API_KEY is not set. Get a key at the Volcano Ark console, "
             "then: export ARK_API_KEY=<key>")
    return key


def zhipu_key():
    key = os.environ.get("ZHIPU_API_KEY", "")
    if not key:
        fail("ZHIPU_API_KEY is not set. Get a key at bigmodel.cn console -> "
             "API Keys, then: export ZHIPU_API_KEY=<key>")
    return key


def gen_seedream(prompt, model, out_path, key):
    """Generate one image with Seedream (Ark), download with curl retry."""
    body = json.dumps({"model": model, "prompt": prompt, "size": "1024x1024",
                       "response_format": "url", "watermark": False}).encode()
    req = urllib.request.Request(
        "https://ark.cn-beijing.volces.com/api/v3/images/generations",
        data=body, headers={"Content-Type": "application/json"}, method="POST")
    req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.build_opener().open(req, timeout=180) as r:
            data = json.load(r)
    except Exception as e:
        print("  API FAILED:", e, flush=True)
        return False
    url = data["data"][0]["url"]
    r = subprocess.run(["curl", "-L", "--retry", "3", "--retry-delay", "2",
                        "-o", str(out_path), url],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0 or not out_path.exists() or out_path.stat().st_size < 50000:
        print("  DOWNLOAD FAILED:", out_path, flush=True)
        return False
    return True


def gen_zhipu(prompt, model, out_path, key):
    """Generate one image with Zhipu (CogView), via its image API."""
    body = json.dumps({"model": model, "prompt": prompt,
                       "size": "1024x1024"}).encode()
    req = urllib.request.Request(
        "https://open.bigmodel.cn/api/paas/v4/images/generations",
        data=body, headers={"Content-Type": "application/json",
                            "Authorization": "Bearer " + key}, method="POST")
    try:
        with urllib.request.build_opener().open(req, timeout=180) as r:
            data = json.load(r)
    except Exception as e:
        print("  API FAILED:", e, flush=True)
        return False
    url = data["data"][0]["url"]
    r = subprocess.run(["curl", "-L", "--retry", "3", "--retry-delay", "2",
                        "-o", str(out_path), url],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0 or not out_path.exists() or out_path.stat().st_size < 50000:
        print("  DOWNLOAD FAILED:", out_path, flush=True)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="Create a new style template.")
    ap.add_argument("--name", required=True, help="template folder name, e.g. my-style")
    ap.add_argument("--spec", required=True, help="spec JSON (see templates/_example_spec.json)")
    ap.add_argument("--engine", default="seedream", choices=["seedream", "zhipu"],
                    help="image engine (default: seedream)")
    ap.add_argument("--model", default="",
                    help="image model (default: doubao-seedream-5-0-pro-260628 / cogview-4)")
    ap.add_argument("--force", action="store_true", help="regenerate existing images")
    args = ap.parse_args()

    if "/" in args.name or "\\" in args.name or args.name in (".", ".."):
        fail("bad template name: %r" % args.name)
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    style = spec.get("style", "")
    items = spec.get("items", [])
    bg_prompt = spec.get("background_prompt", "")
    world_bible = spec.get("world_bible", "")
    if not items and not bg_prompt:
        fail("spec has no items and no background_prompt; nothing to generate")

    if args.engine == "seedream":
        key = ark_key()
        model = args.model or "doubao-seedream-5-0-pro-260628"
        gen = lambda p, o: gen_seedream(p, model, o, key)
    else:
        key = zhipu_key()
        model = args.model or "cogview-4"
        gen = lambda p, o: gen_zhipu(p, model, o, key)

    from generate_stickers_zhipu import cut_white_background

    tpl = BASE / "templates" / args.name
    chars = tpl / "characters"
    raw_dir = BASE / "cutouts" / ("seedream_raw_style_" + args.name if args.engine == "seedream"
                                   else "zhipu_raw_style_" + args.name)
    chars.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    # --- background (full scene, resized to 1344x768, not cut) ---
    if bg_prompt:
        bg_raw = raw_dir / "background.png"
        bg_out = tpl / "background.png"
        if not bg_out.exists() or args.force:
            print("[background] ...", flush=True)
            full = (bg_prompt + ", " + style) if style else bg_prompt
            if gen(full, bg_raw):
                from PIL import Image
                im = Image.open(bg_raw).convert("RGB").resize((BG_W, BG_H), Image.LANCZOS)
                im.save(bg_out)
                print("  ->", bg_out, flush=True)
            else:
                print("  background FAILED, continuing with the rest", flush=True)
        else:
            print("[background] exists, skipped", flush=True)

    # --- characters / locations (single subject, cut to transparent PNG) ---
    for it in items:
        name, label, prompt = it["name"], it.get("label", it["name"]), it["prompt"]
        raw = raw_dir / (name + ".png")
        dest = chars / (name + ".png")
        if dest.exists() and not args.force:
            print("[%s] exists, skipped" % name, flush=True)
            continue
        print("[%s] %s ..." % (name, label), flush=True)
        full = (prompt + ", " + style) if style else prompt
        if not gen(full, raw):
            print("  FAILED, skipped", flush=True)
            continue
        try:
            cut_white_background(str(raw), str(dest))
        except Exception as e:
            print("  CUT FAILED:", e, flush=True)
            continue
        print("  ->", dest, flush=True)

    # --- style.yaml + world_bible.md (written once, never overwritten) ---
    style_yaml = tpl / "style.yaml"
    if not style_yaml.exists():
        style_yaml.write_text(
            "name: %s\nmodel: %s\nengine: %s\nstyle: \"%s\"\n"
            "background: background.png\nsubtitle_font: NotoSansCJK-Bold\n"
            "voice: zh_male_xionger_uranus_bigtts\nvoice_rate: 10\n"
            % (args.name, model, args.engine, style.replace('"', "'")),
            encoding="utf-8")
        print("wrote", style_yaml, flush=True)
    bible = tpl / "world_bible.md"
    if not bible.exists():
        bible.write_text("# %s\n\n%s\n" % (args.name, world_bible or
                          "（在这里写这个世界的角色和地点：谁是谁、在哪发生故事。）\n"),
                         encoding="utf-8")
        print("wrote", bible, flush=True)
    print("Done. Use it with: --template %s --background ai" % args.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
