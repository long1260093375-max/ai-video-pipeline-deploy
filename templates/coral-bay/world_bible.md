# 珊瑚湾世界设定（一整套，原创）

目标：以后每集不再单张单张想形象，所有贴纸、场景、角色都出自同一个世界，
换文案不换世界，系列感一致，角色不變臉。

> 原创声明：珊瑚湾及以下角色、地点均为原创设定，不复刻海绵宝宝、
> 比奇堡、派大星、章鱼哥、蟹老板、菠萝屋等版权角色与场景。
> 如团队持有相关 IP 正式授权，需另按授权范围使用官方素材，不用本设定替代。

## 一、世界：珊瑚湾

- 一个海底小镇，不是某个具体动画的城镇翻版
- 地面是细沙小广场，街道两边是珊瑚房子和海草路灯，天上飘着小气泡
- 固定地点（道具库，每集调用，不重画）：
  - 珊瑚学校：讲概念的主场景，黑板是贝壳形状
  - 海龟杂货铺：买卖、市场、价格类概念的场景
  - 气泡邮局：寄送、物流、跨境类概念的场景（2026-11-04 重做版：蓝色小楼纯建筑、无人，待确认）
  - 珊瑚港：出发、运输、远方市场的场景
  - 珊瑚图书馆：规则、查资料、合规类概念的场景（2026-11-04 重做版：贝壳拱门 + 满墙书架纯建筑、无人，水印已清，待确认）

## 二、固定角色（每集生图时，原样抄下面这段描述，不改长相）

### 1. 墨墨 —— 讲概念的老师
- 一只圆头小蓝章鱼，戴圆框眼镜，围一条黄色围巾
- 性格：耐心、爱举例子，说话慢一条一条讲
- 固定描述（生图时用）：
  "a small round-headed blue octopus teacher wearing round glasses and a yellow scarf"

### 2. 壳壳 —— 开杂货铺的店主
- 一只绿壳海龟，壳上有珊瑚花纹，背一个小布包
- 性格：精打细算，讲买卖、成本、价格时出场
- 固定描述：
  "a green turtle shopkeeper with a coral-patterned shell and a small cloth bag"

### 3. 灯灯 —— 送快递的灯笼鱼
- 一条小灯笼鱼，头顶一盏暖黄小灯，背一个邮包
- 性格：跑得快，讲物流、送货、时效时出场
- 固定描述：
  "a small lanternfish courier with a warm yellow head lantern and a mail bag"

### 4. 珊珊 —— 提问的学生
- 一个粉色珊瑚发的小姑娘，头上别一枚小贝壳发卡
- 性格：好奇、爱追问，负责问出观众想问的问题
- 固定描述：
  "a young girl with pink coral hair and a small shell hairpin"

## 三、固定画风与配色

- 画风：成熟扁平插画（2026-11-04 定向：之前那套可爱风显得太幼稚，改走成熟风；
  以 `generate_coralbay_set_mature.py` 的 STYLE 为准：modern flat illustration for adults，
  clean thin outlines，muted sophisticated colors，realistic proportions，not baby-like）
- 主色：海水蓝 (59, 130, 246)、珊瑚粉 (255, 150, 170)、沙黄 (245, 158, 11)、
  海草绿 (34, 197, 94)、贝壳紫 (168, 85, 247)
- 成片背景目前仍是代码画的暮色渐变 + 粉彩虚化光斑 + 底部柔和渐暗，保证字幕可读；
  另有一张 AI 宽幅珊瑚湾小镇背景（`cutouts/stickers_coralbay_mature/background.png`，
  1344x768，两边珊瑚房子、海草路灯，中间沙滩广场和船，中间留空放贴纸和字幕），
  只有经过虚化 + 底部加深处理后才能当成片背景（其右下角水印正好落在底部加深区），
  是否启用待用户确认，确认前不改成片背景
- 每张贴纸规则不变：单个主体占满画面、无文字、无边框、无白底、透明底 PNG

## 四、生图提示词模板（每集复用）

```
Modern flat illustration for adults, clean thin outlines, muted sophisticated colors,
realistic proportions, calm expression, not baby-like, no oversized eyes,
[上面对应的固定角色描述，或固定地点描述],
single subject, large and clearly visible, filling most of the frame,
isolated on a transparent background, no white background, no white border,
no border, no shadow, no text, no words.
```

- 讲概念：墨墨出场，珊珊提问
- 讲买卖/成本：壳壳出场，杂货铺场景
- 讲物流/送货：灯灯出场，邮局或港口场景
- 讲规则/合规：珊瑚图书馆场景，墨墨拿清单

## 五、以后新集的流程

1. `generate_script_zhipu.py --topic "题目"` 写稿
2. 按稿子每句的意思，从上面 4 个角色 + 5 个地点里选，不新发明角色
2b. 新元素规则（复用优先，2026-11-04 向用户确认过的流程）：每句先查本设定，
    能复用已有角色/地点就复用；实在是新道具、新场景、新角色时，先把它的固定描述
    写进本设定，再按第四节模板生图，不允许同一元素每集换个样
3. 用第四节模板生图、抠图，存到当集的 stickers 目录
4. `make_cutout_from_script.py --script scripts/题目.json --stickers ... --out ...` 出片
5. 只审成片：概念对不对、例子有没有硬伤、角色有没有变脸

## 六、待你定

- 角色数量够不够：现在 4 个，要不要加一个“反派/捣蛋鬼”之类的固定角色？（未定）
- 待你确认（2026-11-04 已生成，尚未回复）：邮局、图书馆重做版是否定稿——
  两张均为纯建筑、无人，邮局是蓝色小楼，图书馆是贝壳拱门 + 满墙书架，
  图书馆右下角水印已清；AI 宽幅小镇背景是否启用（需先虚化 + 底部加深）。
- 已定：小镇名保持“珊瑚湾”；角色全家福已生成
  （`cutouts/stickers_coralbay_mature/family.png`）。
