# Step 2 模型与依赖安装清单

> 所有处理均在本地完成；照片不会上传。模型下载只发生在首次准备阶段。

> Route A 当前使用 SCRFD / BiSeNet / MODNet 做照片特征提取；AnimeGANv2 已下载但未用于 Route A（其“保留真人比例、只做二次元画风”的效果不符合 cartoon chibi 需求）。Route B 将使用本地扩散模型。

## 1. Python 依赖安装位置

项目虚拟环境：

`D:\Python\item\WindowPet\Window_Pet_Generator\.venv`

第三方包安装目录：

`D:\Python\item\WindowPet\Window_Pet_Generator\.venv\Lib\site-packages`

已安装的关键版本：

| 包 | 版本 | 用途 |
|---|---:|---|
| `uniface` | 4.1.0 | SCRFD 人脸检测 + BiSeNet 人脸解析 + MODNet 人像 matte |
| `onnxruntime` | 1.31.0 | CPU ONNX 推理 |
| `numpy` | 2.5.4 | 图像/数组处理 |
| `opencv-python` | 5.0.0.93 | 图像处理（未调用 GUI 窗口） |
| `scipy` | 1.18.1 | UniFace 依赖 |
| `scikit-image` | 0.26.0 | UniFace 依赖 |
| `requests` | 2.34.2 | 模型下载 |
| `tqdm` | 4.70.1 | 下载/推理进度 |
| `Pillow` | 13.0.0 | 图像读写/预览 |
| `PyQt5` | 5.15.11 | 桌宠运行时 |

## 2. 模型文件位置

项目模型根目录：

`D:\Python\item\WindowPet\Window_Pet_Generator\models`

| 模型 | 本地路径 | 大小 | SHA-256 | 用途 |
|---|---|---:|---|---|
| AnimeGANv2 `face_paint_512_v2` | `models\animeganv2\face_paint_512_v2_0.onnx` | 8,594,990 | `1381b17ed988e14a1f3cf8954d88073c0884ff4b70128ebe599f0d6021bca63e` | 早期风格测试；Route A 未使用 |
| SCRFD 500M | `models\uniface\scrfd_500m.onnx` | 2,524,817 | `5e4447f50245bbd7966bd6c0fa52938c61474a04ec7def48753668a9d8b4ea3a` | 人脸检测/5点关键点 |
| BiSeNet ResNet18 | `models\uniface\parsing_resnet18.onnx` | 53,205,364 | `0d9bd318e46987c3bdbfacae9e2c0f461cae1c6ac6ea6d43bbe541a91727e33f` | 人脸语义解析 |
| MODNet photographic | `models\uniface\modnet_photographic.onnx` | 25,969,398 | `5069a5e306b9f5e9f4f2b0360264c9f8ea13b257c7c39943c7cf6a2ec3a102ae` | 人像 alpha matte |

总计约 **90.3 MB**；Route A 实际使用 SCRFD + BiSeNet + MODNet，约 **81.7 MB**。AnimeGANv2 仅保留作参考。

实际采用的是 UniFace 内置 MODNet，而不是单独安装 rembg；两者都是本地人像抠图方案，MODNet 模型更小且本次在 `04.jpg` 上正常输出 alpha。

## 3. UniFace 模型缓存配置

UniFace 通过环境变量 `UNIFACE_CACHE_DIR` 指定权重目录。项目代码会强制设置为：

`D:\Python\item\WindowPet\Window_Pet_Generator\models\uniface`

因此不会写入用户目录 `~/.uniface/models`，也不会使用全局缓存。

验证命令：

```bat
.venv\Scripts\python.exe tools\step2\pipeline.py --verify-models
```

该命令会检查文件存在性、大小和 SHA-256。

## 4. 模型来源

- AnimeGANv2 ONNX：
  - 来源：`https://github.com/Kazuhito00/AnimeGANv2-ONNX-Sample`
  - 文件：`model/face_paint_512_v2_0.onnx`
  - 示例仓库为 MIT License；模型权重的商业使用请同时核对上游 AnimeGANv2 项目许可。
  - Route A 未使用。
- SCRFD 500M：
  - 来源：UniFace 模型仓库，镜像 `https://hf-mirror.com/yakhyo/uniface-weights`
  - 上游：`https://github.com/yakhyo/uniface`
  - UniFace 代码为 MIT；SCRFD 权重来自 InsightFace 生态，商业分发前请核对上游许可。
- BiSeNet ResNet18：
  - 来源：UniFace 模型仓库，镜像 `https://hf-mirror.com/yakhyo/uniface-weights`
  - 上游：`https://github.com/yakhyo/face-parsing`
  - 代码 MIT；模型权重许可请核对上游仓库。
- MODNet photographic：
  - 来源：UniFace 模型仓库，镜像 `https://hf-mirror.com/yakhyo/uniface-weights`
  - 上游：`https://github.com/yakhyo/modnet`
  - 代码 MIT；模型权重许可请核对上游仓库。

> 本项目目前用于本地开发/验收。若要商业发布，请逐个核对上述模型权重许可证。

## 5. 下载方式与网络说明

- GitHub raw / release-assets 在当前网络环境下不稳定；
- BiSeNet 与 MODNet 使用 `hf-mirror.com` 的 Range 分块下载（8 路并行），下载后逐文件校验 SHA-256；
- AnimeGANv2 使用 GitHub Git Blob API 获取，校验 SHA-256；
- 模型只需准备一次，之后照片处理完全本地离线；
- 处理照片时不会发起任何上传请求。

## 6. 临时文件说明

`models\_sources` 目录包含早期失败下载的临时文件（未完成 zip/clone/range 测试片段），**不被运行时代码使用**。可以手动删除该目录，不影响已校验的模型。

## 7. 当前模型选择说明

原计划提到 rembg 的约 170MB U2Net。实际选型时发现 UniFace 已内置：

- SCRFD 人脸检测；
- BiSeNet 人脸解析；
- MODNet 人像 matte；

因此采用 UniFace 一套本地 CPU 方案，减少额外依赖和模型体积。如果后续发现 MODNet 对某些全身照边缘不够好，再补充 rembg 作为可选的 matte 后端。

## 8. Route B（本地扩散模型，尚未下载）

Route B 计划使用 RTX 4060 + SD1.5 / ControlNet / IP-Adapter / Q版 LoRA，模型将放在：

`D:\Python\item\WindowPet\Window_Pet_Generator\models\diffusion`

预计 5–7GB，尚未开始下载；需要用户确认后再安装。