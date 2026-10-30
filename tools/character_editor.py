# -*- coding: utf-8 -*-
"""Step 3 角色配置编辑器：编辑 character.json 的 persona / knowledge / idle_lines，差量写回。

用法:
    .venv\\Scripts\\python.exe tools\\character_editor.py --dir photo_cartoon_instance\\calib_seed777

- persona: 名字 + 人设设定
- knowledge: 键值对(添加/删除/修改)
- idle_lines: 待机台词(文本 + 绑定动作下拉框 + 权重)，添加/删除/修改
- 保存时只更新上述字段，保留 rig.parts / id / contract_version 等其余部分
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

ROOT = Path(__file__).resolve().parents[1]

# 动作库：id -> 中文名（动态读取 assets/actions/*.json，缺中文名则回退为 id）
ACTION_LABELS = {
    "blink": "眨眼", "idle_breath": "呼吸", "jump": "跳跃", "nod": "点头",
    "shake_head": "摇头", "walk": "行走", "wave": "挥手", "yawn": "打哈欠",
}


def load_action_ids() -> list[str]:
    try:
        from app_paths import actions_dir
        actions = actions_dir()
    except Exception:  # pragma: no cover
        actions = ROOT / "assets" / "actions"
    if actions.is_dir():
        return sorted(p.stem for p in actions.glob("*.json"))
    return sorted(ACTION_LABELS.keys())


def action_display(action_id: str) -> str:
    return f"{ACTION_LABELS.get(action_id, action_id)} ({action_id})"


def load_action_display_names() -> dict[str, str]:
    """从动作库 JSON 读取 display_name（id -> 中文名），新动作也能显示中文。"""
    names: dict[str, str] = {}
    try:
        from app_paths import actions_dir
        actions = actions_dir()
    except Exception:  # pragma: no cover
        actions = ROOT / "assets" / "actions"
    if actions.is_dir():
        for p in actions.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8-sig"))
                aid = str(data.get("id") or p.stem)
                names[aid] = str(data.get("display_name") or aid)
            except Exception:  # noqa: BLE001
                pass
    return names


class CharacterEditorWidget(QtWidgets.QWidget):
    """可嵌入的配置编辑部件。"""

    def __init__(self, char_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self.char_dir = char_dir
        self.json_path = char_dir / "character.json" if char_dir else None
        self.memory_path = char_dir / "memory.json" if char_dir else None
        self.doc = {}
        self.action_ids = load_action_ids()
        self.action_names = load_action_display_names()
        self._build_ui()
        if char_dir:
            self.load()

    def set_char_dir(self, char_dir: Path):
        self.char_dir = char_dir
        self.json_path = char_dir / "character.json"
        self.memory_path = char_dir / "memory.json"
        self.load()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)

        # persona
        gp = QtWidgets.QGroupBox("人设 persona")
        f = QtWidgets.QFormLayout(gp)
        self.name_edit = QtWidgets.QLineEdit()
        f.addRow("名字", self.name_edit)
        self.setting_edit = QtWidgets.QPlainTextEdit()
        self.setting_edit.setFixedHeight(70)
        f.addRow("设定", self.setting_edit)
        root.addWidget(gp)

        # knowledge
        gk = QtWidgets.QGroupBox("知识库 knowledge (键值对)")
        kv = QtWidgets.QVBoxLayout(gk)
        self.knowledge_table = QtWidgets.QTableWidget(0, 2)
        self.knowledge_table.setHorizontalHeaderLabels(["键 key", "值 value"])
        self.knowledge_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        kv.addWidget(self.knowledge_table)
        kb = QtWidgets.QHBoxLayout()
        kb.addWidget(QtWidgets.QPushButton("添加知识", clicked=self.add_knowledge))
        kb.addWidget(QtWidgets.QPushButton("删除选中", clicked=self.remove_knowledge))
        kb.addStretch()
        kv.addLayout(kb)
        root.addWidget(gk)

        # memory（对话自动提取的事实）
        gm = QtWidgets.QGroupBox("对话记忆 memory.json (自动提取，可手动增删改)")
        mv = QtWidgets.QVBoxLayout(gm)
        self.memory_table = QtWidgets.QTableWidget(0, 2)
        self.memory_table.setHorizontalHeaderLabels(["键 key", "值 value"])
        self.memory_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        mv.addWidget(self.memory_table)
        mb = QtWidgets.QHBoxLayout()
        mb.addWidget(QtWidgets.QPushButton("添加记忆", clicked=self.add_memory))
        mb.addWidget(QtWidgets.QPushButton("删除选中", clicked=self.remove_memory))
        mb.addStretch()
        mv.addLayout(mb)
        root.addWidget(gm)

        # idle_lines
        gl = QtWidgets.QGroupBox("待机台词 idle_lines (文本 + 绑定动作 + 权重)")
        lv = QtWidgets.QVBoxLayout(gl)
        self.line_table = QtWidgets.QTableWidget(0, 3)
        self.line_table.setHorizontalHeaderLabels(["台词", "绑定动作", "权重"])
        self.line_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.line_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.line_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        lv.addWidget(self.line_table)
        lb = QtWidgets.QHBoxLayout()
        lb.addWidget(QtWidgets.QPushButton("添加台词", clicked=self.add_line))
        lb.addWidget(QtWidgets.QPushButton("删除选中", clicked=self.remove_line))
        lb.addStretch()
        lv.addLayout(lb)
        root.addWidget(gl)

        # 底部按钮
        bb = QtWidgets.QHBoxLayout()
        bb.addWidget(QtWidgets.QPushButton("保存(S)", clicked=self.save))
        bb.addWidget(QtWidgets.QPushButton("重载(R)", clicked=self.load))
        bb.addStretch()
        root.addLayout(bb)
        self.status = QtWidgets.QLabel("")
        root.addWidget(self.status)

    # ---------- 数据填充 ----------
    def _action_combo(self, current_id: str) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        for aid in self.action_ids:
            name = self.action_names.get(aid) or ACTION_LABELS.get(aid, aid)
            combo.addItem(f"{name} ({aid})", aid)
        if current_id in self.action_ids:
            combo.setCurrentIndex(self.action_ids.index(current_id))
        return combo

    def _add_line_row(self, text="", action="wave", weight=1.0):
        row = self.line_table.rowCount()
        self.line_table.insertRow(row)
        self.line_table.setItem(row, 0, QtWidgets.QTableWidgetItem(text))
        self.line_table.setCellWidget(row, 1, self._action_combo(action))
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(0.1, 100.0)
        spin.setDecimals(1)
        spin.setValue(float(weight))
        self.line_table.setCellWidget(row, 2, spin)

    def load(self):
        if not self.json_path.exists():
            QtWidgets.QMessageBox.warning(self, "错误", f"找不到 {self.json_path}")
            return
        self.doc = json.loads(self.json_path.read_text(encoding="utf-8"))
        persona = self.doc.get("persona") or {}
        self.name_edit.setText(persona.get("name", ""))
        self.setting_edit.setPlainText(persona.get("setting", ""))

        self.knowledge_table.setRowCount(0)
        for item in self.doc.get("knowledge") or []:
            row = self.knowledge_table.rowCount()
            self.knowledge_table.insertRow(row)
            self.knowledge_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(item.get("key", ""))))
            self.knowledge_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(item.get("value", ""))))

        self.memory_table.setRowCount(0)
        memory = []
        if self.memory_path.exists():
            try:
                data = json.loads(self.memory_path.read_text(encoding="utf-8-sig"))
                if isinstance(data, list):
                    memory = data
            except (OSError, ValueError):
                memory = []
        for item in memory:
            row = self.memory_table.rowCount()
            self.memory_table.insertRow(row)
            self.memory_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(item.get("key", ""))))
            self.memory_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(item.get("value", ""))))

        self.line_table.setRowCount(0)
        for line in self.doc.get("idle_lines") or []:
            self._add_line_row(
                str(line.get("text", "")),
                str(line.get("action", "wave")),
                float(line.get("weight", 1.0)),
            )
        self.status.setText(f"已加载: {self.json_path}")

    # ---------- 添加/删除 ----------
    def add_knowledge(self):
        row = self.knowledge_table.rowCount()
        self.knowledge_table.insertRow(row)
        self.knowledge_table.setItem(row, 0, QtWidgets.QTableWidgetItem(""))
        self.knowledge_table.setItem(row, 1, QtWidgets.QTableWidgetItem(""))

    def remove_knowledge(self):
        rows = sorted({i.row() for i in self.knowledge_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.knowledge_table.removeRow(r)

    def add_memory(self):
        row = self.memory_table.rowCount()
        self.memory_table.insertRow(row)
        self.memory_table.setItem(row, 0, QtWidgets.QTableWidgetItem(""))
        self.memory_table.setItem(row, 1, QtWidgets.QTableWidgetItem(""))

    def remove_memory(self):
        rows = sorted({i.row() for i in self.memory_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.memory_table.removeRow(r)

    def add_line(self):
        self._add_line_row("", self.action_ids[0] if self.action_ids else "wave", 1.0)

    def remove_line(self):
        rows = sorted({i.row() for i in self.line_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.line_table.removeRow(r)

    # ---------- 收集 + 保存 ----------
    def _collect(self):
        self.doc["persona"] = {
            "name": self.name_edit.text().strip(),
            "setting": self.setting_edit.toPlainText().strip(),
        }
        knowledge = []
        for r in range(self.knowledge_table.rowCount()):
            k = (self.knowledge_table.item(r, 0).text() if self.knowledge_table.item(r, 0) else "").strip()
            v = (self.knowledge_table.item(r, 1).text() if self.knowledge_table.item(r, 1) else "").strip()
            if k or v:
                knowledge.append({"key": k, "value": v})
        self.doc["knowledge"] = knowledge

        idle_lines = []
        for r in range(self.line_table.rowCount()):
            text = (self.line_table.item(r, 0).text() if self.line_table.item(r, 0) else "").strip()
            combo = self.line_table.cellWidget(r, 1)
            action = combo.currentData() if combo else "wave"
            spin = self.line_table.cellWidget(r, 2)
            weight = float(spin.value()) if spin else 1.0
            if text:
                idle_lines.append({"text": text, "action": action, "weight": weight})
        self.doc["idle_lines"] = idle_lines

    def save(self):
        self._collect()
        # 差量写回：只改了 persona/knowledge/idle_lines，其余(rig/id/contract_version)原样保留
        self.json_path.write_text(json.dumps(self.doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # 写回 memory.json
        memory = []
        for r in range(self.memory_table.rowCount()):
            k = (self.memory_table.item(r, 0).text() if self.memory_table.item(r, 0) else "").strip()
            v = (self.memory_table.item(r, 1).text() if self.memory_table.item(r, 1) else "").strip()
            if k or v:
                memory.append({"key": k, "value": v})
        self.memory_path.write_text(json.dumps(memory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        ok, txt = self._validate()
        msg = "保存完成，校验: " + ("PASS" if ok else "FAIL")
        self.status.setText(msg)
        QtWidgets.QMessageBox.information(self, "保存", msg + (("\n" + txt[:800]) if not ok else ""))

    def _validate(self):
        try:
            from app_paths import is_frozen
            if is_frozen():
                return True, "(冻结模式，跳过子进程校验)"
        except Exception:  # pragma: no cover
            pass
        cmd = [sys.executable, str(ROOT / "tools" / "validate.py"), "character", str(self.char_dir),
               "--actions-dir", str(ROOT / "assets" / "actions")]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


class CharacterEditor(QtWidgets.QMainWindow):
    """独立窗口封装（兼容 CLI: --dir 用法）。"""

    def __init__(self, char_dir: Path):
        super().__init__()
        self.editor = CharacterEditorWidget(char_dir)
        self.setCentralWidget(self.editor)
        self.setWindowTitle("角色配置编辑器 - " + char_dir.name)
        self.resize(760, 680)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="角色目录(含 character.json)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    app = QtWidgets.QApplication(sys.argv)
    win = CharacterEditor(Path(args.dir))
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
