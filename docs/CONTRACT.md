# Window Pet Generator · Cut-out 契约 v1

> 状态：1-A 已完成（契约、schema、校验器、占位角色、动作库 v0）
> 契约版本：`1.0`
> 目标平台：Windows
> 后续运行时：PyQt5（1-B 开始）

## 1. 这份契约解决什么

cut-out 的本质是：**同一套参数驱动任意角色的同名部件**。只要所有角色都遵守同一套部件命名、画布坐标、枢轴和绘制顺序，运行时就能用同一份动作 JSON 驱动任何角色，不需要为每个角色重做动画。

这份文档是 1-A 的交付物，也是后续运行时、动作编辑器、照片分层 Agent 和可视化编辑器的共同依据。

## 2. 文件清单

| 文件 | 作用 |
|---|---|
| `contracts/rig_contract.json` | 契约主文件：画布、9 个部件、父级、z 顺序、通道、动作约束 |
| `contracts/character.schema.json` | 角色档案 `character.json` 的 JSON Schema |
| `contracts/action.schema.json` | 动作 JSON 的 JSON Schema |
| `tools/validate.py` | 统一的角色/动作/动作目录校验器（不依赖 jsonschema） |
| `tools/make_placeholder_character.py` | 生成 1-A 用的占位角色与预览图 |
| `assets/actions/*.json` | 共享动作库 v0（8 个动作） |
| `assets/characters/demo/` | 占位角色（9 张全画布 PNG + `character.json` + 预览图） |

## 3. 画布与坐标

- 画布尺寸：`512 x 512`。
- 图像坐标系：**左上角为原点**，x 轴向右，y 轴向下。
- 屏幕锚点：`anchor_point = [256, 512]`，即画布**底部中心**。1-B 的运行时会把该点对齐到桌宠在屏幕上的“脚底位置”，用于整体定位和行走。
- 部件枢轴：每个部件的 `pivot` 使用画布像素坐标，表示该部件旋转/缩放的中心。每个角色可以按自己的美术资源设置不同的枢轴。
- 全画布叠加：每个部件的 PNG 都是 `512 x 512`，只有该部件的像素可见，其余透明；叠在一起就是完整角色。这样不需要为每个部件维护额外的偏移量，AI 分层时也不容易错位。
- 旋转方向：`rot` 为正数时，在屏幕上表现为**顺时针**（因为 y 轴向下）。
- 缩放：`sx` / `sy` 是比例，`1.0` 表示原始大小。
- 平移：`tx` / `ty` 单位是像素，`ty` 正数向下。

## 4. 部件表

| 部件 | 必需 | 父级 | z | 默认枢轴 | 说明 |
|---|---:|---|---:|---|---|
| `head` | 是 | `body` | 3 | `[256, 180]` | 头部；v1 中头发烘焙在 `head.png` 内 |
| `body` | 是 | `root` | 1 | `[256, 320]` | 躯干 |
| `arm_l` | 否 | `body` | 0 | `[200, 300]` | 左臂（画面左侧） |
| `arm_r` | 否 | `body` | 0 | `[312, 300]` | 右臂（画面右侧） |
| `leg_l` | 否 | `root` | -1 | `[230, 420]` | 左腿（画面左侧） |
| `leg_r` | 否 | `root` | -1 | `[282, 420]` | 右腿（画面右侧） |
| `eye_l` | 否 | `head` | 4 | `[230, 200]` | 左眼 |
| `eye_r` | 否 | `head` | 4 | `[282, 200]` | 右眼 |
| `mouth` | 否 | `head` | 4 | `[256, 240]` | 嘴 |

说明：

- `default_pivot` **只是参考值**，不是强制值。每个角色应在 `character.json` 中提供自己的 `pivot`。
- 校验器会对“与默认枢轴偏差超过画布 25%”的角色给出警告，但不会判错；这是为了提醒你确认枢轴是否合理。
- v1 不单列 `hair`。头发烘焙进 `head.png`；如果后续需要头发单独摆动，会在契约 1.x 中增加可选 `hair` 部件。
- 非人形角色（例如团子、幽灵）可以只提供 `head` + `body`，其余可选部件缺失时，运行时忽略对应动作通道。

## 5. 父子关系

```
root（虚拟根节点，锚点 = 画布底部中心）
├── body
│   ├── head
│   │   ├── eye_l
│   │   ├── eye_r
│   │   └── mouth
│   ├── arm_l
│   └── arm_r
├── leg_l
└── leg_r
```

父级变换会自动传递给子级：

- `body` 平移/旋转/缩放时，`head`、`arm_l`、`arm_r` 跟随。
- `head` 平移/旋转/缩放时，`eye_l`、`eye_r`、`mouth` 跟随。
- `leg_l` / `leg_r` 挂在 `root` 下，不随 `body` 的呼吸起伏而移动，避免脚底漂浮。
- `root` 用于整体跳跃、行走时的窗口位移、整体缩放等。

## 6. 部件图片规范

- 格式：PNG。
- 尺寸：必须是 `512 x 512`。
- 通道：必须带透明通道（推荐 `RGBA`）。
- 内容：每张图只保留对应部件，其余区域透明；不要把多个部件合并到同一张图。
- 不要预烘焙动作：呼吸、挥手、眨眼等都由动作 JSON 驱动，不要把动作画进部件图里。
- 文件路径写在 `character.json` 中，必须是相对路径，不能是绝对路径，也不能包含 `..`。
- 推荐命名：`head.png`、`body.png`、`arm_l.png`……与部件名一致，方便人工检查。

## 7. 角色档案 `character.json`

示例（`assets/characters/demo/character.json`）：

```json
{
  "id": "demo",
  "contract_version": "1.0",
  "rig": {
    "parts": {
      "head": {"file": "parts/head.png", "pivot": [256, 276]},
      "body": {"file": "parts/body.png", "pivot": [256, 310]},
      "arm_l": {"file": "parts/arm_l.png", "pivot": [200, 300]},
      "arm_r": {"file": "parts/arm_r.png", "pivot": [312, 300]},
      "leg_l": {"file": "parts/leg_l.png", "pivot": [230, 420]},
      "leg_r": {"file": "parts/leg_r.png", "pivot": [282, 420]},
      "eye_l": {"file": "parts/eye_l.png", "pivot": [230, 200]},
      "eye_r": {"file": "parts/eye_r.png", "pivot": [282, 200]},
      "mouth": {"file": "parts/mouth.png", "pivot": [256, 240]}
    }
  },
  "persona": {
    "name": "小占位",
    "setting": "你是小占位，一个用于测试契约与动作系统的桌宠角色。"
  },
  "knowledge": [
    {"key": "身份", "value": "Window Pet Generator 的占位测试角色"},
    {"key": "喜欢", "value": "被拖动到屏幕各处"}
  ],
  "idle_lines": [
    {"text": "今天也要一起写代码吗？", "action": "wave", "weight": 2},
    {"text": "呼……发会儿呆。", "action": "nod", "weight": 2}
  ]
}
```

字段说明：

| 字段 | 必需 | 说明 |
|---|---:|---|
| `id` | 是 | 角色唯一标识，只能包含字母、数字、`_`、`-` |
| `contract_version` | 是 | 必须与 `rig_contract.json` 的版本一致 |
| `rig.parts` | 是 | 至少包含 `head` 和 `body`；每个部件包含 `file` 与 `pivot` |
| `persona.name` | 是 | 角色显示名 |
| `persona.setting` | 是 | 角色设定（系统提示词的核心内容） |
| `knowledge` | 是 | 结构化知识库数组，每项为 `{key, value}`；v1 先用 key-value，不急于上向量库 |
| `idle_lines` | 是 | 待机台词池；每项为 `{text, action, weight}` |

## 8. 动作 JSON

示例（`assets/actions/wave.json`，节选）：

```json
{
  "id": "wave",
  "display_name": "挥手",
  "duration": 1.4,
  "loop": false,
  "easing": "ease_in_out",
  "tracks": {
    "arm_r": {
      "rot": [
        {"t": 0.0, "v": 0.0},
        {"t": 0.35, "v": -115.0},
        {"t": 0.65, "v": -92.0},
        {"t": 0.95, "v": -115.0},
        {"t": 1.4, "v": 0.0}
      ]
    },
    "head": {
      "rot": [
        {"t": 0.0, "v": 0.0},
        {"t": 0.35, "v": -3.0},
        {"t": 0.95, "v": 3.0},
        {"t": 1.4, "v": 0.0}
      ]
    }
  }
}
```

字段说明：

| 字段 | 必需 | 说明 |
|---|---:|---|
| `id` | 是 | 动作唯一标识；`idle_lines[].action` 引用它 |
| `display_name` | 否 | 菜单/编辑器显示名 |
| `duration` | 是 | 动作时长，单位秒，必须大于 0 |
| `loop` | 是 | 是否循环；背景待机 `idle_breath` 与 `walk` 为循环动作 |
| `easing` | 否 | 默认缓动；可被关键帧的 `ease` 覆盖 |
| `tracks` | 是 | 非空对象；键为动作目标（部件名或 `root`），值为通道表 |

关键帧规则：

- 每个通道是一个数组，至少 1 帧。
- `t` 是时间（秒），必须 **严格递增**，范围在 `[0, duration]` 内。
- `v` 是该通道的值。
- `ease` 可选；表示“从当前关键帧到下一关键帧”的缓动。
- 循环动作建议每个通道的首尾值一致；校验器会对此给出警告。

## 9. 通道与单位

| 通道 | 单位 | 默认值 | 说明 |
|---|---|---:|---|
| `tx` | 像素 | `0` | 水平平移，正数向右 |
| `ty` | 像素 | `0` | 垂直平移，正数向下 |
| `rot` | 度 | `0` | 绕枢轴旋转，正数在屏幕上顺时针 |
| `sx` | 比例 | `1.0` | 水平缩放，不能为负 |
| `sy` | 比例 | `1.0` | 垂直缩放，不能为负 |

未出现在动作中的通道按默认值处理；角色缺失某个可选部件时，运行时忽略该部件的通道。

## 10. 缓动

| 名称 | 效果 |
|---|---|
| `linear` | 匀速 |
| `ease_in` | 慢起快收 |
| `ease_out` | 快起慢收 |
| `ease_in_out` | 两端慢、中间快（默认推荐） |
| `step` | 保持当前值，直到下一关键帧瞬间切换 |

## 11. `root` 虚拟节点

`root` 不是图片部件，而是整只桌宠的虚拟根节点：

- 枢轴为画布底部中心 `[256, 512]`。
- 用于整体跳跃（`jump.json` 的 `root.ty`）、行走时的整体起伏、整体缩放等。
- 行走时的窗口位置移动由 1-B 的控制器负责；`walk.json` 只负责四肢摆动。

## 12. 待机台词与动作绑定

`idle_lines` 的每一项是 `{text, action, weight}`：

- `text`：气泡台词。
- `action`：动作 id，必须存在于 `assets/actions`。
- `weight`：权重，必须大于 0；调度器按权重随机抽取。

运行时有两个明确不同的入口：

1. **待机调度**：按权重从 `idle_lines` 抽取一条 → 播放 `action` + 显示 `text`。
2. **手动动作**：用户从菜单直接选择动作 → **只播放动作，不显示台词**。

建议 `idle_lines` 使用非循环动作（`wave`、`nod`、`blink`、`yawn`、`shake_head` 等）。如果引用了循环动作（例如 `idle_breath`、`walk`），校验器会给出警告，因为循环动作没有天然的结束点，不适合作为一次性的台词演出。

## 13. 校验

在 `Window_Pet_Generator` 目录下运行：

```bat
python tools\validate.py actions assets\actions
python tools\validate.py character assets\characters\demo --actions-dir assets\actions
python tools\validate.py action assets\actions\wave.json
```

- 退出码 `0`：通过（可能有警告）。
- 退出码 `1`：存在错误，不能进入运行时。

校验内容：

- 契约版本、画布、部件、父级、默认枢轴、通道。
- 角色必需字段、必需部件、未知部件、部件文件、PNG 尺寸、透明通道。
- 枢轴范围、知识库结构、待机台词结构、权重。
- 动作目标、通道、关键帧顺序、时间范围、缩放非负、缓动名称、循环首尾值。
- `idle_lines[].action` 是否引用了存在的动作。

## 14. 新建角色步骤

1. 在 `assets/characters/` 下新建角色目录，例如 `assets/characters/my_pet/`。
2. 在目录下新建 `parts/`，放入 9 张（或至少 2 张）`512 x 512` 全画布透明 PNG。
3. 编写 `character.json`，填写 `id`、`contract_version`、`rig.parts`、`persona`、`knowledge`、`idle_lines`。
4. 运行 `python tools\validate.py character assets\characters\my_pet --actions-dir assets\actions`。
5. 1-B 完成后，用运行时加载该角色预览；1-C 完成后，可以直接播放共享动作库。

## 15. 版本演进规则

- **破坏性变更**（重命名部件、改变坐标系、改变图片规范、改变动作格式）必须提升主版本号，例如 `2.0`。
- **向后兼容的新增**（新增可选部件、新增可选通道、新增缓动）可以提升次版本号，例如 `1.1`。
- 运行时必须拒绝加载 `contract_version` 与自身支持版本不一致的角色，避免“看起来能加载、动作却错位”。
- 每个角色只声明一个 `contract_version`；迁移工具由后续的可视化编辑器负责。

## 16. v1 的限制与后续

v1 刻意保持简单，以下能力**不在 1-A 范围内**：

- 网格变形（mesh deformation）、IK、物理摆动。
- 独立 `hair` 部件与头发物理。
- 部件级 z 覆盖（v1 使用契约固定 z）。
- 部件透明度通道（`alpha`）。
- 语音、AI 对话、知识库检索（第 4 步）。
- 照片自动分层（第 2 步）。
- 可视化编辑器与打包（第 5 步）。

已知取舍：

- 全画布叠加会让每个角色占用约 `9 x 512 x 512 x 4` 字节（约 9 MB，未压缩）的内存；对桌宠场景可以接受，换来的是对齐简单、AI 分层不易错位。
- 父子层级是简单刚体层级，没有骨骼约束；这符合“短平快 cut-out”的目标。
- 占位角色只是几何图形，用于验证契约与运行时；真实角色素材会在 1-E 的第二角色测试或第 2 步接入。

## 17. 当前交付状态

| 子阶段 | 状态 |
|---|---|
| 1-A 契约层 | 已完成：契约、schema、校验器、占位角色、8 个动作 |
| 1-B PyQt5 运行时骨架 | 待开始 |
| 1-C 动作系统 | 待开始 |
| 1-D 调度与交互 | 待开始 |
| 1-E 第二角色验收 | 待开始 |