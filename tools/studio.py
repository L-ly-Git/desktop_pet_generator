# -*- coding: utf-8 -*-
"""Step 5 工作台（统一前端）：角色库 + 生成向导 + AI 设置 + 子进程调度。

用法:
    .venv\\Scripts\\python.exe tools\\studio.py

- 角色库：扫描 characters/，运行/配置/分层/删除/打开目录/导入。
- 新建角色：生成向导（照片 -> 本地ComfyUI/云端 -> 3 seed 预览 -> 自动分层 -> 校准）。
- AI 设置：选择服务商（智谱清言/豆包/DeepSeek），填 API key，测试连接。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# 双击（无控制台）运行时 sys.stdout/stderr 为 None，统一替换为空设备，
# 避免 print() / reconfigure() 抛 AttributeError。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")

# 关键：onnxruntime 的 C 扩展必须在 Qt 之前导入，否则 Windows 上 DLL 冲突会触发 access violation。
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import onnxruntime  # noqa: F401, E402

from PyQt5 import QtCore, QtGui, QtWidgets
from tools.character_editor import CharacterEditorWidget
from app_paths import data_root, is_frozen

CHARACTERS_DIR = data_root() / "characters"
RUNTIME_APP = ROOT / "runtime" / "app.py"
EDITOR_APP = ROOT / "tools" / "character_editor.py"
CALIB_APP = ROOT / "tools" / "step2" / "calibrate_panel.py"
SPLIT_APP = ROOT / "tools" / "step2" / "split_general.py"
CHAT_CONFIG = data_root() / "runtime" / "chat_config.json"

# 冻结模式：脚本 -> 子进程模式（exe 重新调用自身 --mode）
MODE_SCRIPTS = {
    "run": RUNTIME_APP,
    "calibrate": CALIB_APP,
    "split": SPLIT_APP,
}

PART_NAMES = ["head", "body", "arm_l", "arm_r", "leg_l", "leg_r", "eye_l", "eye_r", "mouth"]
SEEDS = [12345, 777, 2026]

AI_PROVIDERS = {
    "智谱清言": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    "豆包": {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": "doubao-1-5-lite-32k-250115"},
    "DeepSeek": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
}


def make_cmd(script: Path, args: list[str]) -> list[str]:
    """生成子进程命令：冻结模式用 exe 自身 --mode 分发，开发模式用 python 跑脚本。"""
    if is_frozen():
        mode = next((m for m, sp in MODE_SCRIPTS.items() if Path(sp).resolve() == Path(script).resolve()), None)
        return [sys.executable, "--mode", mode, *args] if mode else [sys.executable, *args]
    return [sys.executable, str(script), *args]


def launch_script(script: Path, args: list[str]) -> subprocess.Popen:
    cmd = make_cmd(script, args)
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    return subprocess.Popen(cmd, cwd=str(data_root()), creationflags=flags,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def read_character(d: Path) -> dict:
    info = {"dir": d, "id": d.name, "name": d.name, "valid": False, "preview": None,
            "setting": "", "parts_ok": True, "missing_parts": [], "error": ""}
    cj = d / "character.json"
    try:
        data = json.loads(cj.read_text(encoding="utf-8-sig"))
        info["id"] = data.get("id", d.name)
        info["name"] = (data.get("persona") or {}).get("name") or info["id"]
        info["setting"] = (data.get("persona") or {}).get("setting", "")
        rig_parts = (data.get("rig") or {}).get("parts", {})
        missing = [n for n in PART_NAMES if n not in rig_parts]
        info["missing_parts"] = missing
        info["parts_ok"] = not missing
        info["valid"] = True
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)
    prev = d / "preview.png"
    if prev.is_file():
        info["preview"] = prev
    return info


def list_characters() -> list[dict]:
    result = []
    if not CHARACTERS_DIR.is_dir():
        return result
    for d in sorted(CHARACTERS_DIR.iterdir()):
        if d.is_dir() and (d / "character.json").is_file():
            result.append(read_character(d))
    return result


class ProcessWorker(QtCore.QThread):
    """在后台线程跑一个子进程，逐行回传 stdout。"""
    log = QtCore.pyqtSignal(str)
    finished_rc = QtCore.pyqtSignal(int)

    def __init__(self, cmd: list[str], parent=None):
        super().__init__(parent)
        self.cmd = cmd

    def run(self):
        p = subprocess.Popen(self.cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace")
        assert p.stdout is not None
        for line in p.stdout:
            self.log.emit(line.rstrip())
        rc = p.wait()
        self.finished_rc.emit(rc)


class GenerateWorker(QtCore.QThread):
    """后台跑生成后端（本地 ComfyUI / 云端）。"""
    log = QtCore.pyqtSignal(str)
    done = QtCore.pyqtSignal(list)

    def __init__(self, backend, photo: Path, cid: str, gender: str, preset: str, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.photo = photo
        self.cid = cid
        self.gender = gender
        self.preset = preset

    def run(self):
        try:
            results = self.backend.generate(self.photo, self.cid, gender=self.gender,
                                            preset=self.preset, seeds=SEEDS, on_log=self.log.emit)
        except Exception as exc:  # noqa: BLE001
            self.log.emit(f"生成异常: {exc}")
            results = [None] * len(SEEDS)
        self.done.emit(results)


class AISettingsDialog(QtWidgets.QDialog):
    """AI 服务商设置：选服务商 / 填 key / 测试连接。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 服务商设置")
        self.resize(520, 360)
        root = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        self.provider = QtWidgets.QComboBox()
        for name in AI_PROVIDERS:
            self.provider.addItem(name)
        self.provider.currentTextChanged.connect(self._on_provider)
        form.addRow("服务商", self.provider)

        self.base_url = QtWidgets.QLineEdit()
        form.addRow("base_url", self.base_url)
        self.model = QtWidgets.QLineEdit()
        form.addRow("模型", self.model)
        self.api_key = QtWidgets.QLineEdit()
        self.api_key.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("API Key", self.api_key)
        root.addLayout(form)

        tip = QtWidgets.QLabel("Key 仅保存在本机 runtime/chat_config.json（明文），请勿外传。")
        tip.setStyleSheet("color:#999;")
        root.addWidget(tip)

        self.status = QtWidgets.QLabel("")
        root.addWidget(self.status)

        btns = QtWidgets.QDialogButtonBox()
        self.test_btn = btns.addButton("测试连接", QtWidgets.QDialogButtonBox.ActionRole)
        save_btn = btns.addButton("保存", QtWidgets.QDialogButtonBox.AcceptRole)
        cancel_btn = btns.addButton("取消", QtWidgets.QDialogButtonBox.RejectRole)
        self.test_btn.clicked.connect(self._test)
        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)
        root.addWidget(btns)

        self._load()
        self._on_provider(self.provider.currentText())

    def _load(self):
        try:
            cfg = json.loads(CHAT_CONFIG.read_text(encoding="utf-8-sig"))
        except Exception:
            cfg = {}
        base = cfg.get("base_url", "")
        model = cfg.get("model", "")
        # 反查服务商
        for name, preset in AI_PROVIDERS.items():
            if preset["base_url"] == base:
                self.provider.setCurrentText(name)
                break
        self.base_url.setText(base or AI_PROVIDERS[self.provider.currentText()]["base_url"])
        self.model.setText(model or AI_PROVIDERS[self.provider.currentText()]["model"])
        self.api_key.setText(cfg.get("api_key", ""))

    def _on_provider(self, name: str):
        preset = AI_PROVIDERS.get(name)
        if preset and not self.base_url.text():
            self.base_url.setText(preset["base_url"])
        if preset and not self.model.text():
            self.model.setText(preset["model"])
        elif preset:
            self.base_url.setText(preset["base_url"])
            self.model.setText(preset["model"])

    def _test(self):
        import requests
        url = self.base_url.text().strip().rstrip("/") + "/chat/completions"
        key = self.api_key.text().strip()
        model = self.model.text().strip()
        if not key:
            self.status.setText("请先填写 API Key")
            return
        self.status.setText("测试中…")
        try:
            r = requests.post(url, headers={"Authorization": f"Bearer {key}"},
                              json={"model": model,
                                    "messages": [{"role": "user", "content": "ping"}],
                                    "max_tokens": 8}, timeout=20)
            if r.status_code == 200:
                self.status.setText("连接成功 ✓")
            else:
                self.status.setText(f"失败 HTTP {r.status_code}: {r.text[:120]}")
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"连接失败: {exc}")

    def _save(self):
        cfg = {
            "base_url": self.base_url.text().strip(),
            "model": self.model.text().strip(),
            "api_key": self.api_key.text().strip(),
            "timeout": 20,
            "history_turns": 8,
            "max_chars": 40,
            "fallback": "我现在连不上网…",
        }
        try:
            old = json.loads(CHAT_CONFIG.read_text(encoding="utf-8-sig"))
        except Exception:
            old = {}
        old.update(cfg)
        CHAT_CONFIG.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.accept()


class GenerateDialog(QtWidgets.QDialog):
    """新建角色向导：生成 + 3 seed 预览 + 自动分层。"""
    character_created = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建角色")
        self.resize(760, 620)
        self.results: list[Path | None] = []
        self.split_dir: Path | None = None
        self._build_ui()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)

        # 参数区
        form = QtWidgets.QFormLayout()
        row = QtWidgets.QHBoxLayout()
        self.photo_edit = QtWidgets.QLineEdit()
        browse = QtWidgets.QPushButton("浏览…")
        browse.clicked.connect(self._pick_photo)
        row.addWidget(self.photo_edit, 1)
        row.addWidget(browse)
        form.addRow("照片", row)

        self.cid_edit = QtWidgets.QLineEdit()
        form.addRow("角色ID", self.cid_edit)
        self.name_edit = QtWidgets.QLineEdit()
        form.addRow("名称", self.name_edit)
        self.gender = QtWidgets.QComboBox()
        self.gender.addItems(["女", "男", "auto"])
        form.addRow("性别", self.gender)
        self.preset = QtWidgets.QComboBox()
        self.preset.addItems(["B", "A", "C"])
        form.addRow("相似度预设", self.preset)
        self.backend = QtWidgets.QComboBox()
        self.backend.addItem("本地 ComfyUI", "comfyui")
        self.backend.addItem("云端生成（待接入）", "cloud")
        form.addRow("生成后端", self.backend)
        root.addLayout(form)

        self.gen_btn = QtWidgets.QPushButton("开始生成（3 个 seed）")
        self.gen_btn.clicked.connect(self._generate)
        root.addWidget(self.gen_btn)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        root.addWidget(self.log)

        # seed 预览
        gp = QtWidgets.QGroupBox("选择立绘")
        glay = QtWidgets.QHBoxLayout(gp)
        self.seed_radios: dict[int, QtWidgets.QRadioButton] = {}
        self.seed_group = QtWidgets.QButtonGroup(self)
        for seed in SEEDS:
            rb = QtWidgets.QRadioButton(f"seed {seed}")
            self.seed_group.addButton(rb, seed)
            glay.addWidget(rb)
            self.seed_radios[seed] = rb
        glay.addStretch(1)
        root.addWidget(gp)
        self.preview = QtWidgets.QLabel("生成后在此显示所选立绘")
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.preview.setMinimumHeight(260)
        self.preview.setStyleSheet("background:#202020; border:1px solid #444;")
        root.addWidget(self.preview, 1)
        self.seed_group.buttonClicked[int].connect(self._show_seed)

        # 分层 + 收尾
        self.split_btn = QtWidgets.QPushButton("对选中立绘自动分层")
        self.split_btn.setEnabled(False)
        self.split_btn.clicked.connect(self._split)
        root.addWidget(self.split_btn)
        self.calib_btn = QtWidgets.QPushButton("打开校准面板")
        self.calib_btn.setEnabled(False)
        self.calib_btn.clicked.connect(self._open_calib)
        root.addWidget(self.calib_btn)

        bottom = QtWidgets.QHBoxLayout()
        bottom.addStretch(1)
        self.exit_btn = QtWidgets.QPushButton("退出")
        self.exit_btn.clicked.connect(self.reject)
        bottom.addWidget(self.exit_btn)
        root.addLayout(bottom)

    def _pick_photo(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择照片", str(ROOT), "图片 (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.photo_edit.setText(path)
            stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(path).stem).strip("_")
            if not self.cid_edit.text():
                self.cid_edit.setText(stem or "photo")
            if not self.name_edit.text():
                self.name_edit.setText(stem or "照片角色")

    def _generate(self):
        from tools.step2.generate_backends import get_backend
        photo = Path(self.photo_edit.text().strip())
        if not photo.is_file():
            QtWidgets.QMessageBox.warning(self, "生成", "请先选择有效的照片文件。")
            return
        cid = re.sub(r"[^A-Za-z0-9_-]+", "_", self.cid_edit.text()).strip("_") or "photo"
        backend = get_backend(self.backend.currentData())
        ok, reason = backend.available()
        if not ok:
            QtWidgets.QMessageBox.warning(self, "生成", f"后端不可用：\n{reason}")
            return
        self.log.clear()
        self.results = []
        self.gen_btn.setEnabled(False)
        self.worker = GenerateWorker(backend, photo, cid, self.gender.currentText(),
                                     self.preset.currentText())
        self.worker.log.connect(lambda s: self.log.appendPlainText(s))
        self.worker.done.connect(self._on_generated)
        self.worker.start()

    def _on_generated(self, results):
        self.gen_btn.setEnabled(True)
        self.results = results
        self.log.appendPlainText("=== 生成结束 ===")
        for seed, path in zip(SEEDS, results):
            self.log.appendPlainText(f"  seed {seed}: {path or '失败'}")
        # 默认选中 seed777，否则第一个成功
        default = 777 if results[SEEDS.index(777)] is not None else None
        if default is None:
            for seed, path in zip(SEEDS, results):
                if path is not None:
                    default = seed
                    break
        if default is not None:
            self.seed_radios[default].setChecked(True)
            self._show_seed(default)
            self.split_btn.setEnabled(True)
        else:
            self.preview.setText("（全部 seed 生成失败）")

        ok_count = sum(1 for p in results if p is not None)
        if ok_count > 0:
            QtWidgets.QMessageBox.information(self, "生成", f"已经生成（{ok_count}/{len(results)} 个 seed 成功）")
        else:
            QtWidgets.QMessageBox.warning(self, "生成", "生成失败（全部 seed 失败）")

    def _show_seed(self, seed: int):
        if not self.results:
            return
        path = self.results[SEEDS.index(seed)]
        if path is None or not Path(path).is_file():
            self.preview.setText(f"seed {seed}: 无结果")
            return
        pm = QtGui.QPixmap(str(path))
        if pm.isNull():
            self.preview.setText(f"seed {seed}: 加载失败")
            return
        pm = pm.scaled(self.preview.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.preview.setPixmap(pm)

    def _selected_seed(self) -> int | None:
        return self.seed_group.checkedId()

    def _split(self):
        seed = self._selected_seed()
        if seed is None or seed not in self.seed_radios or not self.results:
            return
        path = self.results[SEEDS.index(seed)]
        if path is None or not Path(path).is_file():
            QtWidgets.QMessageBox.warning(self, "分层", "所选 seed 没有可用的立绘。")
            return
        cid = re.sub(r"[^A-Za-z0-9_-]+", "_", self.cid_edit.text()).strip("_") or "photo"
        name = self.name_edit.text().strip() or "照片角色"
        self.split_dir = CHARACTERS_DIR / cid
        self.log.appendPlainText(f"=== 自动分层 -> {self.split_dir} ===")
        self.split_btn.setEnabled(False)
        split_args = ["--input", str(path), "--output-dir", str(self.split_dir),
                      "--character-id", cid, "--name", name]
        if is_frozen():
            split_args.append("--no-validate")
        self.pw = ProcessWorker(make_cmd(SPLIT_APP, split_args))
        self.pw.log.connect(lambda s: self.log.appendPlainText(s))
        self.pw.finished_rc.connect(self._on_split)
        self.pw.start()

    def _on_split(self, rc: int):
        self.split_btn.setEnabled(True)
        if rc == 0:
            self.log.appendPlainText("=== 分层完成（已写入角色库） ===")
            self.calib_btn.setEnabled(True)
            self.character_created.emit()
        else:
            self.log.appendPlainText(f"=== 分层失败(rc={rc}) ===")

    def _open_calib(self):
        if self.split_dir:
            launch_script(CALIB_APP, ["--dir", str(self.split_dir)])


class StudioWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Window Pet Studio")
        self.resize(1080, 720)
        self._build_menus()
        self._build_ui()
        self.refresh()

    def _build_menus(self):
        bar = self.menuBar()
        m = bar.addMenu("文件")
        a_new = m.addAction("新建角色…")
        a_new.triggered.connect(self._new_character)
        a_import = m.addAction("导入已有角色目录…")
        a_import.triggered.connect(self._import)
        m.addSeparator()
        a_exit = m.addAction("退出")
        a_exit.triggered.connect(self.close)
        s = bar.addMenu("设置")
        a_ai = s.addAction("AI 服务商…")
        a_ai.triggered.connect(lambda: AISettingsDialog(self).exec_())

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)

        left = QtWidgets.QVBoxLayout()
        left.addWidget(QtWidgets.QLabel("<b>角色库</b>"))
        self.list = QtWidgets.QListWidget()
        self.list.setMinimumWidth(240)
        self.list.currentItemChanged.connect(self._on_select)
        left.addWidget(self.list, 1)

        btn_new = QtWidgets.QPushButton("新建角色…")
        btn_new.clicked.connect(self._new_character)
        left.addWidget(btn_new)
        btn_import = QtWidgets.QPushButton("导入已有角色目录…")
        btn_import.clicked.connect(self._import)
        left.addWidget(btn_import)

        act = QtWidgets.QGridLayout()
        self.btn_run = QtWidgets.QPushButton("运行")
        self.btn_edit = QtWidgets.QPushButton("配置")
        self.btn_calib = QtWidgets.QPushButton("分层")
        self.btn_pack = QtWidgets.QPushButton("打包")
        self.btn_delete = QtWidgets.QPushButton("删除")
        self.btn_open = QtWidgets.QPushButton("打开目录")
        self.btn_run.clicked.connect(self._run)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_calib.clicked.connect(self._calibrate)
        self.btn_pack.clicked.connect(self._pack)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_open.clicked.connect(self._open_dir)
        act.addWidget(self.btn_run, 0, 0)
        act.addWidget(self.btn_edit, 0, 1)
        act.addWidget(self.btn_calib, 1, 0)
        act.addWidget(self.btn_pack, 1, 1)
        act.addWidget(self.btn_delete, 2, 0)
        act.addWidget(self.btn_open, 2, 1)
        left.addLayout(act)
        root.addLayout(left, 0)

        right = QtWidgets.QVBoxLayout()
        self.tabs = QtWidgets.QTabWidget()

        detail = QtWidgets.QWidget()
        dlay = QtWidgets.QVBoxLayout(detail)
        self.preview = QtWidgets.QLabel("未选择角色")
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.preview.setMinimumSize(360, 320)
        self.preview.setStyleSheet("background:#202020; border:1px solid #444;")
        dlay.addWidget(self.preview, 1)
        self.info = QtWidgets.QPlainTextEdit()
        self.info.setReadOnly(True)
        self.info.setMaximumHeight(160)
        dlay.addWidget(self.info)
        self.tabs.addTab(detail, "详情")

        self.config_editor = CharacterEditorWidget()
        self.tabs.addTab(self.config_editor, "配置")

        right.addWidget(self.tabs, 1)
        root.addLayout(right, 1)

        self.statusBar().showMessage(f"角色目录：{CHARACTERS_DIR}")

    def refresh(self):
        self.list.clear()
        self.current = None
        for info in list_characters():
            flag = "" if info["valid"] else " ⚠"
            item = QtWidgets.QListWidgetItem(f"{info['name']}  ({info['id']}){flag}")
            item.setData(QtCore.Qt.UserRole, str(info["dir"]))
            if not info["valid"]:
                item.setForeground(QtGui.QBrush(QtGui.QColor("#e08080")))
            self.list.addItem(item)
        self._update_buttons()
        self.statusBar().showMessage(f"共 {self.list.count()} 个角色 | 目录：{CHARACTERS_DIR}")

    def _selected_dir(self):
        item = self.list.currentItem()
        if item is None:
            return None
        return Path(item.data(QtCore.Qt.UserRole))

    def _on_select(self, *_):
        self._update_buttons()
        d = self._selected_dir()
        if d is None:
            self.preview.setText("未选择角色")
            self.info.setPlainText("")
            return
        info = read_character(d)
        if info["preview"]:
            pm = QtGui.QPixmap(str(info["preview"]))
            if not pm.isNull():
                pm = pm.scaled(self.preview.size(), QtCore.Qt.KeepAspectRatio,
                               QtCore.Qt.SmoothTransformation)
                self.preview.setPixmap(pm)
            else:
                self.preview.setText("预览加载失败")
        else:
            self.preview.setText("（无 preview.png）")
        lines = [f"ID: {info['id']}", f"名称: {info['name']}", f"目录: {info['dir']}",
                 f"校验: {'通过' if info['valid'] else '失败'}"]
        if info["missing_parts"]:
            lines.append(f"缺失部件: {', '.join(info['missing_parts'])}")
        if info["setting"]:
            lines.append(f"设定: {info['setting']}")
        if info.get("error"):
            lines.append(f"错误: {info['error']}")
        self.info.setPlainText("\n".join(lines))
        if (d / "character.json").is_file():
            self.config_editor.set_char_dir(d)

    def _update_buttons(self):
        has = self._selected_dir() is not None
        for b in (self.btn_run, self.btn_edit, self.btn_calib, self.btn_pack,
                  self.btn_delete, self.btn_open):
            b.setEnabled(has)

    def _run(self):
        d = self._selected_dir()
        if d:
            launch_script(RUNTIME_APP, ["--character", str(d)])

    def _edit(self):
        if self._selected_dir():
            self.tabs.setCurrentIndex(1)

    def _calibrate(self):
        d = self._selected_dir()
        if d:
            launch_script(CALIB_APP, ["--dir", str(d)])

    def _pack(self):
        d = self._selected_dir()
        if d is None:
            return
        default = str(ROOT / (d.name + ".zip"))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "导出角色包", default, "Zip 包 (*.zip)")
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        keep = {"character.json", "preview.png", "source.png", "memory.json", "history.json"}
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(d.rglob("*")):
                if not f.is_file():
                    continue
                rel = f.relative_to(d)
                if rel.parts[0] == "parts" or rel.name in keep:
                    zf.write(f, rel)
        QtWidgets.QMessageBox.information(self, "导出", f"已导出角色包：\n{path}")

    def _delete(self):
        d = self._selected_dir()
        if d is None:
            return
        root = CHARACTERS_DIR.resolve()
        resolved = d.resolve()
        if root not in resolved.parents:
            QtWidgets.QMessageBox.warning(self, "删除", "拒绝：目录不在 characters/ 内。")
            return
        ret = QtWidgets.QMessageBox.question(
            self, "删除角色", f"确定删除角色目录？\n{resolved}\n（不可恢复）",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if ret == QtWidgets.QMessageBox.Yes:
            shutil.rmtree(resolved)
            self.refresh()

    def _open_dir(self):
        d = self._selected_dir()
        if d is None:
            return
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(d.resolve())])
        else:
            QtWidgets.QMessageBox.information(self, "打开目录", str(d.resolve()))

    def _new_character(self):
        dlg = GenerateDialog(self)
        dlg.character_created.connect(self.refresh)
        dlg.exec_()

    def _import(self):
        src = QtWidgets.QFileDialog.getExistingDirectory(self, "选择已有角色目录（含 character.json）", str(ROOT))
        if not src:
            return
        src = Path(src)
        if not (src / "character.json").is_file():
            QtWidgets.QMessageBox.warning(self, "导入", "所选目录没有 character.json。")
            return
        target = CHARACTERS_DIR / src.name
        base = target
        n = 1
        while target.exists():
            target = Path(f"{base}_{n}")
            n += 1
        shutil.copytree(src, target)
        self.refresh()
        QtWidgets.QMessageBox.information(self, "导入", f"已导入到 {target}")


def _finish(rc: int) -> int:
    """冻结模式下强制退出（onnxruntime 线程池可能阻止进程自然结束）。"""
    if is_frozen():
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:  # noqa: BLE001
            pass
        os._exit(rc)
    return rc


def main(argv=None):
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    # 子进程模式分发：<exe> --mode run|calibrate|split ...
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "--mode" and len(raw) >= 2:
        mode, rest = raw[1], raw[2:]
        if mode == "run":
            from runtime.app import main as _m
            return _finish(_m(rest))
        if mode == "split":
            from tools.step2.split_general import main as _m
            return _finish(_m(rest))
        if mode == "calibrate":
            import tools.step2.calibrate_panel as _c
            _c.sys.argv = [sys.argv[0], *rest]
            try:
                _c.main()
            except SystemExit:
                pass
            return _finish(0)

    from tools.step2.generate_backends import get_backend  # noqa: F401
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    app = QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName("Window Pet Studio")
    win = StudioWindow()
    win.show()
    return _finish(app.exec_())


if __name__ == "__main__":
    raise SystemExit(main())
