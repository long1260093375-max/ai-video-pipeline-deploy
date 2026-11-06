#!/usr/bin/env python3
"""
Not dependent on Muse: science short-video pipeline.
Usage:
    pip install -r requirements.txt
    python pipeline.py --list
    python pipeline.py --topic chenmo-chengben
    python pipeline.py --all
Output: output/<id>/video.mp4 + script.txt + audio.mp3 + review.md
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

try:
    import yaml
except ImportError:
    yaml = None

from PIL import Image, ImageDraw, ImageFont


def load_yaml(path, default):
    if yaml is None or not Path(path).exists():
        return default
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or default


def find_font(config):
    # Workbench override (2026-11-06): PIPELINE_FONT_PATH, when set to an
    # existing font file, wins over config.yaml candidates. Unset = old
    # behaviour. The workbench sets it per render subprocess so the font
    # picker (SC Bold / ZCOOL KuaiLe / ZCOOL QingKe) takes effect without
    # touching the renderer's code.
    import os
    override = os.environ.get("PIPELINE_FONT_PATH", "")
    if override and Path(override).exists():
        return override
    for p in config.get("font_candidates", []) or []:
        # Relative entries resolve against this pipeline folder, so the
        # bundled fonts/ ships with the package and works on any machine.
        cand = Path(p)
        if not cand.is_absolute():
            cand = BASE / cand
        if cand.exists():
            return str(cand)
    return None


def get_font(config, size):
    path = find_font(config)
    if not path:
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(path, size, index=2)  # NotoSansCJK index 2 = SC, index 0 = JP (user 2026-11-05)
    except Exception:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()


def wrap_text(draw, text, font, max_width):
    lines = []
    cur = ""
    for ch in text:
        trial = cur + ch
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def build_scenes(topic):
    scenes = []
    scenes.append(("开头钩子", topic["hook"]))
    scenes.append(("故事引入", topic["story"]))
    for step in topic.get("steps", []):
        scenes.append((step.get("title", "这一步"), step.get("text", "")))
    scenes.append(("它有什么影响", topic["impact"]))
    scenes.append(("常见误区", topic["misconception"]))
    closing = "所以，记住一句话：" + topic["definition"] + "下期想听哪个概念，评论区告诉我。"
    scenes.append(("记住一句话", closing))
    return scenes


def draw_scene(config, series, title, body, scene_no, total, out_path, episode_title):
    w, h = config.get("resolution", [1080, 1920])
    bg = hex_to_rgb(config.get("background", "#0F172A"))
    accent = hex_to_rgb(config.get("accent", "#F59E0B"))
    text_c = hex_to_rgb(config.get("text_color", "#FFFFFF"))
    muted = hex_to_rgb(config.get("muted_color", "#CBD5E1"))
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 14], fill=accent)
    f_small = get_font(config, 44)
    f_title = get_font(config, 92)
    f_body = get_font(config, 58)
    f_ep = get_font(config, 48)
    d.text((80, 90), series, font=f_small, fill=muted)
    d.text((80, 170), episode_title, font=f_ep, fill=accent)
    d.text((80, 280), str(scene_no) + "/" + str(total), font=f_small, fill=muted)
    y = 430
    for line in wrap_text(d, title, f_title, w - 160):
        d.text((80, y), line, font=f_title, fill=text_c)
        y += 130
    y += 40
    for line in wrap_text(d, body, f_body, w - 160):
        d.text((80, y), line, font=f_body, fill=text_c)
        y += 92
    d.text((80, h - 180), config.get("disclaimer", ""), font=f_small, fill=muted)
    img.save(out_path)
    return out_path


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("命令失败：" + " ".join(cmd) + "\n" + r.stderr[-2000:])
    return r.stdout


def probe_duration(path):
    try:
        out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                   "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
        return float(out.strip())
    except Exception:
        return 0.0


async def tts_section(text, voice, rate, out_path):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(out_path))


def make_audio(scenes, config, workdir, no_tts):
    voice = config.get("voice", "zh-CN-XiaoxiaoNeural")
    rate = config.get("voice_rate", "+0%")
    audios = []
    durations = []
    voice_ok = True
    for i, (_t, text) in enumerate(scenes):
        mp3 = workdir / ("audio_" + str(i) + ".mp3")
        ok = False
        if not no_tts:
            try:
                asyncio.run(tts_section(text, voice, rate, mp3))
                if mp3.exists() and probe_duration(mp3) > 0:
                    ok = True
            except Exception as e:
                print("配音失败（第 " + str(i + 1) + " 段），改用静音估算时长：" + str(e))
        if ok:
            audios.append(mp3)
            durations.append(max(1.5, probe_duration(mp3)))
        else:
            voice_ok = False
            dur = max(2.5, len(text) / 4.5)
            durations.append(dur)
            silent = workdir / ("silent_" + str(i) + ".mp3")
            run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                 "anullsrc=r=44100:cl=stereo", "-t", str(dur), "-q:a", "9",
                 "-acodec", "libmp3lame", str(silent)])
            audios.append(silent)
    lst = workdir / "audio_list.txt"
    lst.write_text("".join("file '" + str(a) + "'\n" for a in audios), encoding="utf-8")
    full = workdir / "audio.mp3"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(lst), "-c", "copy", str(full)])
    return durations, full, voice_ok


def assemble_video(media, durations, audio, out_path, fps, resolution):
    # 稳健版：先每段单独编码成小 mp4，再用 concat 拼起来，最后混入配音。
    # 这样一段出问题也容易定位，不会因为 8 路 concat 滤镜整体失败。
    # media: 每段一个 (kind, path)，kind 是 image 或 video。
    w, h = resolution
    workdir = Path(out_path).parent / "work"
    seg_files = []
    for i, ((kind, path), dur) in enumerate(zip(media, durations)):
        seg = workdir / ("seg_" + str(i) + ".mp4")
        if kind == "video":
            run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", str(path),
                 "-t", str(dur), "-vf",
                 f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps}",
                 "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                 "-r", str(fps), str(seg)])
        else:
            run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", str(dur), "-i", str(path),
                 "-vf", f"scale={w}:{h},fps={fps}",
                 "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                 "-r", str(fps), str(seg)])
        seg_files.append(seg)
    lst = workdir / "video_list.txt"
    lst.write_text("".join("file '" + str(s) + "'\n" for s in seg_files), encoding="utf-8")
    silent_video = workdir / "video_only.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(lst), "-c", "copy", str(silent_video)])
    run(["ffmpeg", "-y", "-v", "error", "-i", str(silent_video), "-i", str(audio),
         "-c", "copy", "-shortest", str(out_path)])


def fmt_time(s):
    ms = int(round(s * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    sec, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, sec, ms)


def write_review(outdir, topic, scenes, durations, voice_ok):
    total = sum(durations)
    lines = []
    lines.append("# 审核：" + topic["title"])
    lines.append("- 成片：video.mp4（%.1f 秒，竖屏 1080x1920）" % total)
    lines.append("- 口播稿：script.txt")
    lines.append("- 配音：" + ("edge-tts 真人音色" if voice_ok else "静音估算（没装 edge-tts 或配音失败，装好重跑即可出声）"))
    lines.append("- 审核只看三样：1）概念讲得对不对 2）例子有没有硬伤 3）画面有没有侵权素材")
    lines.append("- 通过：把本文件夹移到 output/approved/；打回：改 topics.yaml 对应条目，再跑一次同一条命令。")
    lines.append("")
    lines.append("## 分段时长")
    t = 0.0
    for (title, _text), d in zip(scenes, durations):
        lines.append("- " + fmt_time(t) + " - " + fmt_time(t + d) + "  " + title)
        t += d
    (outdir / "review.md").write_text("\n".join(lines), encoding="utf-8")


def llm_draft(title, config):
    key = os.environ.get("LLM_API_KEY", "")
    base = os.environ.get("LLM_API_BASE", config.get("llm_api_base", ""))
    model = os.environ.get("LLM_MODEL", config.get("llm_model", "gpt-4o-mini"))
    if not key or not base:
        raise RuntimeError("LLM 模式需要设置环境变量 LLM_API_KEY 和 LLM_API_BASE")
    import requests
    prompt_path = BASE / "prompts" / "script_prompt.txt"
    prompt = prompt_path.read_text(encoding="utf-8").replace("{TITLE}", title) if prompt_path.exists() else title
    r = requests.post(base.rstrip("/") + "/chat/completions", json={
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }, headers={"Authorization": "Bearer " + key}, timeout=90)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        raise RuntimeError("大模型返回的不是 JSON，先检查提示词和模型")
    data = json.loads(m.group(0))
    data["id"] = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "topic"
    data["title"] = title
    return data


def process_topic(topic, config, no_tts, out_root, voice_file=None):
    outdir = out_root / topic["id"]
    outdir.mkdir(parents=True, exist_ok=True)
    workdir = outdir / "work"
    workdir.mkdir(exist_ok=True)
    scenes = build_scenes(topic)
    script = "\n\n".join("【" + t + "】\n" + text for t, text in scenes)
    (outdir / "script.txt").write_text(script, encoding="utf-8")
    if voice_file and Path(voice_file).exists():
        # 外部配音模式：用用户自己导出的整段配音，按字数比例切分每段时长
        import shutil
        audio = workdir / "audio.mp3"
        shutil.copyfile(voice_file, audio)
        total = probe_duration(audio)
        lens = [max(1, len(text)) for _t, text in scenes]
        durations = [max(2.0, total * ln / sum(lens)) for ln in lens]
        voice_ok = True
    else:
        durations, audio, voice_ok = make_audio(scenes, config, workdir, no_tts)
    media = []
    for i, (title, text) in enumerate(scenes):
        # 优先用视频片段：assets/scene_0.mp4、scene_1.mp4……（你们授权的海绵宝宝片段放这里）
        clip = None
        for ext in (".mp4", ".mov", ".mkv"):
            cand = BASE / "assets" / ("scene_" + str(i) + ext)
            if cand.exists():
                clip = cand
                break
        if clip is not None:
            media.append(("video", clip))
            continue
        img = workdir / ("scene_" + str(i) + ".png")
        custom = BASE / "assets" / ("scene_" + str(i) + ".png")
        if custom.exists():
            from PIL import Image as PILImage
            PILImage.open(custom).convert("RGB").resize(tuple(config.get("resolution", [1080, 1920]))).save(img)
        else:
            draw_scene(config, config.get("series_name", ""), title, text,
                       i + 1, len(scenes), img, topic["title"])
        media.append(("image", img))
    srt = []
    t = 0.0
    for i, (title, text) in enumerate(scenes, 1):
        srt.append(str(i) + "\n" + fmt_time(t) + " --> " + fmt_time(t + durations[i - 1]) + "\n" + text + "\n")
        t += durations[i - 1]
    (outdir / "subtitles.srt").write_text("\n".join(srt), encoding="utf-8")
    video = outdir / "video.mp4"
    assemble_video(media, durations, audio, video, config.get("fps", 30),
                   tuple(config.get("resolution", [1080, 1920])))
    (outdir / "audio.mp3").write_bytes(audio.read_bytes())
    write_review(outdir, topic, scenes, durations, voice_ok)
    print("完成：" + topic["title"] + " -> " + str(video) + "（%.1f 秒，配音=%s）" % (sum(durations), "有声" if voice_ok else "静音估算"))
    return video


def main():
    ap = argparse.ArgumentParser(description="不依赖 Muse 的科普短视频流水线")
    ap.add_argument("--topic", help="选题 id，如 chenmo-chengben")
    ap.add_argument("--all", action="store_true", help="跑 topics.yaml 里的全部选题")
    ap.add_argument("--list", action="store_true", help="列出全部选题")
    ap.add_argument("--llm", metavar="标题", help="用大模型给新标题起草并写入 topics.yaml")
    ap.add_argument("--no-tts", action="store_true", help="不配音，只按估算时长出画面（测试用）")
    ap.add_argument("--voice-file", help="用外部整段配音 mp3 代替 edge-tts，例如剪映导出的配音")
    args = ap.parse_args()
    config = load_yaml(BASE / "config.yaml", {})
    topics = load_yaml(BASE / "topics.yaml", [])
    if not topics:
        print("topics.yaml 为空或缺 PyYAML，先 pip install -r requirements.txt")
        return 1
    if args.list:
        for t in topics:
            print(t["id"] + "  " + t["title"])
        return 0
    if args.llm:
        data = llm_draft(args.llm, config)
        topics.append(data)
        if yaml is not None:
            with open(BASE / "topics.yaml", "w", encoding="utf-8") as f:
                yaml.safe_dump(topics, f, allow_unicode=True, sort_keys=False)
        print("已把新选题写入 topics.yaml：" + data["id"])
        return 0
    out_root = BASE / "output"
    if args.all:
        for t in topics:
            process_topic(t, config, args.no_tts, out_root, args.voice_file)
        return 0
    if args.topic:
        hit = [t for t in topics if t["id"] == args.topic or t["title"] == args.topic]
        if not hit:
            print("找不到选题：" + args.topic + "，用 --list 看看 id")
            return 1
        process_topic(hit[0], config, args.no_tts, out_root, args.voice_file)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
