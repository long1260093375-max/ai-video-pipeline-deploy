#!/usr/bin/env python3
"""HK offshore MG v13, 1080x1920 9:16, 5 beats, user voice, word-aligned.
v13 (user 2026-11-06: "动画切换和声音节奏不是很对得上", "根据声音
调整画面"): v12 timed the visuals to beat offsets, so the events
landed off the words — the S=0 badge popped ~1.7s before "免税",
the coin reached the bank ~0.9s before "账户", the order reached
HK ~0.7s after "香港公司". v13 retimes every visual event to the
key WORD in the user's recording (faster-whisper timestamps):
order->HK on "香港公司" (~1.30s), order->factory on "工厂"
(~4.36s), box->client on "海外" (~5.58s), coin->bank on "账户"
(~8.39s), stamp press on "离岸豁免" (~10.00s), badge pop on
"免税" (~12.52s). Inter-beat pads are removed (PADS 0) so the
video timeline IS the recording timeline; total 13.52s.
v12 (user 2026-11-06: "用你的聲音，按這個節奏重排"): the narration is
the user's own voice note (12.7s, read in one continuous take, ~2x
faster than the Bear TTS and with no pauses). The user read a
condensed 5-sentence version, not the 7 script sentences: the
"transfer to the factory" step is folded into the shipping beat.
So the film is re-cut to 5 beats with subtitles matching the user's
spoken words, and every animation is sped up ~0.6x (node entrance
0.3s, route draw 0.4s, flights 0.7-0.8s) to fit the faster beats.
The rectangular track, node corners and icons are unchanged from
v10/v11. Voice segments were cut from the user's mp3 by
faster-whisper word timestamps and live in OUT/work/voice_0*.mp3.
v11 (v10 fix, self-check): the box flying up the left edge in beat 3
ends right on top of the client label, so the client label is hidden
for beat 3 only (same approach as v9 beat 5). Otherwise identical to v10.
v10 (user 2026-11-06: "要整个形状是长方形，是视频的轨道"): the TRACK
is a rectangle, like the reference image — the 4 nodes sit on its
corners and the routes run along its edges. client TL, bank TR,
hk BR, factory BL. r4 top, r5 right, r2 bottom, r3 left; r1 (the
order, client->HK) is the single diagonal, passing behind the S=0
badge at the rectangle centre. Icons themselves unchanged (user:
"图标是ok的"). v9's rectangular stamp certificate is kept, and
its beat-5 label hiding is no longer needed (stamp sits at the
centre, clear of all labels).
v8 (user 2026-11-06: "还是参考这个，不要一个一个的"): back to the
closed-loop reference — all 4 nodes on screen at once, accumulating
per beat and staying, the 5 legs forming the complete loop (v5
structure). v6/v7's one-beat-at-a-time two-shots are retired. The
flying cargo is the cardboard box (v7 sticker set), not the big red
container. Also fixes the v5 r1/r2 flowing-dot misalignment.
v5 (user 2026-11-06): (1) text centered in its box via ink bbox;
(2) less crowded: icons smaller, nodes spread apart;
(3) closed loop: new r5 bank->HK drawn in beat 6 with the badge,
so every node has 2 connections and the circuit closes.
Arrows are NOT baked into bg: each route draws in AFTER its sticker
appears (0.8s easeOutCubic), dots flow only after the route is complete.
Flights start after their arrow completes. Otherwise identical to v2."
Per-frame PIL rendering (from make_hk_motion_test.py), NOT ffmpeg overlay.
Font B: Noto Sans CJK Bold for ALL text. No fade=t=in anywhere.
Easing + overshoot, breathing nodes, receive pulses + stars, arc flights,
flowing route dots, shrink-suck arrivals. Reuses stickers + voice files.
Cost: 0 new generations."""
import math, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline
from PIL import Image, ImageDraw, ImageFont

T0 = time.time()
BASE = Path(__file__).resolve().parent
STICK = BASE / "cutouts" / "hk_offshore_mg_flat_v9"
V1WORK = BASE / "output" / "hk-offshore-mg-9x16" / "work"
OUT = BASE / "output" / "hk-offshore-mg-9x16-v13"
WORK = OUT / "work"
FRAMES = WORK / "frames"
FRAMES.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)
W, H = 1080, 1920
FPS = 30
CONFIG = pipeline.load_yaml(BASE / "config.yaml", {})
BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

SUBS = [
    "每次我都用香港公司接海外的贸易订单。",
    "然后用大陆的工厂直接发货到海外。",
    "海外客户再把钱打到香港的账户上。",
    "然后再申请离岸豁免。",
    "这样在香港就能够合规免税。",
]
# user voice segments (faster-whisper word timestamps, 2026-11-06):
# [0.00-3.00] [3.00-5.80] [5.80-8.66] [8.66-10.34] [10.34-12.72]
VOICE_DURS = [3.00, 2.80, 2.86, 1.68, 2.38]
PADS = [0, 0, 0, 0, 0.8]  # v13: no gaps; beats butt up exactly like the user reads
DURS = [round(v + p, 3) for v, p in zip(VOICE_DURS, PADS)]
STARTS = [0.0]
for d in DURS[:-1]:
    STARTS.append(round(STARTS[-1] + d, 3))
TOTAL = sum(DURS)
N_FRAMES = int(round(TOTAL * FPS))
print(f"total {TOTAL:.3f}s, {N_FRAMES} frames, starts={STARTS}", flush=True)

# --- v13 arrow timing (word-aligned; video time == recording time) ---
# r1 draws 0.35-0.70 -> order flies 0.70-1.30, arrives on "香港公司"
# r2 draws 3.41-3.76 -> order flies 3.76-4.36, arrives on "工厂"
# r3 draws 4.53-4.88 -> box flies 4.88-5.58, arrives on "海外"
# r4 draws 7.44-7.79 -> coin flies 7.79-8.39, arrives on "账户"
# r5 draws 12.10-12.45 -> badge pops 12.52, on "免税"
# v10 rectangular track: corners client TL (260,400), bank TR (850,400),
# hk BR (850,1360), factory BL (260,1360); centre (555,880).
ROUTE_DUR = 0.35
ROUTE_DEFS = {
    "r1": {"pts": [(420, 550), (770, 1190)], "tip": (770, 1190), "angle": 61, "col": (90, 130, 180), "draw_start": STARTS[0]+0.35, "dur": ROUTE_DUR},
    "r2": {"pts": [(770, 1360), (490, 1360)], "tip": (490, 1360), "angle": 180, "col": (90, 130, 180), "draw_start": STARTS[1]+0.41, "dur": ROUTE_DUR},
    "r3": {"pts": [(260, 1200), (260, 550)], "tip": (260, 550), "angle": -90, "col": (60, 140, 90), "draw_start": STARTS[1]+1.53, "dur": ROUTE_DUR},
    "r4": {"pts": [(430, 400), (690, 400)], "tip": (690, 400), "angle": 0, "col": (180, 130, 40), "draw_start": STARTS[2]+1.64, "dur": ROUTE_DUR},
    "r5": {"pts": [(850, 630), (850, 1190)], "tip": (850, 1190), "angle": 90, "col": (180, 130, 40), "draw_start": STARTS[4]+1.76, "dur": ROUTE_DUR},
}
for _r in ROUTE_DEFS.values():
    _r["draw_end"] = _r["draw_start"] + _r["dur"]
print(f"arrow draws: " + ", ".join(f"{k} {v['draw_start']:.3f}-{v['draw_end']:.3f}" for k, v in ROUTE_DEFS.items()), flush=True)

def _truncate_pts(pts, frac):
    if frac <= 0:
        return []
    total = sum(math.hypot(b[0]-a[0], b[1]-a[1]) for a, b in zip(pts[:-1], pts[1:]))
    target = total * max(0.0, min(1.0, frac))
    out = [pts[0]]
    acc = 0.0
    for a, b in zip(pts[:-1], pts[1:]):
        seg = math.hypot(b[0]-a[0], b[1]-a[1])
        if acc + seg >= target:
            u = (target - acc) / seg if seg else 0
            out.append((a[0]+(b[0]-a[0])*u, a[1]+(b[1]-a[1])*u))
            return out
        out.append(b)
        acc += seg
    return out


def bold(size):
    return ImageFont.truetype(BOLD, size, index=2)  # SC, not JP (user 2026-11-05)

# --- easing ---
def ease_in_out_cubic(u):
    u = max(0.0, min(1.0, u))
    if u < 0.5:
        return 4*u*u*u
    return 1 - ((-2*u+2)**3)/2
def ease_out_cubic(u):
    u = max(0.0, min(1.0, u))
    return 1 - (1-u)**3
def ease_out_back(u):
    u = max(0.0, min(1.0, u))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3*(u-1)**3 + c1*(u-1)**2
def lerp(a, b, u):
    return a + (b-a)*u
def bezier(p0, p1, p2, u):
    return (lerp(lerp(p0[0], p1[0], u), lerp(p1[0], p2[0], u), u),
            lerp(lerp(p0[1], p1[1], u), lerp(p1[1], p2[1], u), u))

# --- assets ---
def trim_resize(src, target_h):
    im = Image.open(src).convert("RGBA")
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    s = target_h / im.height
    return im.resize((max(1, int(im.width*s)), target_h), Image.LANCZOS)

def dashed_line(d, pts, fill, width=6, dash=22, gap=14):
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        L = math.hypot(x1-x0, y1-y0)
        n = max(1, int(L/(dash+gap)))
        for k in range(n):
            t0, t1 = k/n, (k + dash/(dash+gap))/n
            ax, ay = x0+(x1-x0)*t0, y0+(y1-y0)*t0
            bx, by = x0+(x1-x0)*t1, y0+(y1-y0)*t1
            d.line([(ax, ay), (bx, by)], fill=fill, width=width)

def arrowhead(d, tip, angle_deg, fill, size=22):
    a = math.radians(angle_deg)
    p1 = (tip[0]-size*math.cos(a-0.45), tip[1]-size*math.sin(a-0.45))
    p2 = (tip[0]-size*math.cos(a+0.45), tip[1]-size*math.sin(a+0.45))
    d.polygon([tip, p1, p2], fill=fill)

def bg_image():
    top, bot = (234, 242, 251), (255, 255, 255)
    img = Image.new("RGB", (W, H), bot)
    d = ImageDraw.Draw(img)
    for y in range(H):
        f = y/H
        d.line([(0, y), (W, y)], fill=tuple(int(top[i]+(bot[i]-top[i])*f) for i in range(3)))
    for (x0, y0, x1, y1, col) in [(60, 60, 300, 220, (210, 228, 245)), (820, 1500, 1060, 1700, (215, 232, 246))]:
        d.ellipse([x0, y0, x1, y1], fill=col)
    # v3: NO routes baked into bg. Routes are drawn per-frame below,
    # only after their destination sticker has appeared.
    fade = Image.new("L", (W, 380), 0)
    fd = ImageDraw.Draw(fade)
    for y in range(380):
        fd.line([(0, y), (W, y)], fill=int(120*(y/380)**1.5))
    dark = Image.new("RGBA", (W, 380), (10, 20, 40, 255))
    img = img.convert("RGBA")
    img.paste(dark, (0, 1540), fade)
    return img.convert("RGB")

def label_image(text):
    f = bold(36)
    tmp = Image.new("RGBA", (10, 10))
    d0 = ImageDraw.Draw(tmp)
    tw = d0.textlength(text, font=f)
    img = Image.new("RGBA", (int(tw)+36, 58), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, img.width-1, img.height-1], radius=29, fill=(255, 255, 255, 235), outline=(150, 170, 200, 255), width=2)
    # v5: center the ink bbox, not the font em box (CJK ascent skews it)
    bb = d.textbbox((0, 0), text, font=f)
    d.text(((img.width-(bb[2]-bb[0]))/2 - bb[0], (img.height-(bb[3]-bb[1]))/2 - bb[1]), text, font=f, fill=(51, 65, 85))
    return img

def subtitle_image(text):
    # adaptive: keep single line; Bold is wider than Regular
    for size in (56, 52, 48):
        font = bold(size)
        tmp = Image.new("RGBA", (10, 10))
        d0 = ImageDraw.Draw(tmp)
        lines = pipeline.wrap_text(d0, text, font, 1020)
        if len(lines) == 1:
            break
    print(f"subtitle size {size} lines={len(lines)}: {text}", flush=True)
    lh = int(size*1.36)
    img = Image.new("RGBA", (1040, lh+20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bb = d.textbbox((0, 0), lines[0], font=font, stroke_width=3)
    d.text(((1040-(bb[2]-bb[0]))/2 - bb[0], (img.height-(bb[3]-bb[1]))/2 - bb[1]), lines[0], font=font, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
    return img

def coin_image():
    img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, 192, 192], fill=(245, 180, 40), outline=(200, 140, 20), width=6)
    d.ellipse([28, 28, 172, 172], outline=(255, 220, 120), width=4)
    f = bold(110)
    d.text((100, 100), "$", font=f, fill=(255, 255, 255), anchor="mm", stroke_width=2, stroke_fill=(180, 120, 10))
    return img

def badge_image():
    f = bold(96)
    tmp = Image.new("RGBA", (10, 10))
    d0 = ImageDraw.Draw(tmp)
    txt = "S = 0"
    tw = d0.textlength(txt, font=f)
    img = Image.new("RGBA", (int(tw)+220, 140), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, img.width-1, img.height-1], radius=70, fill=(255, 255, 255, 245), outline=(34, 197, 94, 255), width=6)
    # v5: text was sitting low (CJK ascent 1.16em); center the ink bbox
    # in the text zone (left of the check circle) on both axes
    cx = img.width - 80
    bb = d.textbbox((0, 0), txt, font=f)
    zone_w = cx - 42 - 30
    d.text((30 + (zone_w-(bb[2]-bb[0]))/2 - bb[0], (140-(bb[3]-bb[1]))/2 - bb[1]), txt, font=f, fill=(22, 163, 74))
    d.ellipse([cx-42, 28, cx+42, 112], fill=(34, 197, 94))
    f2 = bold(64)
    d.text((cx, 70), "✓", font=f2, fill=(255, 255, 255), anchor="mm")
    return img

BG = bg_image()
BG.save(WORK/"bg.png")
client_im = trim_resize(STICK/"sticker_00.png", 320)
hk_im = trim_resize(STICK/"sticker_01.png", 320)
bank_im = trim_resize(STICK/"sticker_03.png", 290)
factory_im = trim_resize(STICK/"sticker_02.png", 300)
order_im = trim_resize(STICK/"sticker_04.png", 170)
cont_im = trim_resize(STICK/"sticker_05.png", 260)
stamp_im = trim_resize(STICK/"sticker_06.png", 260)
coin_im = coin_image()
badge_im = badge_image()
labels = {n: label_image(t) for n, t in
          [("client", "海外客户"), ("hk", "香港公司"), ("bank", "银行账户"), ("factory", "大陆工厂")]}
subs = [subtitle_image(s) for s in SUBS]

NODES = {
    "client": {"im": client_im, "cx": 260, "cy": 400, "first_t": STARTS[0], "enter": "top", "breath_p": 2.8, "phase": 0.0, "bob_p": 3.0},
    "hk": {"im": hk_im, "cx": 850, "cy": 1360, "first_t": STARTS[0], "enter": "bottom", "breath_p": 3.4, "phase": 1.3, "bob_p": 3.6},
    "factory": {"im": factory_im, "cx": 260, "cy": 1360, "first_t": STARTS[1], "enter": "left", "breath_p": 3.0, "phase": 2.6, "bob_p": 3.2},
    "bank": {"im": bank_im, "cx": 850, "cy": 400, "first_t": STARTS[2], "enter": "right", "breath_p": 3.2, "phase": 0.7, "bob_p": 3.8},
}
# (node, time, amplitude) receive/departure pulses
PULSES = [
    ("hk", ROUTE_DEFS["r1"]["draw_end"]+0.6, 0.12),   # order arrives HK on "香港公司" 1.30
    ("hk", ROUTE_DEFS["r2"]["draw_end"], 0.06),       # order departs HK
    ("factory", ROUTE_DEFS["r2"]["draw_end"]+0.6, 0.12),  # order arrives factory on "工厂" 4.36
    ("factory", ROUTE_DEFS["r3"]["draw_end"], 0.06),  # container departs factory
    ("client", ROUTE_DEFS["r3"]["draw_end"]+0.7, 0.12),  # container arrives client on "海外" 5.58
    ("bank", ROUTE_DEFS["r4"]["draw_end"]+0.6, 0.12),  # coin arrives bank on "账户" 8.39
    ("hk", STARTS[3]+1.34, 0.08),           # stamp press on "离岸豁免" 10.00
    ("hk", STARTS[4]+2.18, 0.08),           # badge pop on "免税" 12.52
]
STAR_EVENTS = [("hk", ROUTE_DEFS["r1"]["draw_end"]+0.6), ("factory", ROUTE_DEFS["r2"]["draw_end"]+0.6),
               ("client", ROUTE_DEFS["r3"]["draw_end"]+0.7), ("bank", ROUTE_DEFS["r4"]["draw_end"]+0.6)]
# flights: timed list (v12: 4 flights across 5 beats; beat 1 carries
# two — order HK->factory, then box factory->client). Each flight waits
# bobbing at its origin from wait_from, flies start->arrive, then
# shrink-sucks into its destination over 0.15s.
ORDER_B1 = ((440, 490), (580, 880), (770, 1190))   # diagonal TL->BR
ORDER_B2 = ((770, 1360), (630, 1360), (490, 1360))   # bottom edge BR->BL
COIN_B4 = ((430, 400), (560, 400), (690, 400))   # top edge TL->TR
FLIGHTS = [
    {"kind": "order", "ctrl": ORDER_B1, "start": ROUTE_DEFS["r1"]["draw_end"], "dur": 0.6,
     "wait_pos": (440, 490), "wait_from": 0.1},
    {"kind": "order", "ctrl": ORDER_B2, "start": ROUTE_DEFS["r2"]["draw_end"], "dur": 0.6,
     "wait_pos": (770, 1190), "wait_from": STARTS[1]},
    {"kind": "container", "start": ROUTE_DEFS["r3"]["draw_end"], "dur": 0.7,
     "wait_pos": (260, 1200), "wait_from": ROUTE_DEFS["r2"]["draw_end"]+0.6},
    {"kind": "coin", "ctrl": COIN_B4, "start": ROUTE_DEFS["r4"]["draw_end"], "dur": 0.6,
     "wait_pos": (430, 400), "wait_from": STARTS[2]+1.10},
]
for fl in FLIGHTS:
    fl["arrive"] = fl["start"] + fl["dur"]

def paste_transformed(frame, im, cx, cy, scale, angle_deg, alpha=1.0):
    nw = max(1, int(im.width*scale)); nh = max(1, int(im.height*scale))
    r = im.resize((nw, nh), Image.LANCZOS)
    if abs(angle_deg) > 0.01:
        r = r.rotate(angle_deg, resample=Image.BICUBIC, expand=False)
    if alpha < 1.0:
        a = r.split()[3].point(lambda v: int(v*alpha))
        r.putalpha(a)
    frame.paste(r, (int(cx - r.width/2), int(cy - r.height/2)), r)
    return r.width, r.height

def draw_star(d, cx, cy, r, fill):
    pts = []
    for i in range(10):
        ang = -math.pi/2 + i*math.pi/5
        rr = r if i % 2 == 0 else r*0.45
        pts.append((cx+rr*math.cos(ang), cy+rr*math.sin(ang)))
    d.polygon(pts, fill=fill)

def route_point(route, u):
    if route == "r1":
        return (lerp(420, 770, u), lerp(550, 1190, u))
    if route == "r2":
        return (lerp(770, 490, u), 1360)
    if route == "r3":
        return (260, lerp(1200, 550, u))
    if route == "r5":
        return (850, lerp(630, 1190, u))
    return (lerp(430, 690, u), 400)
ROUTES = [("r1", (90, 130, 180)), ("r2", (90, 130, 180)),
          ("r3", (60, 140, 90)), ("r4", (180, 130, 40)), ("r5", (180, 130, 40))]

for fi in range(N_FRAMES):
    t = fi / FPS
    beat = 4
    for b in range(5):
        if t < STARTS[b] + DURS[b]:
            beat = b
            break
    beat_start = STARTS[beat]
    lt = t - beat_start
    frame = BG.copy()
    d = ImageDraw.Draw(frame, "RGBA")

    # v3: routes draw in per-frame AFTER their sticker appears; dots only
    # after a route is fully drawn. Nothing at t=0.
    for rname, rdef in ROUTE_DEFS.items():
        if t < rdef["draw_start"]:
            continue
        prog = ease_out_cubic((t - rdef["draw_start"]) / rdef["dur"])
        if prog <= 0:
            continue
        sub = _truncate_pts(rdef["pts"], prog)
        if len(sub) >= 2:
            dashed_line(d, sub, rdef["col"])
        if prog >= 1.0:
            ap = ease_out_back(min((t - rdef["draw_end"]) / 0.15, 1.0))
            if ap > 0:
                tip, ang, col = rdef["tip"], rdef["angle"], rdef["col"]
                a = math.radians(ang)
                sz = 22 * ap
                p1 = (tip[0]-sz*math.cos(a-0.45), tip[1]-sz*math.sin(a-0.45))
                p2 = (tip[0]-sz*math.cos(a+0.45), tip[1]-sz*math.sin(a+0.45))
                d.polygon([tip, p1, p2], fill=col)
            for k in range(4):
                ph = (((t - rdef["draw_end"])*0.30 + k/4.0) % 1.0)
                dx, dy = route_point(rname, ph)
                r = 8 + 2*math.sin(2*math.pi*t*2 + k)
                d.ellipse([dx-r, dy-r, dx+r, dy+r], fill=rdef["col"] + (255,), outline=(255, 255, 255, 255), width=2)

    # nodes
    node_geom = {}
    for name, nd in NODES.items():
        if t < nd["first_t"]:
            continue
        since = t - nd["first_t"]
        eu = ease_out_back(min(since/0.25, 1.0))
        if nd["enter"] == "top":
            ex, ey = 0, -600*(1-eu)
        elif nd["enter"] == "left":
            ex, ey = -400*(1-eu), 0
        elif nd["enter"] == "right":
            ex, ey = 400*(1-eu), 0
        else:
            ex, ey = 0, 400*(1-eu)
        escale = 0.90 + 0.10*eu
        breath = 1.0 + 0.03*math.sin(2*math.pi*t/nd["breath_p"] + nd["phase"])
        bob = 8*math.sin(2*math.pi*t/nd["bob_p"] + nd["phase"])
        sway = 4*math.sin(2*math.pi*t/(nd["bob_p"]+1.1) + nd["phase"]*2)
        tilt = 1.2*math.sin(2*math.pi*t/4.1 + nd["phase"])
        scale = breath * escale
        cx = nd["cx"] + sway + ex
        cy = nd["cy"] + bob + ey
        if name == "client" and beat == 0 and 1.0 <= t <= 1.45:
            cy += 6*math.sin(math.pi*(t-1.0)/0.45)
        for (pn, pt, amp) in PULSES:
            if pn == name and pt <= t <= pt+0.5:
                scale *= 1.0 + amp*math.sin(math.pi*(t-pt)/0.5)
        w, h = paste_transformed(frame, nd["im"], cx, cy, scale, tilt)
        node_geom[name] = (cx, cy, w, h)
        if beat != 4 and not (beat == 1 and name == "client"):
            lab = labels[name]
            frame.paste(lab, (int(cx - lab.width/2), int(cy + h/2 + 14)), lab)
        for (sn, st) in STAR_EVENTS:
            if sn == name and st <= t <= st+0.9 and name in node_geom:
                p = (t-st)/0.9
                sr = (28*ease_out_back(min(p*2.5, 1.0))) * (1 - 0.4*max(0, p-0.5)/0.5)
                if sr > 2:
                    scx, scy = node_geom[name][0], node_geom[name][1]
                    draw_star(d, scx+160, scy-170, sr, (245, 180, 40, 255))

    # movers (v12): FLIGHTS list + stamp (beat 3) + badge (beat 4)
    for fl in FLIGHTS:
        if fl["wait_from"] <= t < fl["start"]:
            # waiting at origin: pop in over 0.2s, then gentle bob
            pop = ease_out_back(min((t-fl["wait_from"])/0.2, 1.0))
            sc = 0.5 + 0.5*pop
            bob = 4*math.sin(2*math.pi*t/3.4)
            if fl["kind"] == "order":
                ox, oy = fl["wait_pos"]
                paste_transformed(frame, order_im, ox, oy + bob, sc, 2*math.sin(2*math.pi*t/2.2))
            elif fl["kind"] == "container":
                paste_transformed(frame, cont_im, fl["wait_pos"][0], fl["wait_pos"][1] + bob, sc, 2*math.sin(2*math.pi*t/2.2))
            elif fl["kind"] == "coin":
                paste_transformed(frame, coin_im, fl["wait_pos"][0], fl["wait_pos"][1] + bob, sc, 0)
        elif fl["start"] <= t < fl["arrive"]:
            u = ease_in_out_cubic((t-fl["start"])/fl["dur"])
            if fl["kind"] == "container":
                x = 260
                y = 1200 - 650*u
                scale = 0.95 + 0.10*math.sin(math.pi*u)
                ang = 6*math.sin(u*math.pi*2)
                paste_transformed(frame, cont_im, x, y, scale, ang)
            elif fl["kind"] == "coin":
                for back, al in ((0.16, 0.35), (0.08, 0.6)):
                    ub = max(0.0, u-back)
                    bx, by = bezier(*fl["ctrl"], ub)
                    paste_transformed(frame, coin_im, bx, by, 0.75, 720*ub, alpha=al)
                x, y = bezier(*fl["ctrl"], u)
                paste_transformed(frame, coin_im, x, y, 0.9 + 0.2*math.sin(math.pi*u), 720*u)
            else:  # order bezier
                x, y = bezier(*fl["ctrl"], u)
                scale = 0.95 + 0.10*math.sin(math.pi*u)
                ang = 6*math.sin(u*math.pi*2)
                paste_transformed(frame, order_im, x, y, scale, ang)
        elif fl["arrive"] <= t < fl["arrive"]+0.15:
            p = (t-fl["arrive"])/0.15
            scale = max(1.05*(1-0.8*p), 0.2)
            alpha = 1.0-0.8*p
            if fl["kind"] == "container":
                sx, sy = lerp(260, 260, p), lerp(550, 400, p)
                paste_transformed(frame, cont_im, sx, sy, scale, 0, alpha=alpha)
            elif fl["kind"] == "coin":
                sx, sy = lerp(850, 850, p), lerp(400, 400, p)
                paste_transformed(frame, coin_im, sx, sy, scale, 720, alpha=alpha)
            else:
                ex_, ey_ = fl["ctrl"][2]
                ox = 14*math.sin(math.pi*min(p*1.4, 1.0))*(1-p)
                paste_transformed(frame, order_im, ex_+ox, ey_, scale, 0, alpha=alpha)
    if beat == 3:
        pop_t = beat_start + 0.64
        if t >= pop_t:
            if t < beat_start + DURS[3] - 0.15:
                p = min((t-pop_t)/0.3, 1.0)
                s = ease_out_back(p)
                scale = 0.5 + 0.5*s
                press_t = beat_start + 1.34
                if press_t <= t <= press_t+0.25:
                    pp = (t-press_t)/0.25
                    scale *= 1.0 - 0.12*math.sin(math.pi*pp) + 0.08*math.sin(math.pi*pp)*pp
                paste_transformed(frame, stamp_im, 555, 880 + 4*math.sin(2*math.pi*t/3.4), scale, 2*math.sin(2*math.pi*t/2.2))
            else:
                p = (t-(beat_start+DURS[3]-0.15))/0.15
                paste_transformed(frame, stamp_im, 555, 880, max(1.0-0.8*p, 0.2), 0, alpha=1.0-0.8*p)
    elif beat == 4:
        pop_t = beat_start + 2.18
        if t >= pop_t:
            p = min((t-pop_t)/0.35, 1.0)
            s = ease_out_back(p)
            scale = 0.8 + 0.25*s
            scale *= 1.0 + 0.02*math.sin(2*math.pi*t/3.0)
            paste_transformed(frame, badge_im, 555, 880, scale, 0)

    # subtitle slide-up + scale 0.96->1.0 over 0.25s
    sub = subs[beat]
    sp = min(lt/0.25, 1.0)
    se = ease_out_cubic(sp)
    sscale = 0.96 + 0.04*se
    sy_off = 20*(1-se)
    sw = max(1, int(sub.width*sscale)); sh = max(1, int(sub.height*sscale))
    sub_r = sub.resize((sw, sh), Image.LANCZOS)
    frame.paste(sub_r, (int((W-sw)/2), int(1660+sy_off)), sub_r)

    frame.convert("RGB").save(FRAMES/f"frame_{fi:04d}.png")
    if fi % 120 == 0:
        print(f"frame {fi}/{N_FRAMES} t={t:.2f} beat={beat+1} elapsed={time.time()-T0:.0f}s", flush=True)

print(f"frames done in {time.time()-T0:.0f}s", flush=True)

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FAILED:", r.stderr[-2000:], file=sys.stderr); sys.exit(1)

silent = WORK/"video_only.mp4"
run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", str(FRAMES/"frame_%04d.png"),
     "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS), str(silent)])
audios = []
for b in range(5):
    src = WORK/f"voice_{b:02d}.mp3"
    a = WORK/f"audio_{b:02d}.mp3"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af", f"apad=whole_dur={DURS[b]}",
         "-t", str(DURS[b]), "-q:a", "9", "-acodec", "libmp3lame", str(a)])
    audios.append(a)
alst = WORK/"audio_list.txt"
alst.write_text("".join(f"file '{a}'\n" for a in audios), encoding="utf-8")
audio = WORK/"audio.mp3"
run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(alst), "-c", "copy", str(audio)])
video = OUT/"video.mp4"
run(["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-i", str(audio), "-c", "copy", "-shortest", str(video)])
(OUT/"audio.mp3").write_bytes(audio.read_bytes())
print(f"done: {video} ({TOTAL:.1f}s, {N_FRAMES} frames) in {time.time()-T0:.0f}s", flush=True)
