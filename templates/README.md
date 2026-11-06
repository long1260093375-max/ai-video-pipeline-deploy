# 风格模板（templates/）

一个模板就是一个文件夹，装着定义一集“长什么样”的全部东西。
换风格 = 换模板名，不用每集重新定风格。

## 现有模板

- `coral-bay/` — 珊瑚湾（第一个模板，用户 2026-11-05 定版）

## 模板里有什么

```
templates/<名字>/
  style.yaml        名字、生图风格词、生图模型、背景、字幕、配音
  world_bible.md    这个世界的固定角色和地点（理解表按这个来配图）
  background.png    小镇背景，1344x768（见下）
  characters/       固定角色贴纸，跨集复用，不用每集重画
```

## 用法

每一步都加 `--template <名字>`（默认 `coral-bay`）：

```bash
# 生图（主贴纸 / 细节贴纸，风格词从模板读）
python generate_kuajing_seedream.py --template coral-bay
python generate_kuajing_details.py --template coral-bay
python generate_stickers_zhipu.py --template coral-bay ...

# 渲染（背景从模板读，不用再手动换背景）
python make_cutout_from_script.py --script scripts/xxx.json \
  --stickers cutouts/... --details cutouts/... \
  --out output/xxx --tts doubao --speaker zh_male_xionger_uranus_bigtts \
  --speech-rate 10 --background ai --template coral-bay
```

`--template` 不存在时会报错并列出已有模板。

## 版式不进模板

一字形/品字型排版、字幕位置、动效、飞机绕飞这些是全系列通用的，
写在渲染器里，不放在模板里。换风格不会把版式换乱。

## 新加一个风格

1. 复制 `templates/coral-bay/` 成 `templates/<新名字>/`，改 `style.yaml`
   里的名字、风格词、配色。
2. 全新世界：再写一份 `world_bible.md`，生成一套角色 + 一张背景
   （先测一组，审过一次再存下来；参考珊瑚湾，一套约 ¥0.6–1）。
3. 背景必须是 **1344x768**：渲染器会裁到 y=690 再拉到 1920x1080，
   沙地线正好落 y=700。直接放 1920x1080 的原图，沙地线会掉到
   y~1000，贴纸全飘起来。
4. 跑 `python -c "from template import list_templates; print(list_templates())"`
   确认新模板能被认出来，再拿一组测试渲染验证。

## 注意事项

- `style.yaml` 里字幕字体必须是思源黑体 SC（index=2），index=0 是日文
  字形，单/贸/发/账会变成単/貿/発/帳（2026-11-05 踩过）。
- 角色必须是这个世界观里的形象（珊瑚湾只用海底生物，不用真人）。
- 模板只管“长什么样”，不管“讲什么”：文案、理解表、分组还是按
  每集的脚本走。
