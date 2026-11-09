#!/usr/bin/env python3
"""v2：按用户新反馈重做
- 去掉闪白：图标正常淡入、正常出现/消失，不闪
- 图标不是一句一页：有对应关系的图标同屏共存，同一组内图标随句子逐个淡入、一直留到本组结束，字幕仍按句切换
- 分组不固定为三个：纯按语义分组，语义连着的就同屏（一个、两个、四个都可以），语义断了就换组
- 例：买了电影票 + 电影不好看 在同一画面；两百块 + 舍不得走 + 票钱回不来 在同一画面"""
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import pipeline
import sticker_motion
from template import load_template
from PIL import Image, ImageDraw, ImageFilter

CONFIG = pipeline.load_yaml(BASE / "config.yaml", {})
import argparse as _ap, json as _json
_ap_p = _ap.ArgumentParser()
_ap_p.add_argument("--script", required=True, help="script JSON from generate_script_zhipu.py")
_ap_p.add_argument("--stickers", required=True, help="directory of sticker_XX.png files")
_ap_p.add_argument("--out", default="", help="output directory (default output/<script stem>)")
_ap_p.add_argument("--tts", default="none", choices=["none", "piper", "doubao"], help="voice: none = silent (old behaviour), piper = offline Piper TTS, doubao = Doubao TTS 2.0 via custom.doubao-tts")
_ap_p.add_argument("--speaker", default="zh_male_xionger_uranus_bigtts", help="Doubao TTS speaker id (only with --tts doubao)")
_ap_p.add_argument("--speech-rate", type=int, default=10, help="Doubao TTS speech rate: 0 = 1.0x, 10 = 1.1x, 100 = 2.0x (only with --tts doubao)")
_ap_p.add_argument("--details", default="", help="dir of detail_XX.png stickers (second content element inside a sentence); empty = none")
_ap_p.add_argument("--skip-details", default="", help="comma-separated beat indices whose detail sticker is skipped (not every sentence needs one; decide by sentence meaning)")
_ap_p.add_argument("--background", default="dusk", choices=["dusk", "ai"], help="background: dusk = code-drawn gradient (default), ai = the template's town image, unblurred, with bottom fade and watermark cropped out")
_ap_p.add_argument("--template", default="coral-bay", help="style template under templates/ (default coral-bay); the background, world and style words come from it")
_ap_p.add_argument("--beat-durs", default="", help="per-beat durations (seconds): a JSON file (list or {\"beat_durs\": [...]}) or a comma-separated list. Overrides the script's beat_durs and the theoretical estimate.")
_ap_p.add_argument("--word-times", default="", help="word timestamps JSON: {beat_index: [{word, start, end}]} with times in seconds relative to the beat start. Used to resolve motion.trigger_word to a real voice time.")
_ap_a = _ap_p.parse_args()
DETAILS = (Path(_ap_a.details) if Path(_ap_a.details).is_absolute() else BASE / _ap_a.details) if _ap_a.details else None
SKIP_DETAILS = {int(x) for x in _ap_a.skip_details.split(",") if x.strip()} if _ap_a.skip_details else set()
_SCRIPT = _json.loads(Path(_ap_a.script).read_text(encoding="utf-8"))
OUT = (Path(_ap_a.out) if _ap_a.out else BASE / "output" / Path(_ap_a.script).stem).resolve()
WORK = OUT / "work"
OUT.mkdir(parents=True, exist_ok=True)
WORK.mkdir(exist_ok=True)
W, H = 1920, 1080
BEATS = [(b["text"], b["key"], b["char"], tuple(b["color"])) for b in _SCRIPT["beats"]]
GROUPS = _SCRIPT["groups"]
for _g in GROUPS:
    assert 1 <= len(_g) <= 2, 'v4 groups must have 1 or 2 stickers'
END_CARDS = [(c, (255, 255, 255)) if i == 0 else (c, (245, 158, 11)) for i, c in enumerate(_SCRIPT["end_cards"])]

def blurred_bg():
    if _ap_a.background == "ai":
        # the template's town image, unblurred as the user asked, but with
        # the bottom dark fade for subtitle readability and the bottom-right
        # AI watermark cropped out. The template stores it at 1344x768, so
        # the sand line lands at y=700 after the stretch below; no manual
        # background swap is needed any more (the old swap step is retired).
        ai_path = load_template(_ap_a.template)["background_path"]
        _ai = Image.open(ai_path).convert("RGB")
        # crop off the bottom strip that carries the AI watermark (bottom-right
        # corner, y >= ~700 in the 1344x768 original) instead of painting over
        # it, which would leave a visible solid block or seam.
        _ai = _ai.crop((0, 0, _ai.width, 690))
        img = _ai.resize((W, H), Image.LANCZOS)
        fade = Image.new("L", (W, 260), 0)
        _fd = ImageDraw.Draw(fade)
        for _y in range(260):
            _fd.line([(0, _y), (W, _y)], fill=int(110 * (_y / 260) ** 1.5))
        _dark = Image.new("RGBA", (W, 260), (8, 12, 32, 255))
        img = img.convert("RGBA")
        img.paste(_dark, (0, 820), fade)
        return img.convert("RGB")
    # v5 background: deep teal-to-plum dusk gradient, pastel bokeh blobs, darker bottom band for subtitles
    img = Image.new("RGB", (W, H), (20, 50, 90))
    d = ImageDraw.Draw(img)
    top, mid, bot = (16, 42, 84), (28, 110, 130), (52, 38, 88)
    for y in range(H):
        f = y / H
        if f < 0.5:
            a, b, k = top, mid, f * 2
        else:
            a, b, k = mid, bot, (f - 0.5) * 2
        d.line([(0, y), (W, y)], fill=tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3)))
    for x0, y0, x1, y1, col in [
        (120, 80, 620, 480, (255, 190, 140)), (1300, 60, 1850, 420, (150, 220, 200)),
        (650, 300, 1150, 750, (200, 170, 230)), (150, 650, 650, 1050, (255, 150, 170)),
        (1400, 620, 1900, 1020, (120, 200, 240)), (850, 120, 1250, 420, (255, 230, 150))]:
        d.ellipse([x0, y0, x1, y1], fill=col)
    img = img.filter(ImageFilter.GaussianBlur(45))
    # soft dark fade at the bottom for subtitle readability (no hard edge)
    fade = Image.new("L", (W, 260), 0)
    _fd = ImageDraw.Draw(fade)
    for _y in range(260):
        _fd.line([(0, _y), (W, _y)], fill=int(110 * (_y / 260) ** 1.5))
    _dark = Image.new("RGBA", (W, 260), (8, 12, 32, 255))
    img = img.convert("RGBA")
    img.paste(_dark, (0, 820), fade)
    return img.convert("RGB")

STICKER_DIR = Path(_ap_a.stickers).resolve()
def small_card(key, icon, accent, cw=540, ch=380, beat_idx=None, explicit_scale=None):
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f_key = pipeline.get_font(CONFIG, 56)
    sticker = None
    if beat_idx is not None:
        sp = STICKER_DIR / ("sticker_%02d.png" % beat_idx)
        if sp.exists():
            sticker = Image.open(sp).convert("RGBA")
    if sticker is not None:
        max_h = ch - 20
        max_w = cw - 20
        if explicit_scale is not None:
            scale = explicit_scale
        else:
            scale = min(max_h / sticker.height, max_w / sticker.width)
        sticker = sticker.resize((max(1, int(sticker.width * scale)), max(1, int(sticker.height * scale))), Image.LANCZOS)
        sx, sy = (cw - sticker.width) // 2, (ch - sticker.height) // 2
        shadow = Image.new("RGBA", sticker.size, (0, 0, 0, 0))
        shadow.paste(Image.new("RGBA", sticker.size, (0, 0, 0, 110)), (0, 0), sticker.split()[3])
        shadow = shadow.filter(ImageFilter.GaussianBlur(8))
        img.paste(shadow, (sx + 8, sy + 10), shadow)
        img.paste(sticker, (sx, sy), sticker)
    else:
        f_icon = pipeline.get_font(CONFIG, 88)
        cx, cy, r = cw // 2, 105 if ch <= 320 else 115, 64 if ch <= 320 else 72
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)
        tw = d.textlength(icon, font=f_icon)
        d.text((cx - tw / 2, cy - 52), icon, font=f_icon, fill=(255, 255, 255))
    # v3: no keyword text, sticker alone, enlarged
    return img

def subtitle_image(text):
    # v6: subtitle larger, stroke thinner/lighter
    # user 2026-11-05 (reference screenshot): subtitle is ONE line, centred
    # near the bottom like the SpongeBob reference (text centre ~y=940 of
    # 1080). The two-line break tried in v4 was wrong; revert to one line.
    font = pipeline.get_font(CONFIG, 64)
    tmp = Image.new("RGBA", (10, 10))
    d0 = ImageDraw.Draw(tmp)
    lines = pipeline.wrap_text(d0, text, font, 1700)
    # don't leave a lone punctuation mark on its own line (it happens when the
    # last character exactly fills a line); pull it back onto the previous line
    if len(lines) > 1 and len(lines[-1]) <= 2 and all(c in "。，、！？；：）" for c in lines[-1]):
        lines[-2] += lines[-1]
        lines.pop()
    lh = 88
    img = Image.new("RGBA", (1800, 340), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y0 = (340 - len(lines) * lh) // 2
    for i, line in enumerate(lines):
        tw = d.textlength(line, font=font)
        d.text(((1800 - tw) / 2, y0 + i * lh), line, font=font, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
    return img

def text_card_image(text, color):
    img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img)
    font = pipeline.get_font(CONFIG, 96)
    lines = pipeline.wrap_text(d, text, font, 1600)
    y = (H - len(lines) * 130) // 2
    for line in lines:
        tw = d.textlength(line, font=font)
        d.text(((W - tw) / 2, y), line, font=font, fill=color)
        y += 130
    return img

bg_path = WORK / "bg.png"
blurred_bg().save(bg_path)
black_path = WORK / "black.png"
Image.new("RGB", (W, H), (0, 0, 0)).save(black_path)
# title
title_img = WORK / "title.png"
img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
f = pipeline.get_font(CONFIG, 150)
t = _SCRIPT["title"]
tw = d.textlength(t, font=f)
d.text(((W - tw) / 2, (H - 150) / 2), t, font=f, fill=(239, 68, 68))
img.save(title_img)

def dur_of(sent):
    rate = 1.0 + (_ap_a.speech_rate / 100.0 if _ap_a.tts == "doubao" else 0.0)
    return max(2.0, len(sent) / 4.5 / rate)

# Beat durations (round 1): from --beat-durs, a sidecar, the script's
# `beat_durs` field, or the theoretical estimate, in that order.
ALL_DURS, _DUR_SRC = sticker_motion.resolve_beat_durs(
    _SCRIPT, _ap_a.beat_durs or None, dur_of,
    script_path=_ap_a.script)
WORD_TIMES = sticker_motion.load_word_times(_ap_a.word_times or None, _SCRIPT)
print("句长来源：%s（%d 句）" % (_DUR_SRC, len(ALL_DURS)))

seg_files, audios, total = [], [], 0.0
seg_idx = 0
TTS = _ap_a.tts
TTS_SCRIPT = BASE / "tools" / "tts_piper.py"

def _silent_mp3(dur, path):
    pipeline.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(dur), "-q:a", "9", "-acodec", "libmp3lame", str(path)])


import hashlib
VOICE_CACHE = BASE / "cutouts" / "voice_cache"

def _doubao_raw(text, speaker, rate, tts_script):
    """Cached raw (unpadded) Doubao audio for this text+speaker+rate.

    The renderer used to re-synthesise every sentence on every render
    (no cache), so re-rendering the same episode paid for the same
    sentences again. Now the raw synthesis is cached by content hash
    under cutouts/voice_cache/ and reused across renders and versions;
    only the (free, local) padding to the beat duration is redone.
    """
    key = hashlib.sha256(("|".join([speaker, str(rate), text])).encode("utf-8")).hexdigest()[:16]
    VOICE_CACHE.mkdir(parents=True, exist_ok=True)
    cached = VOICE_CACHE / (key + ".mp3")
    if cached.exists() and cached.stat().st_size > 1000:
        return cached
    import subprocess as _sp
    rr = _sp.run([sys.executable, str(tts_script),
                  "--text", text, "--speaker", speaker,
                  "--speech-rate", str(rate),
                  "--out", str(cached)], capture_output=True, text=True)
    if rr.returncode != 0 or not cached.exists() or cached.stat().st_size <= 1000:
        return None
    return cached

def _pad_audio(raw, target, out):
    """Pad/trim raw audio to exactly `target` seconds (same rule as tts.py --pad-to)."""
    import subprocess as _sp
    dur_out = _sp.check_output(["ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1",
        str(raw)]).decode().strip()
    dur = float(dur_out.split("=")[1])
    if dur > target:
        filt = "atempo=%.3f,apad=whole_dur=%s" % (dur / target, target)
    else:
        filt = "apad=whole_dur=%s" % target
    _sp.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", filt,
             "-t", str(target), "-q:a", "9", "-acodec", "libmp3lame", str(out)], check=True)

def add_segment(dur, cmd_args, filt, out_name, audio_texts=None, audio_durs=None):
    global total, seg_idx
    out = WORK / out_name
    pipeline.run(["ffmpeg", "-y", "-v", "error"] + cmd_args + ["-filter_complex", filt, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30", str(out)])
    seg_files.append(out)
    total += dur
    seg_audio = WORK / ("audio_%02d.mp3" % seg_idx)
    if TTS == "doubao" and audio_texts:
        parts = []
        ok = True
        for k, (text, bd) in enumerate(zip(audio_texts, audio_durs or [])):
            part = WORK / ("voice_%02d_%d.mp3" % (seg_idx, k))
            raw = _doubao_raw(text, _ap_a.speaker, _ap_a.speech_rate, BASE / "tools" / "tts_doubao.py")
            if raw is None:
                print("配音失败，改用静音：%s" % text[:20])
                ok = False
                break
            try:
                _pad_audio(raw, bd, part)
            except Exception:
                print("配音失败，改用静音：%s" % text[:20])
                ok = False
                break
            parts.append(part)
        if ok and parts:
            lst = WORK / ("voice_list_%02d.txt" % seg_idx)
            lst.write_text("".join("file '" + str(p) + "'\n" for p in parts), encoding="utf-8")
            pipeline.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(seg_audio)])
        else:
            _silent_mp3(dur, seg_audio)
    elif TTS == "piper" and audio_texts:
        parts = []
        ok = True
        for k, (text, bd) in enumerate(zip(audio_texts, audio_durs or [])):
            part = WORK / ("voice_%02d_%d.mp3" % (seg_idx, k))
            import subprocess as _sp
            rr = _sp.run([sys.executable, str(TTS_SCRIPT), "--text", text, "--out", str(part), "--pad-to", str(bd)], capture_output=True, text=True)
            if rr.returncode != 0 or not part.exists():
                print("配音失败，改用静音：%s" % text[:20])
                ok = False
                break
            parts.append(part)
        if ok and parts:
            lst = WORK / ("voice_list_%02d.txt" % seg_idx)
            lst.write_text("".join("file '" + str(p) + "'\n" for p in parts), encoding="utf-8")
            pipeline.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(seg_audio)])
        else:
            _silent_mp3(dur, seg_audio)
    else:
        _silent_mp3(dur, seg_audio)
    audios.append(seg_audio)
    seg_idx += 1
    return out

# no title segment: user 2026-11-05 wants the film to start directly with
# the first cartoon scene, no title black screen or title subtitle.
for gi, group in enumerate(GROUPS):
    durs = [ALL_DURS[i] for i in group]
    gdur = sum(durs)
    offsets = [0.0]
    for dd in durs[:-1]:
        offsets.append(offsets[-1] + dd)
    # v5 layout rule (user-approved 2026-11-05, group-1 test v5):
    # max 2 stickers per screen, no top keyword/explainer text layer.
    # - Grounding: stickers up to 45% of screen height (486px), feet on the
    #   sand line (y=700 in the new Coral Bay background, measured from
    #   work/bg.png), not a 300px card floating at y=60.
    # - Size: equalise by opaque pixel area, anchored on the first sticker
    #   at 486px height, so a wide sticker no longer dominates a narrow one.
    # - Pair spacing: 220px inner gap between the two cards, symmetric
    #   about screen centre 960.
    # - Entrances: horizontal slide-in (<1s), no 0.4s 300px drop, no large
    #   sine bob (only +-4px). First sticker slides in from the left, then
    #   slides left to make room; second slides in from the right.
    if len(group) not in (1, 2):
        raise ValueError("v5 groups must have 1 or 2 stickers")
    import numpy as _np
    _infos = []
    for bi in group:
        _sp = STICKER_DIR / ("sticker_%02d.png" % bi)
        _im = Image.open(_sp).convert("RGBA")
        _area = int((_np.array(_im.split()[3]) > 10).sum())
        _infos.append((_im, _area))
    _target_h = 486.0
    _scale0 = _target_h / _infos[0][0].height
    _target_area = _infos[0][1] * _scale0 ** 2
    _scales = [(_target_area / a) ** 0.5 if a else 1.0 for _, a in _infos]
    card_ws, card_hs, sticker_hs = [], [], []
    for (_im, _a), _s in zip(_infos, _scales):
        _w = max(1, int(_im.width * _s))
        _h = max(1, int(_im.height * _s))
        card_ws.append(_w + 20)
        card_hs.append(_h + 20)
        sticker_hs.append(_h)
    _feet_y = 700
    ys = [_feet_y - _h for _h in sticker_hs]
    if len(group) == 1:
        xs = [(W - card_ws[0]) // 2]
    else:
        _total = card_ws[0] + card_ws[1] + 220
        _left = (W - _total) // 2
        xs = [_left, _left + card_ws[0] + 220]
    pair_scales = {bi: _s for bi, _s in zip(group, _scales)}
    args, filt_parts, cur = [], [], "bg"
    det_sizes = {}
    args += ["-loop", "1", "-t", str(gdur), "-i", str(bg_path)]
    filt_parts.append("[0:v]fps=30[bg]")
    inp = 1
    labels = {}
    for k, bi in enumerate(group):
        sent, key, icon, accent = BEATS[bi]
        card_path = WORK / ("card_%02d.png" % bi)
        small_card(key, icon, accent, card_ws[k], card_hs[k], beat_idx=bi, explicit_scale=pair_scales.get(bi)).save(card_path)
        args += ["-loop", "1", "-t", str(gdur), "-i", str(card_path)]
        labels[("card", k)] = inp
        # no fade-in: user 2026-11-05 said stickers must not have a black
        # entrance effect. The old fade=t=in darkened the sticker on entry.
        filt_parts.append("[%d:v]format=rgba[c%d]" % (inp, k))
        inp += 1
    det_rot = {}
    for k, bi in enumerate(group):
        # detail sticker (user 2026-11-05: split each sentence's content,
        # add a second small element inside the sentence). detail_XX.png is
        # pre-cut to 250px tall; here it is fitted into a 320x250 box.
        if DETAILS is None or bi in SKIP_DETAILS:
            continue
        det_src = DETAILS / ("detail_%02d.png" % bi)
        if not det_src.exists():
            continue
        _dim = Image.open(det_src)
        _sc = min(1.0, 320 / _dim.width, 250 / _dim.height)
        _dw, _dh = max(1, int(_dim.width * _sc)), max(1, int(_dim.height * _sc))
        det_path = WORK / ("detail_%02d.png" % bi)
        _dim.resize((_dw, _dh), Image.LANCZOS).save(det_path)
        det_sizes[bi] = (_dw, _dh)
        args += ["-loop", "1", "-t", str(gdur), "-i", str(det_path)]
        labels[("det", k)] = inp
        if bi == 2:
            # the airplane orbits the globe (user 2026-11-05): it needs a
            # per-frame rotation so its nose follows the flight path. The
            # angle is 0 while it drops in, then follows the orbit tangent.
            # t1 = when the orbit starts (0.5s after it appears, i.e.
            # after the fall, at the resolved trigger time).
            _tl, _ = sticker_motion.resolve_trigger(
                _SCRIPT["beats"][bi], bi, durs[k], WORD_TIMES)
            _t1 = offsets[k] + _tl + 0.5
            _ang = ("if(lt(t,%.2f),0,atan2(180*sin(1.5708*(t-%.2f)),-300*cos(1.5708*(t-%.2f)))-PI)"
                    % (_t1, _t1, _t1))
            filt_parts.append("[%d:v]format=rgba,rotate=a='%s':ow='hypot(iw,ih)':oh='hypot(iw,ih)':fillcolor=black@0[d%d]" % (inp, _ang, k))
            det_rot[bi] = int((_dw ** 2 + _dh ** 2) ** 0.5) + 2
        else:
            filt_parts.append("[%d:v]format=rgba[d%d]" % (inp, k))
        inp += 1
    for k, bi in enumerate(group):
        sent = BEATS[bi][0]
        sub_path = WORK / ("sub_%02d.png" % bi)
        subtitle_image(sent).save(sub_path)
        args += ["-loop", "1", "-t", str(gdur), "-i", str(sub_path)]
        labels[("sub", k)] = inp
        # no fade-in on subtitles either (same black-entrance reason)
        filt_parts.append("[%d:v]format=rgba[s%d]" % (inp, k))
        inp += 1
    tmp = 0
    # layout (user 2026-11-05): 3 or 4 elements on screen -> one row
    # (一字形), all feet on the sand line, details between the two mains.
    # The pin (品字型) layout was retired the same day: when the three
    # images differ a lot in size, the small one on top looks off, so a
    # straight line reads better. Fewer -> the old v5 pair layout (first
    # sticker centred, then slides to its slot).
    _n_det = sum(1 for bi in group if bi in det_sizes)
    _n_elem = len(group) + _n_det
    _mode = "row" if (_n_elem in (3, 4) and len(group) == 2) else "pair"
    _row_cx = {}
    if _mode == "row":
        _widths = [card_ws[0]]
        if group[0] in det_sizes:
            _widths.append(det_sizes[group[0]][0])
        if group[1] in det_sizes:
            _widths.append(det_sizes[group[1]][0])
        _widths.append(card_ws[1])
        _gap = 100
        _left = (W - (sum(_widths) + (_n_elem - 1) * _gap)) // 2
        _cx = _left
        for _i, _w in enumerate(_widths):
            _row_cx[_i] = _cx + _w // 2
            _cx += _w + _gap
    for k, bi in enumerate(group):
        off = offsets[k]
        end = offsets[k + 1] if k + 1 < len(group) else gdur
        # detail trigger (round 1): resolved from the beat's motion config.
        # `trig` is the absolute time (within this group segment) when the
        # detail STARTS entering.
        _trig_local, _trig_src = sticker_motion.resolve_trigger(
            _SCRIPT["beats"][bi], bi, durs[k], WORD_TIMES)
        trig = off + _trig_local
        if _trig_src != "default":
            print("组 %d 句 %d 细节触发：%.2fs（%s）" % (gi + 1, bi + 1, trig, _trig_src))
        # entrance (round 1): horizontal slide-in only. The old bi % 4
        # rotation (left / right / drop from top / rise from bottom) is
        # gone; direction comes from motion.enter (default left).
        # Smootherstep easing over 0.6s from the beat start. No idle bob
        # and no hop: the sticker stays still after entering.
        enter_dir = sticker_motion.resolve_enter(_SCRIPT["beats"][bi])
        ex = sticker_motion.ff_enter_offset(enter_dir, start=off)
        Wk, Hk = card_ws[k], card_hs[k]
        YB = ys[k] + Hk
        # centre-x of this sticker over time
        if _mode == "row":
            # row order is [main0, detail0, [detail1,] main1]
            cx_expr = "%d" % (_row_cx[0] if k == 0 else _row_cx[len(_widths) - 1])
        elif len(group) == 1:
            cx_expr = "%d" % (xs[k] + Wk // 2)
        elif k == 0:
            # first sticker slides left to its slot when the second
            # appears, smootherstep (0.6s), starting 0.1s before that.
            _off1 = offsets[1]
            cx_expr = sticker_motion.ff_slide(
                str(W // 2), str(xs[0] + Wk // 2),
                max(0.0, _off1 - sticker_motion.YIELD_LEAD),
                sticker_motion.YIELD_DUR)
        else:
            cx_expr = "%d" % (xs[k] + Wk // 2)
        # main sticker: one framing for the whole group (the mid-sentence
        # push-in cut was rejected by the user 2026-11-05: cut the sentence's
        # content, not the picture). It accumulates within the group.
        x1 = "(%s)+(%s)-%d/2" % (cx_expr, ex, Wk)
        y1 = "%d" % (YB - Hk)
        nxt = "tmp%d" % tmp
        filt_parts.append("[%s][c%d]overlay=x='%s':y='%s':enable='between(t,%s,%s)'[%s]" % (cur, k, x1, y1, off, gdur, nxt))
        cur, tmp = nxt, tmp + 1
        # detail sticker: the sentence's second content element. It drops
        # in from above at the resolved trigger time with an accelerating
        # fall, then ONE small upward bounce (8px, 0.35s) that never goes
        # below the sand line and settles to still. No continuous bob.
        #   row: in the one-row line between the two mains
        #   otherwise: inner side of its main sticker (old v8 rule)
        # The airplane (beat 2) is special: after it appears it orbits the
        # globe (user 2026-11-05), one slow circle per 4s, nose following
        # the path, instead of sitting in the row.
        if bi in det_sizes:
            _dw, _dh = det_sizes[bi]
            _drop = sticker_motion.ff_drop(trig)
            _bounce = sticker_motion.ff_bounce(trig + sticker_motion.DROP_DUR)
            if bi == 2 and _mode == "row":
                _ocx, _ocy = _row_cx[0], int(700 - sticker_hs[0] / 2)
                _S = det_rot[bi]
                _t1 = trig + 0.5
                _th = "1.5708+1.5708*(t-%.2f)" % _t1
                _dx = ("if(lt(t,%.2f),%d-%d/2,%d+300*cos(%s)-%d/2)"
                       % (_t1, _ocx, _S, _ocx, _th, _S))
                _dy = ("if(lt(t,%.2f),%d-(%s)-%d/2,%d-180*sin(%s)-%d/2)"
                       % (_t1, _ocy - 180, _drop, _S, _ocy, _th, _S))
                nxt = "tmp%d" % tmp
                filt_parts.append("[%s][d%d]overlay=x='%s':y='%s':enable='between(t,%s,%s)'[%s]" % (cur, k, _dx, _dy, trig, gdur, nxt))
                cur, tmp = nxt, tmp + 1
                continue
            elif _mode == "row":
                _dx = "%d-%d/2" % (_row_cx[1 + k], _dw)
                _dy = "%d-(%s)+(%s)" % (700 - _dh, _drop, _bounce)
            else:
                if len(group) == 2:
                    _side = 1 if k == 0 else -1
                    _vstag = -130 if k == 0 else 130
                else:
                    _side, _vstag = 1, 0
                _dx = "(%s)+%d-%d/2" % (cx_expr, _side * 400, _dw)
                _dy = "%d-(%s)+(%s)" % (int(ys[k] + Hk / 2 + _vstag - _dh / 2), _drop, _bounce)
            nxt = "tmp%d" % tmp
            filt_parts.append("[%s][d%d]overlay=x='%s':y='%s':enable='between(t,%s,%s)'[%s]" % (cur, k, _dx, _dy, trig, gdur, nxt))
            cur, tmp = nxt, tmp + 1
    for k, bi in enumerate(group):
        end = offsets[k + 1] if k + 1 < len(group) else gdur
        nxt = "tmp%d" % tmp
        filt_parts.append("[%s][s%d]overlay=x='(W-w)/2':y=775:enable='between(t,%s,%s)'[%s]" % (cur, k, offsets[k], end, nxt))
        cur, tmp = nxt, tmp + 1
    filt = ";".join(filt_parts)
    filt = filt.replace("[%s]" % cur, "[v]", 1) if False else filt
    # last overlay output must be [v]: rebuild last part
    filt_parts[-1] = filt_parts[-1].rsplit("[", 1)[0] + "[v]"
    filt = ";".join(filt_parts)
    add_segment(gdur, args, filt, "seg_group%d.mp4" % gi, audio_texts=[BEATS[i][0] for i in group], audio_durs=durs)
    print("组 %d 完成：%s（%.1f 秒，同屏 %d 个图标）" % (gi + 1, "、".join(BEATS[i][1] for i in group), gdur, len(group)))
for j, (text, color) in enumerate(END_CARDS):
    card_path = WORK / ("end_%d.png" % j)
    text_card_image(text, color).save(card_path)
    add_segment(3.0, ["-loop", "1", "-t", "3.0", "-i", str(card_path)], "[0:v]fps=30[v]", "seg_end%d.mp4" % j)
    print("结尾 %d 完成" % (j + 1))
lst = WORK / "video_list.txt"
lst.write_text("".join("file '" + str(s) + "'\n" for s in seg_files), encoding="utf-8")
silent_video = WORK / "video_only.mp4"
pipeline.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent_video)])
alst = WORK / "audio_list.txt"
alst.write_text("".join("file '" + str(a) + "'\n" for a in audios), encoding="utf-8")
audio = WORK / "audio.mp3"
pipeline.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(alst), "-c", "copy", str(audio)])
video = OUT / "video.mp4"
pipeline.run(["ffmpeg", "-y", "-v", "error", "-i", str(silent_video), "-i", str(audio), "-c", "copy", "-shortest", str(video)])
(OUT / "audio.mp3").write_bytes(audio.read_bytes())
lines = ["【标题】" + _SCRIPT["title"]]
for gi, group in enumerate(GROUPS):
    lines.append("组 %d 同屏：%s" % (gi + 1, " + ".join("%s（%s）" % (BEATS[i][0], BEATS[i][1]) for i in group)))
lines += ["【结尾】" + t for t, _ in END_CARDS]
(OUT / "script.txt").write_text("\n".join(lines), encoding="utf-8")
print("完成：" + _SCRIPT.get("topic", _SCRIPT["title"]) + "·同屏版 -> " + str(video) + "（%.1f 秒，%d 段）" % (total, len(seg_files)))
