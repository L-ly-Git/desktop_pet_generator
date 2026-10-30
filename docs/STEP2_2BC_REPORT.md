# Step 2-B/2-C 报告（Route A：9 部件角色生成与校验）

> 日期：2026-10-24  
> 路线：A（模板驱动卡通小人）  
> 状态：2-B/2-C 已完成  
> 说明：2-D 可视化校准面板、2-E 最终验收仍待开始。

## 1. 生成的角色

| 角色 id | 来源照片 | 名称 | 发长 | 服装轮廓 | 眼镜 | 契约校验 |
|---|---|---|---:|---|---:|---|
| `photo_char_01` | 02.jpg（半身） | 照片角色 01 | medium | dress | 是 | PASS |
| `photo_char_02` | 03.jpg（全身正面） | 照片角色 02 | long | tunic | 否 | PASS |
| `photo_char_03` | 04.jpg（全身 3/4 侧） | 照片角色 03 | long | tunic | 否 | PASS |

角色目录：

- `assets/characters/photo_char_01/`
- `assets/characters/photo_char_02/`
- `assets/characters/photo_char_03/`

每个目录包含：

- `parts/head.png`
- `parts/body.png`
- `parts/arm_l.png` / `parts/arm_r.png`
- `parts/leg_l.png` / `parts/leg_r.png`
- `parts/eye_l.png` / `parts/eye_r.png`
- `parts/mouth.png`
- `character.json`
- `preview.png`

所有部件均为 `512×512` 全画布透明 PNG；`character.json` 的 `contract_version` 为 `1.0`；`idle_lines` 与 demo 相同（5 条：wave / nod / blink / yawn / shake_head）。

## 2. 预览

![三个照片角色的卡通小人预览](../artifacts/step2/chibi_gallery.png)

## 3. 动作复用与运行时验证

对 `photo_char_01` 跑共享动作快照：

![photo_char_01 动作复用](../artifacts/step2/photo_char_01_actions.png)

1-E 基准（`photo_char_01`，0.30 缩放，18 秒）：

| 指标 | 实测 |
|---|---:|
| 平均 FPS | 61.26 |
| p95 帧时间 | 20.17ms |
| 平均 CPU | 14.60% |
| 内存增长 | +4.0MB |
| 动作覆盖 | 8/8 |
| 待机台词/气泡 | 通过 |
| 拖拽/行走/右键菜单 | 通过 |
| 结果 | PASS |

三个角色都通过了运行时窗口冒烟测试：

- `photo_char_01`：exit 0
- `photo_char_02`：exit 0
- `photo_char_03`：exit 0

基准报告：`artifacts/step2/photo_char_01_benchmark.json`

## 4. 与 2-B/2-C 原计划的差异

Route A 的图层不是从照片硬拆手臂/腿，而是：

1. 用 SCRFD/BiSeNet/MODNet 提取照片特征；
2. 将特征映射到 Q 版卡通模板；
3. 直接生成干净的 9 部件图层和 pivot。

因此 2-B/2-C 不需要先用矩形框手动分割身体/四肢；身体/四肢由模板保证清洁和可绑定。代价是角色是“风格化卡通小人”，不保证严格长相一致。

## 5. 已知限制

- 不是严格的人脸 likeness；发色、肤色、服装颜色和发型特征来自照片分析。
- BiSeNet 在 3/4 侧脸、小脸、头发/帽子场景下可能把头发识别成 hat，颜色会被近似处理。
- 02 是半身照，但模板仍生成完整腿部。
- 眼镜目前是简单圆框；复杂配饰未支持。
- 长发烘焙在 head 中，头部旋转会带动头发。
- 2-D 可视化校准面板尚未实现；当前参数调整需要改 profile/重新生成。
- 2-E 最终验收尚未开始。
- Route B（本地扩散模型）尚未下载模型，留作后续增强。

## 6. 下一步

- 2-D：做一个最小校准面板，允许调整肤色/发色/服装色、发长、服装轮廓、pivot 和 z 顺序；
- 2-E：对三张照片做最终质量/性能验收；
- 或先实现 Route B：本地扩散模型 Q 版生成（5–7GB，RTX 4060）。