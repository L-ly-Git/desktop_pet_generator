# Window Pet Generator（Windows 桌宠生成器）

把 **真人照片 → Q 版卡通桌宠** 的完整流程做成本地化工具：

> 上传照片 → 生成 A-pose Q 版立绘 → 自动分层成 9 部件 → 校准 → 配置人设/知识库/待机台词 → AI 对话 → 运行 / 打包分发。


---

## 一、功能总览

| 模块 | 说明 | 入口 |
|---|---|---|
| 契约 | 512×512 画布、9 部件（head/body/arm_l/arm_r/leg_l/leg_r/eye_l/eye_r/mouth）、动作 schema | `contracts/` |
| 运行时 | 透明桌宠窗口、cut-out 骨骼渲染、8 个动作、待机调度、气泡、点击穿透、拖拽/行走 | `runtime/app.py` |
| 生成（2A） | 照片 → A-pose Q 版立绘（3 个 seed、相似度预设 A/B/C、性别） | 工作台「新建角色」或 `step2_pipeline.py` |
| 自动分层（2B） | 立绘 → 9 部件（SAM 提示式分割 + 几何规则） | `split_general.py` |
| 手动校准（2C） | 笔刷/套索/智能套索/枢轴 手动修正分层 | `calibrate_panel.py` |
| 遮挡修复 | 补齐被上层遮住的下层部件，旋转不漏洞 | `occlusion.py` |
| 配置（3） | 人设 / 知识库 / 待机台词 / 对话记忆 | 工作台「配置」页或 `character_editor.py` |
| AI 对话（4） | 多服务商、长时记忆、反幻觉 | `runtime/chat.py` |
| 工作台（5） | 统一前端：角色库 + 新建向导 + AI 设置 | `tools/studio.py` |
| 打包 | PyInstaller onedir，一键出 exe | `build.bat` / `build_exe.py` |

内置 8 个共享动作：`blink 眨眼 / idle_breath 呼吸待机 / jump 跳跃 / nod 点头 / shake_head 摇头 / walk 行走 / wave 挥手 / yawn 打哈欠`。

---

## 二、快速开始（开发模式）

```powershell
cd Window_Pet_Generator

python -m venv .venv
.venv\Scriptsctivate
pip install -r requirements.txt

python tools\studio.py          # 启动工作台
```

> 仅“生成（照片→Q版）”需要额外准备本地 ComfyUI（见「常见问题」）。分层/配置/运行桌宠不需要 ComfyUI。

---

## 三、工作台使用说明

启动：`python tools\studio.py`

### 1. 角色库（左侧）
列出 `characters/` 下所有角色，选中后右侧显示预览与信息。每个角色可：
- **运行**：启动该角色桌宠（实时读取角色目录）
- **配置**：切到内嵌配置页（人设/知识库/待机台词/记忆）
- **分层**：打开校准面板微调部件
- **打包**：导出角色包（zip，`character.json + parts/ + preview/source/memory/history`）
- **删除 / 打开目录 / 导入已有角色目录**

### 2. 新建角色（4 步向导）
「新建角色…」→ 填参数 → 「开始生成」：
1. **生成**：选照片、角色ID、名称、性别（女/男/auto）、相似度预设（A 基线 / B 增强相似·推荐 / C 最大相似）、后端（本地 ComfyUI / 云端待接入）；后台生成 3 个 seed，实时刷日志，完成后弹窗「已经生成」。
2. **选立绘**：点选 3 个 seed 缩略图之一。
3. **自动分层**：点「对选中立绘自动分层」，结果写入 `characters/<id>` 并出现在角色库。
4. **校准**：点「打开校准面板」手动微调。

### 3. AI 服务商设置
菜单「设置 → AI 服务商…」：选择服务商（智谱清言 / 豆包 / DeepSeek，自动填默认 base_url 与模型）、填 API Key、点「测试连接」、保存。配置写入 `runtime/chat_config.json`，桌宠对话直接生效。

---

## 四、桌宠交互说明

启动桌宠后（工作台点「运行」或命令行）：
- **Ctrl + 鼠标右键**：唤起/关闭常驻对话输入框（在角色下方）
- **右键菜单**：聊天 / 清空记忆
- **左键拖拽**：移动角色；移动到窗口外触发“行走”
- 待机台词按设定间隔自动播放；AI 回复可带 `[动作]` 标签触发动作

---

## 五、命令行工具

```powershell
# 完整流程：生成 + 自动分层
.venv\Scripts\python.exe tools\step2\step2_pipeline.py --photo 03.jpg --character-id photo03 --name "角色03" --gender 女 --preset B --backend comfyui

# 单独自动分层（默认 SAM；可选 segformer / color）
.venv\Scripts\python.exe tools\step2\split_general.py --input <rgba.png> --output-dir <dir> --character-id <id> --parser sam

# 手动校准面板
.venv\Scripts\python.exe tools\step2\calibrate_panel.py --dir <dir>

# 配置编辑器（独立窗口）
.venv\Scripts\python.exe tools\character_editor.py --dir <dir>

# 运行桌宠
.venv\Scripts\python.exe runtimepp.py --character <角色目录> --list-actions
```

校准面板快捷键：
`1-9 选部件` · `0/E 橡皮` · `B 涂刷` · `L 套索` · `W 智能套索` · `P 枢轴` · `V 视图` · `G 网格` · `S 保存` · `R 重载` · `Ctrl+Z 撤销` · `Esc 回到涂刷` · 中键/右键拖动平移 · `Ctrl+滚轮` 缩放。

---

## 六、打包与分发

### 一键打包
双击 `build.bat`（自动建 `.venv`、装依赖与 PyInstaller、跑打包），或：

```powershell
.venv\Scripts\python.exe build_exe.py
```

产物：`dist\WindowPetStudio\`（约 548MB，onedir）：
```
dist\WindowPetStudio├─ WindowPetStudio.exe        # 双击启动工作台
├─ characters\                # 角色库（可增删改，无需重打包）
├─ assetsctions\            # 动作库（可增删改，无需重打包）
├─ runtime\chat_config.json   # AI 服务商配置
├─ photo_cartoon_instance\    # 生成输出目录
└─ _internal\                 # Python 运行时 + 模型（只读）
```

**只有改代码/功能时才需要重新打包**；加角色、加动作、改配置都不需要。

### 分发给别人
直接把 `dist\WindowPetStudio\` 文件夹压缩发出去即可（**不要带 `.venv`**，exe 已自带运行时）。对方解压后双击 exe 即用，无需装 Python。注意：
1. **发之前清空 `runtime\chat_config.json` 里的 `api_key`**（否则会泄露你的 Key），让对方在「设置→AI 服务商」填自己的。
2. 「生成」功能依赖对方本机 ComfyUI(8188)；分层/配置/运行不受影响。
3. 未签名 exe 首次运行可能被 Windows SmartScreen 拦截，点「更多信息 → 仍要运行」。

---

## 七、目录结构

```
Window_Pet_Generator/
├─ contracts/            # 契约：rig_contract.json、character/action schema
├─ runtime/              # 桌宠运行时（渲染/动作/气泡/点击穿透/对话）
├─ tools/
│   ├─ studio.py         # 工作台（角色库 + 新建向导 + AI 设置）
│   ├─ character_editor.py
│   ├─ validate.py
│   └─ step2/            # 生成后端、自动分层、校准面板、遮挡修复
├─ assets/
│   ├─ actions/          # 共享动作库（*.json）
│   └─ characters/       # 示例角色 demo、demo2
├─ characters/           # 你的角色库（工作台管理，已 gitignore）
├─ models/               # 模型（mobilesam、anime_face_seg 已入库；大模型见文档）
├─ app_paths.py          # 开发/冻结模式路径
├─ build_exe.py / build.bat / WindowPetStudio.spec   # 打包
└─ requirements.txt
```

---

## 八、契约与自定义动作

### 9 部件契约
角色目录结构：
```
<角色>/character.json      # persona、knowledge、idle_lines、rig.parts(pivot)
<角色>/parts/*.png         # head/body/arm_l/arm_r/leg_l/leg_r/eye_l/eye_r/mouth
<角色>/preview.png  source.png  memory.json  history.json
```

### 添加动作
在 `assets/actions/` 放一个 JSON 即可（重启桌宠/工作台后生效，**无需重新打包**）：

```json
{
  "id": "dance",
  "display_name": "跳舞",
  "duration": 1.6,
  "loop": true,
  "easing": "ease_in_out",
  "tracks": {
    "body": { "rot": [ {"t":0,"v":0}, {"t":0.5,"v":8}, {"t":1,"v":-8}, {"t":1.6,"v":0} ] }
  }
}
```

要点：
- `id` 必须与文件名一致（`dance.json` → `"id":"dance"`）；
- `tracks` 的键只能是 9 个部件名，通道为 `rot/pos/scale`；
- 新动作会同步出现在配置页「绑定动作」下拉（显示 `display_name`），AI 也可用 `[dance]` 标签触发。

---

## 九、已实现 / 未实现

### ✅ 已实现
- 9 部件 cut-out 契约 + 8 个共享动作 + 运行时渲染
- 照片 → A-pose Q 版立绘（本地 ComfyUI，3 seed，相似度预设 A/B/C，性别）
- SAM 提示式 + 几何规则的自动分层（黑西装/长裙等案例可用）
- 手动校准面板（笔刷/套索/智能套索/枢轴/网格/缩放平移/撤销）
- 遮挡修复
- 配置编辑（人设/知识库/待机台词/记忆）
- AI 对话（智谱/豆包/DeepSeek 可切换，长时记忆 history.json + memory.json，反幻觉）
- 桌宠运行（透明窗口、拖拽/行走、Ctrl+右键对话、右键菜单）
- 统一工作台 + PyInstaller onedir 打包 + 数据外置

### ❌ 未实现 / 待办
- **云端生成后端**：`generate_backends/cloud.py` 为占位，照片生成仍走本地 ComfyUI
- **生成功能未内置进 exe**：打包版“生成”依赖本人电脑 ComfyUI(8188)，未自带
- **单角色独立桌宠 exe**：目前只能导出角色 zip + 完整工作台 exe，未做“只含单个角色”的独立包
- **可视化动作编辑器**：目前动作靠手写 JSON
- **情绪词→动作映射可配置化**：`EMOTION_TO_ACTION` 仍写死在 `runtime/chat.py`（AI 可用 `[动作id]` 标签触发任意动作）
- **眼睛/嘴定位**：`anime_face_seg` 在部分角色上偶尔定位不准（身体分层不受影响）
- **SegFormer 人体解析**：对 Q 版泛化差，已默认切到 SAM+几何，`--parser segformer` 仅保留
- 
---

## 十、常见问题

**Q：报 `access violation` 或闪退？**
这是 onnxruntime 与 Qt 的 DLL 加载顺序问题，代码里已通过“onnxruntime 先于 Qt 导入 + 运行时钩子”处理；请用仓库内 `tools/studio.py` 或打包产物运行，不要自行调整导入顺序。

**Q：点「生成」提示后端不可用？**（还未实现）
本地 ComfyUI 未启动。启动 ComfyUI（默认 `http://127.0.0.1:8188`）后再试；分层/配置/运行不受此影响。

**Q：生成出来的角色和照片不像？**
用预设 C（最大相似），或换个 seed；生成阶段的关键参数在 `tools/step2/generate_backends/comfyui.py` 的 `CONFIGS`。

**Q：打包后 exe 双击没反应？**
用 `build.bat` 或 `python build_exe.py` 重新打包；确认 `dist\WindowPetStudio\_internal\models\` 里模型完整。

**Q：加动作后配置页没出现中文名？**
确认动作 JSON 有 `display_name` 字段、且文件名与 `id` 一致；重启工作台/桌宠后再看。
