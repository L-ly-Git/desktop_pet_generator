# Photo to 9-part Chibi（示例风格）

> 目标：真人照片 → 稳定 9 部件 Q版卡通小人 → 契约可用的 character.json + preview.png。

## 1. 文件位置

项目内 Python 工具：

- `tools\step2\photo_to_chibi9.py`：稳定入口（特征提取 + 示例风格渲染 + 自动校验）
- `tools\step2\chibi_render_style.py`：样式渲染器（双辫、草帽、连衣裙、裙摆小花、白鞋袜）

Codex skill 包装：

- `C:\Users\罗烈易\.codex\skills\photo-to-chibi9\SKILL.md`
- `C:\Users\罗烈易\.codex\skills\photo-to-chibi9\scripts\run.py`

## 2. 输出目录

```text
<输出目录>\
├── character.json
├── parts\
│   ├── head.png
│   ├── body.png
│   ├── arm_l.png
│   ├── arm_r.png
│   ├── leg_l.png
│   ├── leg_r.png
│   ├── eye_l.png
│   ├── eye_r.png
│   └── mouth.png
└── preview.png
```

- 所有部件：512×512 全画布透明 PNG；
- `character.json`：契约 1.0，合法 ASCII 角色 id；
- `preview.png`：512×512 棋盘格预览；
- 工具会自动运行 `tools/validate.py`，输出 `契约校验: PASS/FAIL`。

## 3. 项目内 Python 用法

```bat
D:\Python\item\WindowPet\Window_Pet_Generator\.venv\Scripts\python.exe ^
  D:\Python\item\WindowPet\Window_Pet_Generator\tools\step2\photo_to_chibi9.py ^
  --input "02.jpg" ^
  --output-dir "photo_cartoon_instance\photo_char_01_example" ^
  --character-id photo_char_01 ^
  --name "照片角色 01" ^
  --preset example
```

## 4. Codex skill 用法

```bat
D:\Python\item\WindowPet\Window_Pet_Generator\.venv\Scripts\python.exe ^
  C:\Users\罗烈易\.codex\skills\photo-to-chibi9\scripts\run.py ^
  --input "03.jpg" ^
  --output-dir "photo_cartoon_instance\photo_char_02_example" ^
  --character-id photo_char_02 ^
  --name "照片角色 02" ^
  --preset example
```

该 skill 只是项目内 Python 工具的包装；最终桌面应用直接调用 `tools\step2\photo_to_chibi9.py`，不依赖 Codex。

## 5. 风格预设

- `--preset example`（默认）：
  - 黑色双辫；
  - 宽边草帽；
  - 黄色无袖连衣裙；
  - 裙摆五瓣小花；
  - 白色鞋袜；
  - 肤色来自照片。
- `--preset example --keep-photo-colors`：
  - 保留示例造型（双辫/草帽/连衣裙/小花）；
  - 发色、眼睛、嘴、服装颜色使用照片提取值。
- `--preset photo`：
  - 使用照片颜色、发长、服装轮廓和帽子检测；
  - 不强制双辫/草帽/黄裙。

覆盖参数：

- `--outfit auto|dress|tunic`
- `--hat auto|on|off`
- `--hair-style auto|long|medium|short|twin_braids`
- `--character-id`、`--name`

## 6. 测试结果

已用 02.jpg / 03.jpg / 04.jpg 测试 `--preset example`：

| 照片 | 输出角色 | 契约校验 |
|---|---|---|
| 02.jpg | photo_char_01_example | PASS |
| 03.jpg | photo_char_02_example | PASS |
| 04.jpg | photo_char_03_example | PASS |

三角色预览：

![示例风格三角色](../photo_cartoon_instance/example_style_gallery.png)

agent-vision 对生成预览的检查结果：黑色双辫、宽边草帽、黄色无袖连衣裙、裙摆五瓣小花、白色鞋袜，符合示例风格。

## 7. 最终应用集成

最终桌面应用可以不依赖 Codex，直接：

- import `tools.step2.photo_to_chibi9` 调用其函数；或
- subprocess 调用 `photo_to_chibi9.py`；
- 输出目录直接作为角色目录加载到 runtime；
- 依赖项目 `.venv` 与 `models\uniface`，照片全程本地。

## 8. 限制

- 是风格化 Q版小人，不保证严格长相一致；
- 示例风格默认黑发/黄裙，保留照片颜色需加 `--keep-photo-colors`；
- 复杂配饰、非正面姿势、严重遮挡可能需要后续校准；
- skill 是开发期包装，最终应用应使用项目内 Python 工具。