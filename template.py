"""Style template loader for the cutout science video pipeline.

A template is a folder under templates/<name>/ with:
  style.yaml      - name, image style words, model, background, fonts, voice
  world_bible.md  - the fixed cast and locations (the understanding step reads this)
  background.png  - 1344x768 town background (renderer crops to y=690, stretches
                    to 1920x1080, sand line lands at y=700)
  characters/     - the fixed cast stickers, reused across episodes

Layout rules (one-row / pin rows, subtitle position, motion, the airplane
orbit) are series-wide and deliberately NOT part of a template: changing the
look must not change the layout.

Usage:
    from template import load_template, list_templates
    tpl = load_template("coral-bay")
    tpl["image_style"]          # prompt words for main stickers
    tpl["detail_style"]         # prompt words for detail stickers
    tpl.background_path         # Path to templates/coral-bay/background.png
    tpl.world_bible_path        # Path to templates/coral-bay/world_bible.md
    tpl.characters_dir          # Path to templates/coral-bay/characters/
"""
import yaml
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

DEFAULTS = {
    "image_model": "doubao-seedream-5-0-pro-260628",
    "sand_line_y": 700,
    "background": "background.png",
    "world_bible": "world_bible.md",
    "characters": "characters/",
}


def list_templates():
    """Names of all folders under templates/ that contain a style.yaml."""
    if not TEMPLATES_DIR.exists():
        return []
    return sorted(
        p.name for p in TEMPLATES_DIR.iterdir()
        if p.is_dir() and (p / "style.yaml").exists()
    )


def load_template(name):
    """Load a template by name. Returns a dict with resolved Path values.

    Raises ValueError naming the available templates when the name is unknown
    or the folder is incomplete.
    """
    avail = list_templates()
    tpl_dir = TEMPLATES_DIR / name
    if name not in avail:
        raise ValueError(
            "unknown template %r (available: %s)"
            % (name, ", ".join(avail) if avail else "none")
        )
    style_path = tpl_dir / "style.yaml"
    data = yaml.safe_load(style_path.read_text(encoding="utf-8")) or {}
    merged = dict(DEFAULTS)
    merged.update(data)
    # detail stickers fall back to the main style words when not specified
    if "detail_style" not in merged and "image_style" in merged:
        merged["detail_style"] = merged["image_style"]
    bg = tpl_dir / merged["background"]
    bible = tpl_dir / merged["world_bible"]
    chars = tpl_dir / merged["characters"]
    missing = [str(p) for p in (bg, bible) if not p.exists()]
    if missing:
        raise ValueError("template %r is incomplete, missing: %s" % (name, missing))
    merged["dir"] = tpl_dir
    merged["background_path"] = bg
    merged["world_bible_path"] = bible
    merged["characters_dir"] = chars
    return merged
