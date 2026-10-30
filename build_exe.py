# -*- coding: utf-8 -*-
"""构建 WindowPetStudio.exe（onedir）并外置数据。

用法:
    .venv\\Scripts\\python.exe build_exe.py
产物:
    dist/WindowPetStudio/WindowPetStudio.exe
    dist/WindowPetStudio/characters/            (复制现有角色)
    dist/WindowPetStudio/runtime/chat_config.json
    dist/WindowPetStudio/photo_cartoon_instance/ (生成输出目录)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist" / "WindowPetStudio"


def run(cmd: list[str]) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def make_icon() -> bool:
    """用 demo 角色预览图生成 icon.ico（供 exe 图标与桌面快捷方式使用）。"""
    candidates = [
        ROOT / "characters" / "demo" / "preview.png",
        ROOT / "assets" / "characters" / "demo" / "preview.png",
    ]
    src = next((p for p in candidates if p.is_file()), None)
    if src is None:
        print("未找到图标源图（characters/demo/preview.png），跳过图标", flush=True)
        return False
    try:
        from PIL import Image
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:  # pragma: no cover
            resample = Image.LANCZOS
        img = Image.open(src).convert("RGBA")
        img = img.resize((256, 256), resample)
        ico = ROOT / "icon.ico"
        img.save(ico, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
        print(f"已生成图标 {ico}", flush=True)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"图标生成失败（忽略）: {exc}", flush=True)
        return False


def make_shortcut() -> bool:
    """在「所有用户桌面」C:\\Users\\Public\\Desktop 创建 WindowPetStudio.lnk；
    若无写权限则回退到当前用户桌面。"""
    exe = DIST / "WindowPetStudio.exe"
    if not exe.exists():
        print("exe 不存在，跳过桌面快捷方式", flush=True)
        return False
    ps = (
        "$ErrorActionPreference = 'Stop'\n"
        "$W = New-Object -ComObject WScript.Shell\n"
        "$targets = @([Environment]::GetFolderPath('CommonDesktopDirectory'), [Environment]::GetFolderPath('Desktop'))\n"
        "$ok = $false\n"
        "foreach ($d in $targets) {\n"
        "    try {\n"
        "        $lnk = Join-Path $d 'WindowPetStudio.lnk'\n"
        "        $s = $W.CreateShortcut($lnk)\n"
        f"        $s.TargetPath = '{exe}'\n"
        f"        $s.WorkingDirectory = '{DIST}'\n"
        f"        $s.IconLocation = '{exe},0'\n"
        "        $s.Description = 'Window Pet Studio'\n"
        "        $s.Save()\n"
        "        Write-Output ('CREATED:' + $lnk)\n"
        "        $ok = $true\n"
        "        break\n"
        "    } catch {\n"
        "        Write-Output ('FAILED:' + $d)\n"
        "    }\n"
        "}\n"
        "if (-not $ok) { exit 1 }\n"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (r.stdout or "").strip()
    if r.returncode == 0 and "CREATED:" in out:
        line = next((x for x in out.splitlines() if x.startswith("CREATED:")), "")
        print(f"已创建桌面快捷方式 -> {line.replace('CREATED:', '')}", flush=True)
        return True
    print(f"桌面快捷方式创建失败: {out or r.stderr}", flush=True)
    return False


def _patch_pyinstaller():
    """onnxruntime 的 C 扩展在 Qt 之后 import 会触发 access violation。

    PyInstaller 的二进制依赖分析会开一个子进程，先把所有 Qt 包 import 进去，
    再 import 其它包，导致 onnxruntime 在 Qt 之后加载而崩溃。
    这里把 onnxruntime 加入该子进程的“抑制导入”列表（其 DLL 已由 hook 静态收集）。
    """
    import inspect
    import PyInstaller.building.build_main as bm
    src = inspect.getsource(bm.find_binary_dependencies)
    old_line = "        suppressed_imports = [package for package in _QT_BINDINGS if package not in qt_packages]\n"
    assert old_line in src, "PyInstaller 源码结构变化，补丁需要更新"
    src = src.replace(
        old_line,
        old_line + "        suppressed_imports += ['onnxruntime']\n",
        1,
    )
    ns = dict(bm.__dict__)
    exec(compile(src, "<patched-find_binary_dependencies>", "exec"), ns)
    bm.find_binary_dependencies = ns["find_binary_dependencies"]
    print("已打补丁：onnxruntime 不在依赖分析子进程中导入")


def main() -> int:
    make_icon()
    _patch_pyinstaller()
    # 1) PyInstaller 打包（进程内运行，补丁才能生效）
    import PyInstaller.__main__ as pym
    sys.argv = [sys.argv[0], "WindowPetStudio.spec", "--noconfirm",
                "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"), "--clean"]
    rc = 0
    try:
        pym.run()
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    if rc != 0:
        print("PyInstaller 失败", flush=True)
        return rc
    if not (DIST / "WindowPetStudio.exe").exists():
        print(f"未找到产物 {DIST / 'WindowPetStudio.exe'}", flush=True)
        return 1

    # 2) 外置数据：characters/
    dst_chars = DIST / "characters"
    if dst_chars.exists():
        shutil.rmtree(dst_chars)
    if (ROOT / "characters").is_dir():
        shutil.copytree(ROOT / "characters", dst_chars)
        print(f"已复制 characters -> {dst_chars}", flush=True)
    else:
        dst_chars.mkdir(parents=True, exist_ok=True)
        print("characters/ 为空，已创建空目录", flush=True)

    # 3) chat_config（无则用示例）
    (DIST / "runtime").mkdir(parents=True, exist_ok=True)
    src_cfg = ROOT / "runtime" / "chat_config.json"
    if not src_cfg.exists():
        src_cfg = ROOT / "runtime" / "chat_config.example.json"
    shutil.copyfile(src_cfg, DIST / "runtime" / "chat_config.json")
    print("已复制 chat_config", flush=True)

    # 4) 生成输出目录
    (DIST / "photo_cartoon_instance").mkdir(parents=True, exist_ok=True)
    print("已创建 photo_cartoon_instance/", flush=True)

    # 5) 外置动作库（可增删改，无需重打包；内置副本作为兜底）
    dst_actions = DIST / "assets" / "actions"
    if dst_actions.exists():
        shutil.rmtree(dst_actions)
    shutil.copytree(ROOT / "assets" / "actions", dst_actions)
    print("已复制 assets/actions（外部可编辑）", flush=True)

    # 6) 创建桌面快捷方式（图标随 exe 内嵌图标）
    make_shortcut()

    print("\n=== 构建完成 ===", flush=True)
    print(f"可执行文件: {DIST / 'WindowPetStudio.exe'}", flush=True)
    print("说明: 生成功能依赖本机 ComfyUI(8188)；characters/actions/chat_config 均外置，可自由增删改。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
