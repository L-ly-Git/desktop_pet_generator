# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包 spec（onedir）。

打包进 _internal 的只读资源：contracts / assets/actions / 三个必需模型。
可写/外部数据（characters/、runtime/chat_config.json、photo_cartoon_instance/）
放在 exe 旁边，不打包进来。
"""
from pathlib import Path

ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "contracts"), "contracts"),
    (str(ROOT / "assets" / "actions"), "assets/actions"),
    (str(ROOT / "models" / "matting"), "models/matting"),
    (str(ROOT / "models" / "mobilesam"), "models/mobilesam"),
    (str(ROOT / "models" / "anime_face_seg"), "models/anime_face_seg"),
    # 真人照片分层（不卡通化）：SegFormer 人体解析 + SCRFD 人脸检测
    (str(ROOT / "models" / "human_parsing" / "segformer_b5.onnx"), "models/human_parsing"),
    (str(ROOT / "models" / "uniface" / "scrfd_500m.onnx"), "models/uniface"),
]

a = Analysis(
    ["tools/studio.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "pyi_rth_onnxruntime.py")],
    excludes=[
        "torch", "torchvision", "torchaudio",
        "matplotlib", "scipy", "pandas", "IPython", "jupyter",
        # 真人眼嘴已改用轻量 scrfd_onnx（不依赖 uniface）；auto 性别回退默认女
        "uniface", "skimage", "sklearn",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

_icon = str(ROOT / "icon.ico") if (ROOT / "icon.ico").is_file() else None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WindowPetStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI 应用，不弹控制台
    disable_windowed_traceback=False,
    icon=_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WindowPetStudio",
)
