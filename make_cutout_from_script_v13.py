#!/usr/bin/env python3
"""v12：每屏最多 2 个贴纸（用户 2026-11-06：1 个居中、2 个一边一个）。
每句自成一屏，不再按组积累；主贴纸句首居中，细节句中从上掉落、主贴纸
左移让位。v11 的 3-4 图一字排已废弃。

v2：按用户新反馈重做
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
_ap_p.add_argument("--beat-durs", default="", help="per-beat durations (seconds): a JSON file (list or {\"beat_durs\": [...]}) or a comma-separated list. Overrides the script's beat_durs and the theoretical estimate. A '<script stem>_beat_durs.json' sidecar next to the script is used when this is empty.")
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

# Beat durations (round 1, 2026-11-07): no longer hardcoded for one film.
# Resolved from --beat-durs, a "<script stem>_beat_durs.json" sidecar, the
# script's own `beat_durs` field, or the theoretical estimate, in that
# order (sticker_motion.resolve_beat_durs). The old hardcoded list was the
# faster-whisper measurement of the kuajing v10 Bear track; it now lives
# in scripts/跨境电商_beat_durs.json so this file stays film-agnostic.
# Boundaries are quantised to whole frames at 30fps from the CUMULATIVE
# durations, so the per-beat error does not accumulate.
BEAT_DURS, _DUR_SRC = sticker_motion.resolve_beat_durs(
    _SCRIPT, _ap_a.beat_durs or None, dur_of,
    script_path=_ap_a.script)
_BEAT_BOUNDS, _BEAT_BOUNDS_F, BEAT_FRAMES = sticker_motion.frame_bounds(BEAT_DURS)
WORD_TIMES = sticker_motion.load_word_times(_ap_a.word_times or None, _SCRIPT)
print("句长来源：%s（%d 句）" % (_DUR_SRC, len(BEAT_DURS)))

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

def add_segment(dur, cmd_args, filt, out_name, audio_texts=None, audio_durs=None, frames=None):
    global total, seg_idx
    out = WORK / out_name
    out_args = ["-filter_complex", filt, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30"]
    if frames:
        out_args += ["-frames:v", str(frames)]
    pipeline.run(["ffmpeg", "-y", "-v", "error"] + cmd_args + out_args + [str(out)])
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
# v12 (user 2026-11-06): max 2 stickers per screen — 1 centered, 2 one on
# each side. Each beat is its own screen (v11's group accumulation and its
# 3-4-in-a-row layout are retired). A beat starts with 1 main sticker
# centred, feet on the sand line; if the sentence has a second content
# element, its detail drops in at mid-beat, the main slides to the left
# slot and the detail lands on the right slot. Beats without a detail stay
# 1 sticker centred for the whole beat. The airplane (beat 2) still orbits
# the globe after it appears.
# v13 (user 2026-11-06 15:22: "我是说这个视频的声音" — the cross-border
# v12's sound/rhythm): v12 timed every beat to the THEORETICAL duration
# (len/4.5/1.1), but the real Bear voice (v10 track) drifts from it —
# measured with faster-whisper, beat 0's voice ends 0.79s before its
# subtitle leaves, beat 12's voice runs 0.51s past its subtitle change,
# max drift ~0.8s. v13 retimes every beat to the ACTUAL voice: each beat
# spans from its sentence's voice start to the next sentence's voice
# start (BEAT_DURS below), so subtitles/stickers change exactly when the
# voice changes sentence. Total beats 50.48s + 6s end cards = 56.48s,
# matching the v10 audio (56.44s).
for bi in range(len(BEATS)):
    sent, key, icon, accent = BEATS[bi]
    dur = BEAT_FRAMES[bi] / 30.0  # v13: frame-exact real voice timing
    # detail trigger (round 1): resolved from the beat's motion config
    # (trigger_time > word timestamp > estimated by keyword position >
    # mid-sentence default). `trig` is when the detail STARTS entering.
    trig, trig_src = sticker_motion.resolve_trigger(
        _SCRIPT["beats"][bi], bi, dur, WORD_TIMES)
    if trig_src != "default":
        print("句 %d 细节触发：%.2fs（%s）" % (bi + 1, trig, trig_src))
    # main sticker: 486px tall (45% of screen height), feet on sand line
    _sp = STICKER_DIR / ("sticker_%02d.png" % bi)
    _im = Image.open(_sp).convert("RGBA")
    _s = 486.0 / _im.height
    _mw, _mh = max(1, int(_im.width * _s)), max(1, int(_im.height * _s))
    card_w, card_h = _mw + 20, _mh + 20
    # detail sticker (the sentence's second content element)
    has_det = False
    det_w = det_h = None
    det_rot = None
    if DETAILS is not None and bi not in SKIP_DETAILS:
        det_src = DETAILS / ("detail_%02d.png" % bi)
        if det_src.exists():
            has_det = True
            _dim = Image.open(det_src)
            _sc = min(1.0, 320 / _dim.width, 250 / _dim.height)
            det_w, det_h = max(1, int(_dim.width * _sc)), max(1, int(_dim.height * _sc))
            det_path = WORK / ("detail_%02d.png" % bi)
            _dim.resize((det_w, det_h), Image.LANCZOS).save(det_path)
            if bi == 2:
                det_rot = int((det_w ** 2 + det_h ** 2) ** 0.5) + 2
    # slots: single -> centred at 960; pair -> main left, detail right,
    # the pair as a group centred about 960 with a 220px inner gap
    if has_det:
        _total = card_w + 220 + det_w
        _left = (W - _total) // 2
        main_cx_end = _left + card_w // 2
        det_cx = _left + card_w + 220 + det_w // 2
    else:
        main_cx_end = W // 2
        det_cx = None
    args, filt_parts, cur = [], [], "bg"
    args += ["-loop", "1", "-t", str(dur), "-i", str(bg_path)]
    filt_parts.append("[0:v]fps=30[bg]")
    inp = 1
    card_path = WORK / ("card_%02d.png" % bi)
    small_card(key, icon, accent, card_w, card_h, beat_idx=bi, explicit_scale=_s).save(card_path)
    args += ["-loop", "1", "-t", str(dur), "-i", str(card_path)]
    filt_parts.append("[%d:v]format=rgba[c0]" % inp)
    inp += 1
    det_inp = None
    if has_det:
        det_inp = inp
        args += ["-loop", "1", "-t", str(dur), "-i", str(det_path)]
        if bi == 2:
            # the airplane orbits the globe (user 2026-11-05): per-frame
            # rotation so its nose follows the flight path. t1 = when the
            # orbit starts (0.5s after it appears, i.e. after the fall).
            _t1 = trig + 0.5
            _ang = ("if(lt(t,%.2f),0,atan2(180*sin(1.5708*(t-%.2f)),-300*cos(1.5708*(t-%.2f)))-PI)"
                    % (_t1, _t1, _t1))
            filt_parts.append("[%d:v]format=rgba,rotate=a='%s':ow='hypot(iw,ih)':oh='hypot(iw,ih)':fillcolor=black@0[d0]" % (inp, _ang))
        else:
            filt_parts.append("[%d:v]format=rgba[d0]" % inp)
        inp += 1
    sub_path = WORK / ("sub_%02d.png" % bi)
    subtitle_image(sent).save(sub_path)
    args += ["-loop", "1", "-t", str(dur), "-i", str(sub_path)]
    sub_inp = inp
    filt_parts.append("[%d:v]format=rgba[s0]" % inp)
    inp += 1
    tmp = 0
    # main sticker entrance (round 1): horizontal slide-in only. The old
    # bi % 4 rotation (left / right / drop from top / rise from bottom)
    # is gone; direction comes from motion.enter (default left).
    # Smootherstep easing over 0.6s. No idle bob and no hop any more:
    # after entering, the sticker stays still on the sand line.
    enter_dir = sticker_motion.resolve_enter(_SCRIPT["beats"][bi])
    ex = sticker_motion.ff_enter_offset(enter_dir, start=0.0)
    # centre-x over time: centred until the detail is about to enter,
    # then slides to the left slot with smootherstep (0.6s), starting
    # 0.1s before the detail trigger so it is already moving when the
    # detail arrives. No hop.
    if has_det:
        cx_expr = sticker_motion.ff_slide(
            str(W // 2), str(main_cx_end),
            max(0.0, trig - sticker_motion.YIELD_LEAD),
            sticker_motion.YIELD_DUR)
    else:
        cx_expr = "%d" % (W // 2)
    x1 = "(%s)+(%s)-%d/2" % (cx_expr, ex, card_w)
    y1 = "%d" % (700 - _mh)
    nxt = "tmp%d" % tmp
    filt_parts.append("[%s][c0]overlay=x='%s':y='%s':enable='between(t,0,%s)'[%s]" % (cur, x1, y1, dur, nxt))
    cur, tmp = nxt, tmp + 1
    # detail sticker: drops in from above at the resolved trigger time
    # with an accelerating fall, then ONE small upward bounce (8px,
    # 0.35s) that never goes below the sand line and settles to still.
    # No continuous bob afterwards. The airplane (beat 2) is special:
    # after it appears it orbits the globe, one slow circle per 4s,
    # nose following the path.
    if has_det:
        _drop = sticker_motion.ff_drop(trig)
        _bounce = sticker_motion.ff_bounce(trig + sticker_motion.DROP_DUR)
        if bi == 2:
            _ocx, _ocy = main_cx_end, int(700 - _mh / 2)
            _S = det_rot
            _t1 = trig + 0.5
            _th = "1.5708+1.5708*(t-%.2f)" % _t1
            _dx = ("if(lt(t,%.2f),%d-%d/2,%d+300*cos(%s)-%d/2)"
                   % (_t1, _ocx, _S, _ocx, _th, _S))
            _dy = ("if(lt(t,%.2f),%d-(%s)-%d/2,%d-180*sin(%s)-%d/2)"
                   % (_t1, _ocy - 180, _drop, _S, _ocy, _th, _S))
        else:
            _dx = "%d-%d/2" % (det_cx, det_w)
            _dy = "%d-(%s)+(%s)" % (700 - det_h, _drop, _bounce)
        nxt = "tmp%d" % tmp
        filt_parts.append("[%s][d0]overlay=x='%s':y='%s':enable='between(t,%.2f,%s)'[%s]" % (cur, _dx, _dy, trig, dur, nxt))
        cur, tmp = nxt, tmp + 1
    nxt = "tmp%d" % tmp
    filt_parts.append("[%s][s0]overlay=x='(W-w)/2':y=775:enable='between(t,0,%s)'[%s]" % (cur, dur, nxt))
    cur, tmp = nxt, tmp + 1
    filt_parts[-1] = filt_parts[-1].rsplit("[", 1)[0] + "[v]"
    filt = ";".join(filt_parts)
    add_segment(dur, args, filt, "seg_beat%02d.mp4" % bi, audio_texts=[sent], audio_durs=[dur], frames=BEAT_FRAMES[bi])
    print("句 %d 完成：%s（%.1f 秒，%s）" % (bi + 1, key, dur, "主贴纸 + 细节" if has_det else "主贴纸居中"))

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
for bi in range(len(BEATS)):
    lines.append("句 %d：%s（%s）" % (bi + 1, BEATS[bi][0], BEATS[bi][1]))
lines += ["【结尾】" + t for t, _ in END_CARDS]
(OUT / "script.txt").write_text("\n".join(lines), encoding="utf-8")
print("完成：" + _SCRIPT.get("topic", _SCRIPT["title"]) + "·v13（按实际配音逐句对位） -> " + str(video) + "（%.1f 秒，%d 段）" % (total, len(seg_files)))
