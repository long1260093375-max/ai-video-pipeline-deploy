# 拍剪科普视频流水线（本地部署包）

不依赖 Muse，在团队自己的电脑上跑：给选题 → 自动写稿 → 审理解表 → 自动生图抠图 → 自动渲染出片。审片通过后就是成片。

> **从 GitHub clone 下来的注意**：仓库里只有代码和文档。字体（`fonts/`）、Piper 语音模型（`tools/piper/`）、珊瑚湾模板图片（`templates/coral-bay/background.png` 和 `characters/*.png`）、配音缓存（`cutouts/voice_cache/`）这几个大文件不在仓库里——要完整能跑的包，用团队内部发的 `ai-video-pipeline-deploy.zip`，解压后就是齐的；也可以按下面“装机准备”里的说明自己补这几样。

## 一、装机准备（只做一次）

**需要先装好的东西**
- Python 3.10 或更高（建议 3.12）
- ffmpeg（渲染和配音都要用；装好后在终端里跑 `ffmpeg -version` 能出版本号就行）

**1. 建虚拟环境并装依赖**
```bash
cd ai-video-pipeline-deploy
python3 -m venv .venv
# Windows：.venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
```
第一次跑抠图时，rembg 会自动下载一次抠图模型 `u2net.onnx`（约 176MB），要联网，下载完以后就不用再下了。

**2. 配三个 key（环境变量，key 不要写进任何文件、不要发群里）**

| 环境变量 | 用在哪 | 去哪申请 |
|---|---|---|
| `ZHIPU_API_KEY` | 写稿、智谱生图（CogView） | 智谱 bigmodel.cn 控制台 → API Keys |
| `ARK_API_KEY` | Seedream 生图（主贴纸、细节、香港图标） | 火山引擎方舟控制台 → API Key |
| `DOUBAO_TTS_API_KEY` | 豆包配音（熊二等） | 火山引擎语音合成控制台 → API Key |

```bash
# macOS / Linux（写进 ~/.zshrc 或 ~/.bashrc 就不用每次都输）
export ZHIPU_API_KEY=你的key
export ARK_API_KEY=你的key
export DOUBAO_TTS_API_KEY=你的key
```
```bat
:: Windows（cmd）
set ZHIPU_API_KEY=你的key
set ARK_API_KEY=你的key
set DOUBAO_TTS_API_KEY=你的key
```

注意三点：
- 豆包配音的 key 和 Ark 生图的 key 是两笔不同的资源，结清 Ark 欠费不等于语音资源已开通；配音报 403 `45000030 resource not granted` 就是语音资源没开通，去语音合成控制台看。
- Seedream 每个模型要在方舟控制台逐个开通，没开通会报 404；429 是限流，停下来等一会儿，不要连续重试。
- 智谱生图按次计费：CogView-3-Flash 免费、CogView-4 约 ¥0.06/张、GLM-Image 约 ¥0.1/张；Seedream 约 ¥0.06/张。只计成功生成的。

**3. 字体不用装**
字幕用的思源黑体 SC 已经打进包里了（`fonts/NotoSansCJK-Bold.ttc`、`fonts/NotoSansCJK-Regular.ttc`），程序会优先用它。站酷快乐体、站酷庆科黄油体也在 `fonts/` 里，工作台里可以选。
注意：NotoSansCJK 这个文件的 index 2 才是简体中文，index 0 是日文，程序里已经写死了用 index 2，不要改。

**Windows 特别说明**
- `tools/piper/` 里是 Linux 版离线配音（花燕），Windows 上跑不了。Windows 机器用豆包配音（`--tts doubao`）就行；想离线配音的话，去 [Piper 官网](https://github.com/rhasspy/piper) 下 Windows 版，替换掉 `tools/piper/` 里的 `piper` 可执行文件和 `models/zh_huayan.onnx`，再把中文语音模型放进去。
- 命令行里的路径分隔符用 `\`，`export` 换成 `set`（见上面）。

## 二、做一集的流程（命令行版）

以“跨境电商”这集为例，四个步骤都在包根目录下跑（先 `source .venv/bin/activate`）。

**第 1 步：写稿**
```bash
python3 generate_script_zhipu.py --topic "跨境电商" --out scripts/跨境电商.json
```
出来一个 JSON：标题、12–14 句短句（200–320 字）、每句关键词、语义分组。文案有问题直接改这个 JSON。

**第 2 步：理解表（审阅关卡，一定要看）**
按脚本 + 模板 `templates/coral-bay/world_bible.md` 的规则，出一份“每句画什么”的表，审过才生图。工作台里这步是自动出的草稿（见下面）；命令行版先按 `understanding/RULES.md` 的原则自己列一张：
- 每句画面 = 地标/场景（珊瑚湾成熟扁平画风）+ 这句相关的金钱/物体 + 必要的图形符号
- 抽象词不要硬套字面符号，用人物互动讲清（比如“刺耳”不用耳朵图标，用一讲一听）
- 优先复用已有素材，但置信度 ≥80% 才复用，低于 80% 直接生成新图，不要硬凑

**第 3 步：生图 + 抠图**
```bash
# Seedream 生主贴纸（推荐，画风稳；模型可在脚本里换 5.0 Pro / 5.0 Flash）
python3 generate_kuajing_seedream.py
# Seedream 生细节贴纸（句中飞进来的第二元素）
python3 generate_kuajing_details.py
# 抠图（rembg U2Net，本地免费；原图在 cutouts/seedream_raw_*，成品在 cutouts/stickers_*）
python3 workbench/rembg_cut.py cutouts/seedream_raw_kuajing cutouts/stickers_kuajing_seedream_rembg
```
也可以用智谱生图（CogView-4），见 `generate_stickers_zhipu.py --help`；但 CogView 常漏关键物体、乱加人或水印，要人工审、常返工，Seedream 更稳。

**第 4 步：渲染出片**
```bash
python3 make_cutout_from_script_v13.py --script scripts/跨境电商.json \
  --stickers cutouts/stickers_kuajing_seedream_rembg \
  --out output/kuajing-seedream-v13 \
  --tts doubao --speaker zh_male_xionger_uranus_bigtts --speech-rate 10 \
  --background ai --details cutouts/stickers_kuajing_seedream_detail \
  --skip-details 1,3 --template coral-bay
```
- `--tts doubao` 是熊二配音（1.1 倍速）；`--tts piper` 是离线花燕；`--tts none` 是无声测试。
- `--background ai` 是珊瑚湾小镇背景（模板里读）；不加这个参数会用默认暮色渐变背景。
- `--skip-details 1,3` 是跳过第 1、3 句的细节贴纸（这两句没有第二个内容元素，硬加会很牵强）。
- 成片在 `output/kuajing-seedream-v13/video.mp4`。
- **配音有缓存，不会重复扣字数**：同一句话 + 同一个音色 + 同一语速，第一次合成后存在 `cutouts/voice_cache/` 里（按内容哈希命名），以后重渲直接复用，不再调接口、不再扣费；只有改了文案、换了音色或语速，才会重新合成。包里已带好跨境电商 14 句的熊二缓存，重渲这集不花钱。

出片后先自查再发：多时间点看背景对不对、贴纸和句子语义对不对、字幕有没有截断或溢出、配音多时间点有没有声、有没有 AI 水印。改过的版本用新文件名，不要覆盖旧成片，不然会看到缓存的旧版。

**香港离岸 MG 竖版（9:16）是另一条线**，不用上面这套渲染器：
```bash
# 先画图标（Seedream 扁平风，7 张）
python3 generate_hk_offshore_icons_flat.py
# 再渲染（v13 是定版：用户原声 5 句、逐词对位；配音文件放 output/hk-offshore-mg-9x16-v13/work/voice_0*.mp3）
python3 make_hk_offshore_mg_9x16_v13.py
```
香港片的税在画面和字幕里统一写 **S**，配音读“税”；四图标固定在长方形轨道四角，收尾 S=0 章盖在正中。

## 三、工作台（网页版，推荐日常用）

命令行四步都接进了工作台，点点鼠标就行：
```bash
source .venv/bin/activate
python3 workbench/app.py
# 打开 http://127.0.0.1:5000
```
功能：选风格模板、选人物形象、选配音（熊二默认 + 其他音色 + Piper 花燕 + 无声测试）、选字体；输入单个主题、批量选题（最多 20）、自己文案、已有脚本重渲；理解表是审阅关卡，审过才生图；审片后批准才能导出（单个 MP4 / 批量 zip）。
注意：工作台 v1 生图只有智谱 CogView-4（Seedream 还没接进工作台），没有细节贴纸；想用 Seedream 生图或细节贴纸，走上面命令行第 3、4 步。

## 四、包里都有什么

```
ai-video-pipeline-deploy/
  README.md                  本说明
  requirements.txt           Python 依赖
  config.yaml                全局配置（字体候选、配色、字幕）
  pipeline.py                字体、图片等公共函数
  template.py                模板加载器（templates/<名字>/）
  create_style.py            新建风格模板（见下面“加新风格”）
  generate_script_zhipu.py   写稿（智谱文字模型）
  generate_stickers_zhipu.py 智谱生图 + 抠图
  generate_kuajing_seedream.py      Seedream 生主贴纸
  generate_kuajing_details.py       Seedream 生细节贴纸
  generate_hk_offshore_icons_flat.py Seedream 生香港图标
  make_cutout_from_script.py        横屏抠图渲染器（v11 规则）
  make_cutout_from_script_v13.py    横屏抠图渲染器（v13，帧精确对位）
  make_hk_offshore_mg_9x16_v13.py   香港竖版 MG 渲染器（定版 v13）
  tools/
    tts_doubao.py            豆包配音（读 DOUBAO_TTS_API_KEY）
    tts_piper.py             Piper 离线配音包装
    piper/                   Piper Linux 版 + 花燕语音模型
  templates/
    coral-bay/               珊瑚湾模板（风格词、世界设定、背景、固定角色）
    _example_spec.json       新风格的配方示例（照着改）
    README.md                怎么加新风格
  fonts/                     思源黑体 SC（Bold/Regular）+ 站酷两个字体
  workbench/                 网页工作台（Flask）
  scripts/                   例：跨境电商、深圳、香港公司注册的成稿
  understanding/             理解表规则 + 例表
```

## 五、加新风格（本地直接做，不用找我）

可以，两种做法都在包里：

**做法一：改现有风格（最快，不用生图）**
```bash
cp -r templates/coral-bay templates/my-style
# 改 templates/my-style/style.yaml 里的风格词和配色，
# 有新背景图就替换掉 templates/my-style/background.png（1344x768），
# 角色想换就替换掉 characters/ 里对应的图
# 用的时候：--template my-style --background ai
```
模板就是一个文件夹，改完直接能用，不用改代码。

**做法二：全新做一个世界（要生图，约 ¥0.06/张）**
```bash
# 1. 复制配方示例，改成你想要的世界：画风词、背景、角色和地点、世界设定
cp templates/_example_spec.json my_style_spec.json
# 2. 一键生成整个模板（默认 Seedream Pro；--engine zhipu 换智谱 CogView-4）
python3 create_style.py --name my-style --spec my_style_spec.json
# 3. 用的时候：--template my-style --background ai
```
`create_style.py` 会生成：背景图（1344x768）、每个角色/地点的透明贴纸（自动抠图）、`style.yaml`、`world_bible.md`，都放在 `templates/my-style/` 里。跑过的图不会重复生成，加新角色时再跑一次就行（`--force` 强制重画）。
新风格第一次做一套 10 张左右大概 ¥0.6–1，之后复用不花钱，每集只花新贴纸的钱。

## 六、版式规则（全系列通用，不要改）

- 每画面最多 1–2 张贴纸：1 张居中，2 张一边一个；贴纸约 40–50% 屏高，脚落沙地线
- 不要顶部关键词/解说文字层；不要卡片框；字幕单行、64px、3px 描边
- 贴纸按不透明像素面积拉平，不要按外框高度
- 换句时贴纸正常出现/消失，不要闪白；入场水平滑入，不要大幅上下浮动
- 细节贴纸只在句意里确实有第二个内容元素时加，句中从上掉落，主贴纸左移让位

## 七、常见问题

- **配音报 403**：先看是哪个 key：豆包 403 `45000030` 是语音资源没开通（和 Ark 欠费是两回事）；Ark 403 也可能是欠费。去对应控制台查余额和开通状态。
- **Seedream 报 404**：那个模型没在方舟控制台开通，去开通；官方没有 2.0，3.0/4.0/4.5/5.0 Pro/5.0 Flash 才有。
- **Seedream 报 429**：限流了，停下来等，不要连续重试。
- **字幕出现日文汉字**（比如発、帳）：字体用了 NotoSansCJK 的 index 0。程序里已经固定 index 2，不要改；如果自己换了字体文件，确认它有简体中文。
- **贴纸抠出来有白边/白底**：白底洪泛抠图已经退役了，现在默认 rembg U2Net；纯白物体在纯白底上（比如白长方形证书）要用连通域方法，见香港 v9 的做法。
- **渲染出来没声音**：先看是不是豆包 403 导致垫了静音；配音文案没变的话，可以直接把旧版同文案的音轨合进来（参考跨境电商 v11/v12 的做法）。
- **工作台打不开**：确认 `.venv` 已激活、`pip install -r requirements.txt` 装过、端口 5000 没被占。

## 八、定版记录（2026-11-06）

- 香港离岸 MG 竖版：**v13 定版**（`output/hk-offshore-mg-9x16-v13/video.mp4`，13.5 秒，用户原声 5 句、逐词对位）
- 跨境电商一分钟入门：**v13 定版**（`output/kuajing-seedream-v13/video.mp4`，56.5 秒，熊二配音、按实际配音逐句对位）
- 深圳主线：v3 已通过（珊瑚湾背景 + 图标贴纸；字幕仍是日文版字体，未重渲）
