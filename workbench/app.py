#!/usr/bin/env python3
"""Cutout science video workbench (v11-style films).

Run from this directory:
    python3 app.py
Then open http://127.0.0.1:5000

What it does: pick a style template, a cast, a voice and a font, then give it
a topic (or several, one per line) or your own copy. It drives the EXISTING
pipeline scripts as subprocesses -- it never reimplements rendering:
  topic -> generate_script_zhipu.py -> understanding table (you review it)
        -> generate_stickers_zhipu.py + rembg cut
        -> make_cutout_from_script.py --template <name>
You review the finished film, approve it, then export the mp4 (or a zip of
all approved films).

Layout and motion rules (one-row/pin rows, subtitle position, the airplane
orbit, SC subtitles) are series-wide and already live in the renderer; this
app does not re-decide them.

API keys come from environment variables only (ARK_API_KEY,
DOUBAO_TTS_API_KEY, ZHIPU_API_KEY). The settings page shows set/unset only
and never prints a key value. A step whose key is missing fails with a clear
message; a render that comes back silent is marked failed, never delivered
as a finished film.
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

WORKBENCH_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = WORKBENCH_DIR.parent
DATA_DIR = WORKBENCH_DIR / "data"
JOBS_DIR = DATA_DIR / "jobs"
JOBS_FILE = DATA_DIR / "jobs.json"
# Local deploy: rembg lives in this same venv (requirements.txt), so use
# the running interpreter; keep the old separate rembg_venv path when it
# exists (original VM layout).
_REMBG_VENV_PY = PIPELINE_ROOT / "tools" / "rembg_venv" / "bin" / "python"
REMBG_PY = _REMBG_VENV_PY if _REMBG_VENV_PY.exists() else Path(sys.executable)
REMBG_CUT = WORKBENCH_DIR / "rembg_cut.py"

sys.path.insert(0, str(PIPELINE_ROOT))
import pipeline as pipeline_mod
from template import list_templates, load_template

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
# RLock (not Lock): create_job holds the lock while logging, and log() /
# update_job() acquire it again. A plain Lock would deadlock the request.
_lock = threading.RLock()

# ---------------------------------------------------------------- voices
VOICES = [
    {"id": "doubao_xionger", "label": "熊二（豆包，卡通男声，1.1x）",
     "engine": "doubao", "speaker": "zh_male_xionger_uranus_bigtts", "rate": 10},
    {"id": "doubao_vv", "label": "vv（豆包，女声，1.1x）",
     "engine": "doubao", "speaker": "zh_female_vv_uranus_bigtts", "rate": 10},
    {"id": "doubao_peiqi", "label": "佩奇（豆包，女声，1.1x）",
     "engine": "doubao", "speaker": "zh_female_peiqi_uranus_bigtts", "rate": 10},
    {"id": "doubao_xiaoxue", "label": "小雪（豆包，女声，1.1x）",
     "engine": "doubao", "speaker": "zh_female_xiaoxue_uranus_bigtts", "rate": 10},
    {"id": "doubao_shuangkuaisisi", "label": "爽快思思（豆包，女声，1.1x）",
     "engine": "doubao", "speaker": "zh_female_shuangkuaisisi_uranus_bigtts", "rate": 10},
    {"id": "piper_huayan", "label": "花燕（Piper 离线，备用）",
     "engine": "piper", "speaker": "", "rate": 0},
    {"id": "none", "label": "无配音（仅画面测试）",
     "engine": "none", "speaker": "", "rate": 0},
]
VOICE_BY_ID = {v["id"]: v for v in VOICES}

# ---------------------------------------------------------------- fonts
FONT_PALETTE = [
    (59, 130, 246), (16, 185, 129), (245, 158, 11),
    (239, 68, 68), (139, 92, 246), (42, 165, 184),
]


def font_options():
    """Subtitle font choices. The renderer reads the font through
    pipeline.find_font, which honours PIPELINE_FONT_PATH when set; the
    workbench sets that variable per render subprocess (see render_job)."""
    cfg = pipeline_mod.load_yaml(PIPELINE_ROOT / "config.yaml", {})
    noto = pipeline_mod.find_font(cfg)
    fonts_dir = PIPELINE_ROOT / "fonts"
    opts = [
        {"id": "noto-sc", "label": "思源黑体 SC Bold（默认，简体字形正确）",
         "path": noto, "available": bool(noto)},
        {"id": "zcool-kuaile", "label": "站酷快乐体（圆润卡通；S 像 5）",
         "path": str(fonts_dir / "ZCOOLKuaiLe-Regular.ttf"),
         "available": (fonts_dir / "ZCOOLKuaiLe-Regular.ttf").exists()},
        {"id": "zcool-qingke", "label": "庆科黄油体（可能缺字）",
         "path": str(fonts_dir / "ZCOOLQingKeHuangYou-Regular.ttf"),
         "available": (fonts_dir / "ZCOOLQingKeHuangYou-Regular.ttf").exists()},
    ]
    return opts


FONT_BY_ID = {f["id"]: f for f in font_options()}

KEY_NAMES = ["ARK_API_KEY", "DOUBAO_TTS_API_KEY", "ZHIPU_API_KEY"]


def key_status():
    return {k: bool(os.environ.get(k)) for k in KEY_NAMES}


# ---------------------------------------------------------------- job store
def _load_jobs():
    if not JOBS_FILE.exists():
        return {}
    try:
        return json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_jobs(jobs):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = JOBS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(JOBS_FILE)


def get_job(job_id):
    with _lock:
        return _load_jobs().get(job_id)


def update_job(job_id, fn):
    with _lock:
        jobs = _load_jobs()
        job = jobs.get(job_id)
        if job is None:
            return None
        fn(job)
        job["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _save_jobs(jobs)
        return job


def new_job_id():
    return uuid.uuid4().hex[:12]


def job_dir(job_id):
    d = JOBS_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def log(job_id, msg):
    line = "%s %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    def _fn(job):
        job.setdefault("log", []).append(line)
        job["log"] = job["log"][-300:]
    update_job(job_id, _fn)
    print("[%s] %s" % (job_id, msg), flush=True)


def fail_job(job_id, stage, msg):
    log(job_id, "失败：%s" % msg)
    def _fn(job):
        job["status"] = "failed"
        job["stage"] = stage
        job["error"] = msg
    update_job(job_id, _fn)


def set_stage(job_id, status, stage):
    def _fn(job):
        job["status"] = status
        job["stage"] = stage
    update_job(job_id, _fn)


# ---------------------------------------------------------------- copy split
def split_copy(text):
    """Split pasted copy into short sentences (Chinese punctuation)."""
    parts = re.split(r"[。！？；\n]+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def build_script_json(title, beats, end_cards, topic=""):
    """beats: [{text, key}]. Fills char/color the way the script generator does.
    A beat's optional `motion` dict (enter / trigger_word / trigger_time)
    is carried through unchanged so the renderer can use it; the same
    goes for top-level `beat_durs` / `word_times` when the caller passes
    them via a `meta` beat (not used by the UI yet)."""
    out_beats = []
    for i, b in enumerate(beats):
        beat = {
            "text": b["text"],
            "key": b.get("key") or b["text"][:4],
            "char": b["text"][:1],
            "color": list(FONT_PALETTE[i % len(FONT_PALETTE)]),
        }
        if isinstance(b.get("motion"), dict):
            beat["motion"] = b["motion"]
        out_beats.append(beat)
    total = sum(len(b["text"]) for b in out_beats)
    groups = [[i, i + 1] for i in range(0, len(out_beats) - 1, 2)]
    if len(out_beats) % 2 == 1:
        groups.append([len(out_beats) - 1])
    return {
        "topic": topic or title,
        "title": title,
        "beats": out_beats,
        "groups": groups,
        "end_cards": end_cards,
        "sticker_prompts": [b["key"] for b in out_beats],
        "total_chars": total,
        "estimated_seconds": round(total / 4.5 + 9, 1),
    }


# ---------------------------------------------------------------- understanding draft
def parse_world_bible(text):
    """Best-effort parse of a template's world_bible.md.
    Returns (locations, characters): locations are place names, characters
    are {name, role, desc} dicts with the fixed English description."""
    locations = []
    characters = []
    # Locations: the bullets directly under the "固定地点" line. Stop at the
    # first non-bullet line, so later sections that merely mention 固定地点
    # (e.g. the prompt-template section) are not picked up.
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "固定地点" in line:
            for j in range(i + 1, len(lines)):
                m = re.match(r"\s*-\s*([^：:（(]+)[：:]", lines[j])
                if not m:
                    break
                locations.append(m.group(1).strip())
            break
    # characters: "### 1. 墨墨 —— 讲概念的老师" + quoted fixed description
    for m in re.finditer(
            r"###\s*\d+\.\s*(\S+)\s*——\s*([^\n]*)\n(.*?)(?=\n###|\n##|\Z)",
            text, re.S):
        name, role, body = m.group(1), m.group(2).strip(), m.group(3)
        dm = re.search(r'"([^"]+)"', body)
        characters.append({
            "name": name, "role": role,
            "desc": dm.group(1) if dm else "",
        })
    return locations, characters


SCENE_RULES = [
    (("钱", "成本", "价格", "买", "卖", "花", "省", "便宜", "贵"), "杂货铺"),
    (("寄", "快递", "订单", "下单"), "邮局"),
    (("仓库", "发货", "运", "物流", "船", "海外"), "港口"),
    (("规则", "合规", "法律", "税", "账", "算"), "图书馆"),
]
SYMBOL_RULES = [
    (("钱", "成本", "价格"), "金币"),
    (("税",), "% 符号"),
    (("订单",), "文件"),
    (("退",), "回头箭头"),
]


def _pick(rules, text, default):
    for keywords, value in rules:
        if any(k in text for k in keywords):
            return value
    return default


def draft_understanding(script, template_name):
    """Rule-based draft understanding table from a script JSON and the
    template's world bible. No text model is called. The user reviews and
    edits this table before any image is generated."""
    tpl = load_template(template_name)
    bible = tpl["world_bible_path"].read_text(encoding="utf-8")
    locations, characters = parse_world_bible(bible)
    style = tpl.get("image_style", "")
    rows = []
    for i, beat in enumerate(script["beats"]):
        text = beat["text"]
        key = beat.get("key", "")
        scene_hint = _pick(SCENE_RULES, text, "学校")
        scene = next((loc for loc in locations if scene_hint in loc),
                     locations[0] if locations else scene_hint)
        symbol = _pick(SYMBOL_RULES, text, "")
        prompt = "%s，%s，%s" % (key, scene, style) if key else text
        rows.append({
            "beat": i, "text": text, "key": key, "scene": scene,
            "object": key, "symbol": symbol, "prompt": prompt,
        })
    return {"template": template_name, "locations": locations,
            "characters": characters, "rows": rows}


# ---------------------------------------------------------------- subprocess
def run_cmd(job_id, cmd, env_extra=None, cwd=None):
    """Run a pipeline script as a subprocess, streaming its output into the
    job log. Returns (returncode, stdout)."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    log(job_id, "运行：%s" % " ".join(str(c) for c in cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          cwd=str(cwd or PIPELINE_ROOT), env=env, timeout=3600)
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.strip().splitlines()[-25:]:
        log(job_id, "  " + line)
    return proc.returncode, out


def audio_mean_volume(video_path):
    """Mean volume in dB of a rendered mp4, or None when unreadable."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(video_path),
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, timeout=300)
    m = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", proc.stderr or "")
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------- job engine
def advance_job(job_id):
    """Run the next phases of a job until it pauses for the user, finishes,
    or fails. Runs in a background thread; each user action re-enters here."""
    job = get_job(job_id)
    if job is None:
        return
    if job["status"] in ("running",):
        return
    jdir = job_dir(job_id)
    set_stage(job_id, "running", job.get("stage") or "开始")
    try:
        _advance(job_id, job, jdir)
    except Exception as exc:  # noqa: BLE001 - surface any failure on the job
        fail_job(job_id, "异常", "内部错误：%s" % exc)


def _advance(job_id, job, jdir):
    mode = job["mode"]
    tpl_name = job["template"]
    script_path = jdir / "script.json"

    # -- phase 1: script (topic mode only; copy/existing already have one)
    if mode == "topic" and not script_path.exists():
        if not os.environ.get("ZHIPU_API_KEY"):
            fail_job(job_id, "写稿",
                     "缺少 ZHIPU_API_KEY：写稿需要智谱 key，请在启动终端里 "
                     "export ZHIPU_API_KEY=... 后重启本程序。")
            return
        set_stage(job_id, "running", "写稿")
        rc, _ = run_cmd(job_id, [
            sys.executable, str(PIPELINE_ROOT / "generate_script_zhipu.py"),
            "--topic", job["topic"], "--model", "glm-4.6",
            "--out", str(script_path)])
        if rc != 0 or not script_path.exists():
            fail_job(job_id, "写稿", "写稿失败（脚本生成器退出码 %s），请看日志。" % rc)
            return
        log(job_id, "写稿完成：%s" % script_path.name)

    if mode == "existing" and not script_path.exists():
        fail_job(job_id, "写稿", "找不到已有脚本：%s" % job.get("script_source"))
        return

    script = json.loads(script_path.read_text(encoding="utf-8"))
    n_beats = len(script["beats"])
    log(job_id, "脚本：%d 句，%s" % (n_beats, script.get("title", "")))

    # -- phase 2: understanding table (draft, then wait for the user)
    if mode != "existing" and not (jdir / "understanding.json").exists():
        set_stage(job_id, "running", "理解表")
        draft = draft_understanding(script, tpl_name)
        (jdir / "understanding_draft.json").write_text(
            json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        set_stage(job_id, "awaiting_understanding", "等你审理解表")
        log(job_id, "理解表草稿已生成，等你审阅（%d 行）。" % len(draft["rows"]))
        return

    # -- phase 3: stickers (existing mode reuses the given sticker dir)
    stickers_dir = jdir / "stickers"
    if mode != "existing":
        if not stickers_dir.exists() or not list(stickers_dir.glob("sticker_*.png")):
            if not os.environ.get("ZHIPU_API_KEY"):
                fail_job(job_id, "生图",
                         "缺少 ZHIPU_API_KEY：生图需要智谱 key，请在启动终端里 "
                         "export ZHIPU_API_KEY=... 后重启本程序。")
                return
            set_stage(job_id, "running", "生图")
            understanding = json.loads((jdir / "understanding.json").read_text(encoding="utf-8"))
            prompts = [{"key": r["key"], "prompt": r["prompt"]}
                       for r in understanding["rows"]]
            prompts_path = jdir / "prompts.json"
            prompts_path.write_text(json.dumps(prompts, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
            raw_dir = jdir / "raw"
            flood_dir = jdir / "stickers_flood"
            rc, _ = run_cmd(job_id, [
                sys.executable, str(PIPELINE_ROOT / "generate_stickers_zhipu.py"),
                "--prompts", str(prompts_path), "--model", "cogview-4",
                "--template", tpl_name,
                "--out-dir", str(flood_dir), "--raw-dir", str(raw_dir)])
            if rc != 0 or not list(raw_dir.glob("*.png")):
                fail_job(job_id, "生图", "生图失败（退出码 %s），请看日志。" % rc)
                return
            log(job_id, "生图完成，开始 rembg 抠图。")
            rc, _ = run_cmd(job_id, [
                str(REMBG_PY), str(REMBG_CUT), str(raw_dir), str(stickers_dir)])
            if rc != 0:
                fail_job(job_id, "抠图", "rembg 抠图失败（退出码 %s），请看日志。" % rc)
                return
            made = sorted(stickers_dir.glob("sticker_*.png"))
            if len(made) != n_beats:
                fail_job(job_id, "抠图",
                         "贴纸数量不对：应有 %d 张，实际 %d 张。" % (n_beats, len(made)))
                return
            log(job_id, "贴纸就绪：%d 张。" % len(made))
    else:
        stickers_dir = Path(job["stickers_dir"])
        if not stickers_dir.is_absolute():
            stickers_dir = PIPELINE_ROOT / stickers_dir
        if not list(stickers_dir.glob("sticker_*.png")):
            fail_job(job_id, "生图", "贴纸目录里没有 sticker_XX.png：%s" % stickers_dir)
            return

    # -- phase 4: render
    set_stage(job_id, "running", "渲染")
    voice = VOICE_BY_ID[job["voice"]]
    if voice["engine"] == "doubao" and not os.environ.get("DOUBAO_TTS_API_KEY"):
        log(job_id, "提醒：DOUBAO_TTS_API_KEY 未设置，豆包配音可能失败；"
                    "渲完会验音，无声会直接判失败。")
    font = FONT_BY_ID.get(job["font"]) or FONT_BY_ID["noto-sc"]
    env_extra = {}
    if font.get("path"):
        env_extra["PIPELINE_FONT_PATH"] = font["path"]
    render_dir = jdir / "render"
    cmd = [sys.executable, str(PIPELINE_ROOT / "make_cutout_from_script.py"),
           "--script", str(script_path), "--stickers", str(stickers_dir),
           "--out", str(render_dir), "--tts", voice["engine"],
           "--background", "ai", "--template", tpl_name]
    if voice["engine"] == "doubao":
        cmd += ["--speaker", voice["speaker"], "--speech-rate", str(voice["rate"])]
    if job.get("details_dir"):
        cmd += ["--details", job["details_dir"]]
    if job.get("skip_details"):
        cmd += ["--skip-details", job["skip_details"]]
    rc, _ = run_cmd(job_id, cmd, env_extra=env_extra)
    video = render_dir / "video.mp4"
    if rc != 0 or not video.exists():
        fail_job(job_id, "渲染", "渲染失败（退出码 %s），请看日志。" % rc)
        return
    bg = render_dir / "work" / "bg.png"
    if bg.exists():
        log(job_id, "背景 MD5：%s" % hashlib.md5(bg.read_bytes()).hexdigest())
    if voice["engine"] != "none":
        vol = audio_mean_volume(video)
        log(job_id, "配音平均音量：%s dB" % (vol if vol is not None else "读不到"))
        if vol is None or vol <= -60:
            fail_job(job_id, "验音",
                     "渲染出的成片是无声的（平均音量 %s dB）：豆包配音没有返回音频，"
                     "请检查 DOUBAO_TTS_API_KEY 或火山账号状态，确认后再重试。"
                     % (vol if vol is not None else "读不到"))
            return
    set_stage(job_id, "awaiting_review", "等你审片")
    log(job_id, "渲染完成，等你审片。")


def start_advance(job_id):
    threading.Thread(target=advance_job, args=(job_id,), daemon=True).start()


def create_job(data):
    """Validate the new-episode form and create one job per topic."""
    mode = data.get("mode", "topic")
    template = data.get("template", "coral-bay")
    if template not in list_templates():
        raise ValueError("未知的模板：%s" % template)
    voice_id = data.get("voice", "doubao_xionger")
    if voice_id not in VOICE_BY_ID:
        raise ValueError("未知的配音：%s" % voice_id)
    font_id = data.get("font", "noto-sc")
    if font_id not in FONT_BY_ID:
        raise ValueError("未知的字体：%s" % font_id)
    characters = data.get("characters") or []
    titles = []
    if mode == "topic":
        topic = (data.get("topic") or "").strip()
        if not topic:
            raise ValueError("请填写一个选题。")
        titles = [(topic, {"mode": "topic", "topic": topic})]
    elif mode == "batch":
        topics = [t.strip() for t in (data.get("topics") or "").splitlines() if t.strip()]
        if not topics:
            raise ValueError("请至少填写一个选题，一行一个。")
        if len(topics) > 20:
            raise ValueError("批量一次最多 20 个选题。")
        titles = [(t, {"mode": "topic", "topic": t}) for t in topics]
    elif mode == "copy":
        title = (data.get("title") or "").strip()
        text = (data.get("copy") or "").strip()
        if not text:
            raise ValueError("请粘贴文案。")
        beats = split_copy(text)
        if len(beats) < 2:
            raise ValueError("文案至少要拆成 2 句。")
        if not title:
            title = beats[0][:12]
        titles = [(title, {"mode": "copy", "title": title, "draft_beats": beats})]
    elif mode == "existing":
        script_source = (data.get("script_source") or "").strip()
        stickers_dir = (data.get("stickers_dir") or "").strip()
        if not script_source or not stickers_dir:
            raise ValueError("已有脚本模式需要脚本文件和贴纸目录。")
        src = Path(script_source)
        if not src.is_absolute():
            src = PIPELINE_ROOT / src
        if not src.exists():
            raise ValueError("找不到脚本文件：%s" % src)
        title = src.stem
        titles = [(title, {"mode": "existing", "title": title,
                           "script_source": str(src),
                           "stickers_dir": stickers_dir,
                           "details_dir": (data.get("details_dir") or "").strip(),
                           "skip_details": (data.get("skip_details") or "").strip()})]
    else:
        raise ValueError("未知的模式：%s" % mode)

    batch_group = uuid.uuid4().hex[:8] if len(titles) > 1 else None
    created = []
    with _lock:
        jobs = _load_jobs()
        for title, extra in titles:
            job_id = new_job_id()
            job = {
                "id": job_id, "title": title, "batch_group": batch_group,
                "template": template, "characters": characters,
                "voice": voice_id, "font": font_id,
                "status": "queued", "stage": "新建",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "log": [], "error": "",
            }
            job.update(extra)
            jobs[job_id] = job
            created.append(job)
            jdir = job_dir(job_id)
            if mode == "copy":
                (jdir / "copy.txt").write_text(data.get("copy") or "", encoding="utf-8")
            if mode == "existing":
                shutil.copy(job["script_source"], jdir / "script.json")
            log(job_id, "新建任务：%s（模板 %s，配音 %s）"
                % (title, template, VOICE_BY_ID[voice_id]["label"]))
        _save_jobs(jobs)
    for job in created:
        if job["mode"] == "copy":
            # copy mode pauses for the user to edit the split beats first
            set_stage(job["id"], "awaiting_beats", "等你改分句")
        else:
            start_advance(job["id"])
    return created


# ---------------------------------------------------------------- routes
@app.route("/")
def index():
    scripts = [{"name": p.name, "path": "scripts/%s" % p.name}
               for p in sorted((PIPELINE_ROOT / "scripts").glob("*.json"))]
    return render_template(
        "index.html",
        templates=list_templates(),
        voices=VOICES,
        fonts=font_options(),
        keys=key_status(),
        scripts=scripts,
    )


@app.route("/api/templates/<name>/characters")
def template_characters(name):
    try:
        tpl = load_template(name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    chars_dir = tpl["characters_dir"]
    files = sorted(p.name for p in chars_dir.glob("*.png")) if chars_dir.exists() else []
    return jsonify({"template": name,
                    "characters": [{"file": f,
                                    "url": "/api/template_file/%s/characters/%s" % (name, f)}
                                   for f in files]})


@app.route("/api/template_file/<name>/characters/<path:fname>")
def template_file(name, fname):
    try:
        tpl = load_template(name)
    except ValueError:
        abort(404)
    path = (tpl["characters_dir"] / fname).resolve()
    if not str(path).startswith(str(tpl["characters_dir"].resolve())):
        abort(403)
    if not path.exists():
        abort(404)
    return send_file(path, mimetype="image/png")


@app.route("/api/settings")
def settings():
    return jsonify({"keys": key_status()})


@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    jobs = _load_jobs()
    ordered = sorted(jobs.values(), key=lambda j: j["created_at"], reverse=True)
    return jsonify({"jobs": ordered})


@app.route("/api/jobs", methods=["POST"])
def api_create_job():
    try:
        created = create_job(request.get_json(force=True) or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"jobs": [{"id": j["id"], "title": j["title"]} for j in created]})


@app.route("/api/jobs/<job_id>", methods=["GET"])
def api_get_job(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "找不到任务"}), 404
    detail = dict(job)
    jdir = JOBS_DIR / job_id
    if (jdir / "script.json").exists():
        detail["script"] = json.loads((jdir / "script.json").read_text(encoding="utf-8"))
    if (jdir / "understanding_draft.json").exists():
        detail["understanding_draft"] = json.loads(
            (jdir / "understanding_draft.json").read_text(encoding="utf-8"))
    if (jdir / "understanding.json").exists():
        detail["understanding"] = json.loads(
            (jdir / "understanding.json").read_text(encoding="utf-8"))
    detail["has_video"] = (jdir / "render" / "video.mp4").exists()
    return jsonify(detail)


@app.route("/api/jobs/<job_id>/beats", methods=["POST"])
def api_submit_beats(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "找不到任务"}), 404
    if job["status"] != "awaiting_beats":
        return jsonify({"error": "这个任务现在不在改分句阶段。"}), 400
    data = request.get_json(force=True) or {}
    beats = [b for b in data.get("beats", []) if (b.get("text") or "").strip()]
    if len(beats) < 2:
        return jsonify({"error": "至少要 2 句。"}), 400
    title = (data.get("title") or job["title"]).strip()
    end_cards = data.get("end_cards") or ["谢谢观看", "下期再见"]
    script = build_script_json(title, beats, end_cards[:2], topic=job.get("topic", ""))
    (job_dir(job_id) / "script.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    log(job_id, "分句已确认：%d 句。" % len(beats))
    start_advance(job_id)
    return jsonify({"ok": True})


@app.route("/api/jobs/<job_id>/understanding", methods=["POST"])
def api_submit_understanding(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "找不到任务"}), 404
    if job["status"] != "awaiting_understanding":
        return jsonify({"error": "这个任务现在不在审理解表阶段。"}), 400
    data = request.get_json(force=True) or {}
    rows = data.get("rows")
    if not rows:
        return jsonify({"error": "理解表是空的。"}), 400
    (job_dir(job_id) / "understanding.json").write_text(
        json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    log(job_id, "理解表已确认（%d 行），开始生图。" % len(rows))
    start_advance(job_id)
    return jsonify({"ok": True})


@app.route("/api/jobs/<job_id>/approve", methods=["POST"])
def api_approve(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "找不到任务"}), 404
    if job["status"] != "awaiting_review":
        return jsonify({"error": "这个任务现在没有可审的成片。"}), 400
    set_stage(job_id, "approved", "已通过，可导出")
    log(job_id, "已通过审片。")
    return jsonify({"ok": True})


@app.route("/api/jobs/<job_id>/reject", methods=["POST"])
def api_reject(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "找不到任务"}), 404
    if job["status"] != "awaiting_review":
        return jsonify({"error": "这个任务现在没有可审的成片。"}), 400
    set_stage(job_id, "rejected", "已打回")
    log(job_id, "已打回（不导出）。")
    return jsonify({"ok": True})


@app.route("/api/jobs/<job_id>/retry", methods=["POST"])
def api_retry(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "找不到任务"}), 404
    if job["status"] not in ("failed", "interrupted"):
        return jsonify({"error": "只有失败或中断的任务可以重试。"}), 400
    def _fn(j):
        j["status"] = "queued"
        j["error"] = ""
    update_job(job_id, _fn)
    log(job_id, "重试。")
    start_advance(job_id)
    return jsonify({"ok": True})


@app.route("/api/jobs/<job_id>/delete", methods=["POST"])
def api_delete(job_id):
    with _lock:
        jobs = _load_jobs()
        if job_id not in jobs:
            return jsonify({"error": "找不到任务"}), 404
        del jobs[job_id]
        _save_jobs(jobs)
    shutil.rmtree(JOBS_DIR / job_id, ignore_errors=True)
    return jsonify({"ok": True})


@app.route("/api/jobs/<job_id>/video")
def api_video(job_id):
    video = JOBS_DIR / job_id / "render" / "video.mp4"
    if not video.exists():
        abort(404)
    return send_file(video, mimetype="video/mp4", conditional=True)


@app.route("/api/jobs/<job_id>/export")
def api_export(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "找不到任务"}), 404
    if job["status"] != "approved":
        return jsonify({"error": "只有通过审片的才能导出。"}), 400
    video = JOBS_DIR / job_id / "render" / "video.mp4"
    if not video.exists():
        return jsonify({"error": "找不到成片文件。"}), 404
    name = re.sub(r"[^\w\-]+", "-", job["title"]).strip("-") or job_id
    return send_file(video, as_attachment=True,
                     download_name="%s.mp4" % name, mimetype="video/mp4")


@app.route("/api/export_all")
def api_export_all():
    jobs = _load_jobs()
    approved = [j for j in jobs.values() if j["status"] == "approved"]
    if not approved:
        return jsonify({"error": "没有通过审片的成片。"}), 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for job in approved:
            video = JOBS_DIR / job["id"] / "render" / "video.mp4"
            if not video.exists():
                continue
            name = re.sub(r"[^\w\-]+", "-", job["title"]).strip("-") or job["id"]
            zf.write(video, "%s.mp4" % name)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name="approved_videos.zip",
                     mimetype="application/zip")


@app.route("/api/jobs/<job_id>/log")
def api_log(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "找不到任务"}), 404
    return jsonify({"log": job.get("log", [])})


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    # Jobs left "running" by a previous process can never finish; mark them
    # interrupted so the user can retry them instead of waiting forever.
    with _lock:
        jobs = _load_jobs()
        changed = False
        for job in jobs.values():
            if job["status"] == "running":
                job["status"] = "interrupted"
                job["stage"] = "上次运行中断"
                job["error"] = "程序重启或中断，请重试。"
                changed = True
        if changed:
            _save_jobs(jobs)
    print("工作台：http://127.0.0.1:5000  （pipeline：%s）" % PIPELINE_ROOT)
    app.run(host="127.0.0.1", port=5000, threaded=True)
