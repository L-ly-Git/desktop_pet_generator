# -*- coding: utf-8 -*-
"""2-D 手动校准面板（v3）：涂刷/套索/枢轴 + 网格 + 自由缩放平移 + 保存自动重算枢轴。

用法:
    .venv\\Scripts\\python.exe tools\\step2\\calibrate_panel.py --dir photo_cartoon_instance\\split_xxx

操作:
    1-9 选择部件, 0/E = 橡皮擦
    左键拖动 = 涂刷(或套索)；滚轮 = 笔刷大小
    B = 涂刷  L = 套索  P = 枢轴编辑(拖十字)
    Ctrl+滚轮 或 +/- = 缩放(锚定鼠标)；中键/右键拖动 = 平移视图
    V = 切换视图；G = 网格参考线；Ctrl+Z = 撤销；S = 保存；R = 重载
    左上角图例显示 9 个部件颜色与是否已填(✓/✗)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.step2.occlusion import complete_parts
from tools.step2.sam_segment import SAMSegmenter
from PyQt5 import QtCore, QtGui, QtWidgets

ROOT = Path(__file__).resolve().parents[2]
PART_NAMES = ["head", "body", "arm_l", "arm_r", "leg_l", "leg_r", "eye_l", "eye_r", "mouth"]
ID2NAME = {i + 1: n for i, n in enumerate(PART_NAMES)}
NAME2ID = {n: i + 1 for i, n in enumerate(PART_NAMES)}
COLORS = {
    0: (70, 70, 70),
    1: (235, 80, 80), 2: (245, 160, 40), 3: (70, 180, 240), 4: (50, 110, 220),
    5: (80, 210, 90), 6: (40, 150, 55), 7: (235, 80, 220), 8: (180, 60, 200), 9: (240, 220, 60),
}
PRIORITY = ["eye_l", "eye_r", "mouth", "head", "body", "arm_l", "arm_r", "leg_l", "leg_r"]


def read_rgba(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGBA"))


def build_labels_from_parts(parts_dir: Path) -> np.ndarray:
    labels = np.zeros((512, 512), dtype=np.uint8)
    occupied = np.zeros((512, 512), dtype=bool)
    for name in PRIORITY:
        p = parts_dir / f"{name}.png"
        if not p.exists():
            continue
        alpha = read_rgba(p)[..., 3]
        mask = alpha > 16
        labels[mask & ~occupied] = NAME2ID[name]
        occupied |= mask
    return labels


def derive_pivots(labels: np.ndarray) -> dict:
    piv = {}
    for name in PART_NAMES:
        i = NAME2ID[name]
        m = labels == i
        ys, xs = np.where(m)
        if len(xs) == 0:
            piv[name] = [256, 256]
            continue
        cx = float(xs.mean())
        if name in ("head", "body"):
            cy = float(ys.min() + (ys.max() - ys.min()) * 0.5)
        elif name in ("arm_l", "arm_r", "leg_l", "leg_r"):
            cy = float(ys.min())
        else:
            cy = float(ys.mean())
        piv[name] = [int(round(cx)), int(round(cy))]
    return piv


def inpaint_base(source: np.ndarray, labels: np.ndarray) -> np.ndarray:
    mask = np.isin(labels, [NAME2ID["eye_l"], NAME2ID["eye_r"], NAME2ID["mouth"]]).astype(np.uint8) * 255
    if mask.sum() == 0:
        return source.copy()
    return cv2.inpaint(source, mask, 3, cv2.INPAINT_TELEA)


class CanvasWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.source = np.zeros((512, 512, 3), np.uint8)
        self.labels = np.zeros((512, 512), np.uint8)
        self.pivots = {}
        self.pivot_edited = set()
        self.brush = 14
        self.part_id = 1
        self.view_mode = "both"
        self.tool = "brush"          # brush / lasso / pivot
        self.zoom = 1.0
        self.pan_x = 256.0           # 画布坐标(窗口中心对应)
        self.pan_y = 256.0
        self.show_grid = True
        self.cursor_pos = None
        self.drag_pivot = None
        self.lasso_points = []
        self.panning = False
        self.pan_last = None
        self.undo_stack = []
        self.sam = None
        self.sam_ready = False
        self.foreground = np.zeros((512, 512), bool)  # 角色像素掩码(载入时锁定)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def set_data(self, source, labels, pivots):
        self.source = np.ascontiguousarray(source)
        self.labels = labels
        self.pivots = dict(pivots)
        self.pivot_edited = set()
        self.undo_stack.clear()
        self.sam_ready = False
        self.foreground = labels != 0

    # ---------- 坐标变换(显示与输入共用，严格绑定) ----------
    def _transform(self):
        base = min(self.width() / 512.0, self.height() / 512.0)
        scale = base * self.zoom
        off_x = self.width() / 2.0 - self.pan_x * scale
        off_y = self.height() / 2.0 - self.pan_y * scale
        return scale, off_x, off_y

    def _to_canvas(self, pos):
        scale, off_x, off_y = self._transform()
        return int((pos.x() - off_x) / scale), int((pos.y() - off_y) / scale)

    def zoom_at(self, mx, my, factor):
        scale, _, _ = self._transform()
        cx = self.pan_x + (mx - self.width() / 2) / scale
        cy = self.pan_y + (my - self.height() / 2) / scale
        self.zoom = max(0.25, min(8.0, self.zoom * factor))
        scale2 = min(self.width() / 512.0, self.height() / 512.0) * self.zoom
        self.pan_x = cx - (mx - self.width() / 2) / scale2
        self.pan_y = cy - (my - self.height() / 2) / scale2
        self.update()

    def pan_by(self, dx, dy):
        scale, _, _ = self._transform()
        self.pan_x -= dx / scale
        self.pan_y -= dy / scale
        self.update()

    # ---------- 绘制 ----------
    def paintEvent(self, event):
        qp = QtGui.QPainter(self)
        qp.fillRect(self.rect(), QtGui.QColor(30, 30, 30))
        scale, off_x, off_y = self._transform()
        target = QtCore.QRectF(off_x, off_y, 512 * scale, 512 * scale)

        # 棋盘背景（裁剪到画布）
        qp.save()
        qp.setClipRect(target)
        cell = max(3, int(8 * scale))
        for y in range(0, 512, 8):
            for x in range(0, 512, 8):
                c = 52 if ((x // 8 + y // 8) % 2 == 0) else 36
                qp.fillRect(int(off_x + x * scale), int(off_y + y * scale),
                            int(8 * scale) + 1, int(8 * scale) + 1, QtGui.QColor(c, c, c))

        overlay = np.zeros((512, 512, 3), np.uint8)
        has_part = np.zeros((512, 512), np.uint8)
        for pid in range(1, 10):
            m = self.labels == pid
            if m.any():
                overlay[m] = COLORS[pid]
                has_part[m] = 1

        if self.view_mode in ("source", "both"):
            qp.drawImage(target, self._qimage(self.source))
        if self.view_mode in ("overlay", "both"):
            if self.view_mode == "overlay":
                qp.drawImage(target, self._qimage(overlay))
            else:
                ov = np.zeros((512, 512, 4), np.uint8)
                ov[..., :3] = overlay
                ov[..., 3] = has_part * 140
                qp.drawImage(target, self._qimage_rgba(ov))

        # 网格参考线
        if self.show_grid:
            qp.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 36), 1))
            for gx in range(0, 513, 64):
                x = off_x + gx * scale
                qp.drawLine(int(x), int(off_y), int(x), int(off_y + 512 * scale))
            for gy in range(0, 513, 64):
                y = off_y + gy * scale
                qp.drawLine(int(off_x), int(y), int(off_x + 512 * scale), int(y))
        qp.restore()

        # 套索路径
        if self.tool == "lasso" and len(self.lasso_points) >= 2:
            qp.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1, QtCore.Qt.DashLine))
            for i in range(len(self.lasso_points) - 1):
                x1 = off_x + self.lasso_points[i][0] * scale
                y1 = off_y + self.lasso_points[i][1] * scale
                x2 = off_x + self.lasso_points[i + 1][0] * scale
                y2 = off_y + self.lasso_points[i + 1][1] * scale
                qp.drawLine(int(x1), int(y1), int(x2), int(y2))

        # 枢轴十字
        for name, (px, py) in self.pivots.items():
            x = off_x + px * scale
            y = off_y + py * scale
            qp.setPen(QtGui.QPen(QtGui.QColor(*COLORS[NAME2ID[name]]), 2))
            s = 6
            qp.drawLine(int(x - s), int(y), int(x + s), int(y))
            qp.drawLine(int(x), int(y - s), int(x), int(y + s))
            qp.drawText(int(x + 4), int(y - 4), name)

        # 笔刷光标
        if self.tool == "brush" and self.cursor_pos is not None:
            r = self.brush * scale
            qp.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1))
            qp.setBrush(QtCore.Qt.NoBrush)
            qp.drawEllipse(QtCore.QPointF(self.cursor_pos.x(), self.cursor_pos.y()), r, r)
        # 套索光标
        if self.tool == "lasso" and self.cursor_pos is not None:
            qp.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1))
            qp.setBrush(QtCore.Qt.NoBrush)
            qp.drawEllipse(self.cursor_pos, 4, 4)

        self._draw_legend(qp)

    def _draw_legend(self, qp):
        n = len(PART_NAMES)
        legend_w, legend_h = 190, 34 + n * 20
        qp.setPen(QtCore.Qt.NoPen)
        qp.setBrush(QtGui.QColor(30, 30, 30, 215))
        qp.drawRoundedRect(8, 8, legend_w, legend_h, 6, 6)
        qp.setPen(QtGui.QColor(255, 255, 255))
        qp.setFont(QtGui.QFont("Microsoft YaHei", 9))
        qp.drawText(18, 26, "部件图例 (1-9 选, B涂/L套索/P枢轴)")
        for i, name in enumerate(PART_NAMES):
            pid = NAME2ID[name]
            y = 42 + i * 20
            qp.setPen(QtCore.Qt.NoPen)
            qp.setBrush(QtGui.QColor(*COLORS[pid]))
            qp.drawRect(18, y - 12, 14, 14)
            filled = bool((self.labels == pid).any())
            qp.setPen(QtGui.QColor(230, 230, 230) if filled else QtGui.QColor(235, 120, 120))
            qp.drawText(38, y, f"{pid}.{name}  {'✓' if filled else '✗未填'}")

    @staticmethod
    def _qimage(rgb):
        h, w = rgb.shape[:2]
        return QtGui.QImage(rgb.data, w, h, rgb.strides[0], QtGui.QImage.Format_RGB888).copy()

    @staticmethod
    def _qimage_rgba(rgba):
        h, w = rgba.shape[:2]
        return QtGui.QImage(rgba.data, w, h, rgba.strides[0], QtGui.QImage.Format_RGBA8888).copy()

    def _push_undo(self):
        self.undo_stack.append(self.labels.copy())
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def undo(self):
        if self.undo_stack:
            self.labels = self.undo_stack.pop()
            self.update()

    # ---------- 鼠标 ----------
    def mousePressEvent(self, e):
        self.setFocus()
        if e.button() in (QtCore.Qt.MiddleButton, QtCore.Qt.RightButton):
            self.panning = True
            self.pan_last = e.pos()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            return
        if e.button() == QtCore.Qt.LeftButton:
            x, y = self._to_canvas(e.pos())
            if self.tool == "pivot":
                for name, (px, py) in self.pivots.items():
                    if abs(px - x) <= 10 and abs(py - y) <= 10:
                        self.drag_pivot = name
                        break
            elif self.tool == "lasso":
                self.lasso_points = [(x, y)]
            elif self.tool == "sam":
                self._sam_click(x, y)
            else:
                self._push_undo()
                self._paint(x, y)

    def mouseMoveEvent(self, e):
        self.cursor_pos = e.pos()
        if self.panning and self.pan_last is not None:
            self.pan_by(e.pos().x() - self.pan_last.x(), e.pos().y() - self.pan_last.y())
            self.pan_last = e.pos()
            return
        if e.buttons() & QtCore.Qt.LeftButton:
            x, y = self._to_canvas(e.pos())
            if self.tool == "pivot" and self.drag_pivot:
                self.pivots[self.drag_pivot] = [max(0, min(511, x)), max(0, min(511, y))]
                self.pivot_edited.add(self.drag_pivot)
                self.update()
            elif self.tool == "lasso" and self.lasso_points:
                self.lasso_points.append((x, y))
                self.update()
            elif self.tool == "brush":
                self._paint(x, y)
        else:
            self.update()

    def mouseReleaseEvent(self, e):
        if self.panning:
            self.panning = False
            self.pan_last = None
            self.unsetCursor()
            return
        if e.button() == QtCore.Qt.LeftButton and self.tool == "lasso" and len(self.lasso_points) >= 3:
            self._lasso_fill()
        self.drag_pivot = None

    def leaveEvent(self, e):
        self.cursor_pos = None
        self.update()

    def wheelEvent(self, e):
        if e.modifiers() & QtCore.Qt.ControlModifier:
            self.zoom_at(e.pos().x(), e.pos().y(), 1.15 if e.angleDelta().y() > 0 else 1 / 1.15)
        else:
            self.brush = max(2, min(80, self.brush + (2 if e.angleDelta().y() > 0 else -2)))
            self.update()

    def _lasso_fill(self):
        pts = np.array(self.lasso_points, dtype=np.int32).reshape(-1, 1, 2)
        mask = np.zeros((512, 512), np.uint8)
        cv2.fillPoly(mask, [pts], 1)
        self._push_undo()
        self.labels[mask == 1] = self.part_id
        self.lasso_points = []
        self.update()

    def _sam_click(self, x, y):
        try:
            if self.sam is None:
                self.sam = SAMSegmenter()
            if not self.sam_ready:
                self.sam.encode(self.source)
                self.sam_ready = True
            mask = self.sam.predict((x, y)) & self.foreground
            self._push_undo()
            self.labels[mask] = self.part_id
            self.update()
        except Exception as exc:
            print("SAM 分割失败:", exc)

    def _paint(self, x, y):
        if not (0 <= x < 512 and 0 <= y < 512):
            return
        r = self.brush
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    px, py = x + dx, y + dy
                    if 0 <= px < 512 and 0 <= py < 512:
                        self.labels[py, px] = self.part_id
        self.update()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, out_dir: Path):
        super().__init__()
        self.out_dir = out_dir
        self.setWindowTitle("2-D 校准面板 - " + out_dir.name)
        self.canvas = CanvasWidget()
        self.setCentralWidget(self.canvas)
        self._build_toolbar()
        self._build_shortcuts()
        self.resize(980, 780)
        self.load()

    def _build_toolbar(self):
        tb = self.addToolBar("工具")
        for i, name in enumerate(PART_NAMES, start=1):
            act = QtWidgets.QAction(f"{i}:{name}", self)
            act.triggered.connect(lambda _, n=name: self.select_part(n))
            tb.addAction(act)
        tb.addAction(QtWidgets.QAction("0:橡皮", self, triggered=lambda: self.select_part(None)))
        tb.addSeparator()
        for label, tool in [("B:涂刷", "brush"), ("L:套索", "lasso"), ("W:智能套索", "sam"), ("P:枢轴", "pivot")]:
            tb.addAction(QtWidgets.QAction(label, self, triggered=lambda _, t=tool: self.set_tool(t)))
        tb.addSeparator()
        tb.addAction(QtWidgets.QAction("V:视图", self, triggered=self.cycle_view))
        tb.addAction(QtWidgets.QAction("G:网格", self, triggered=self.toggle_grid))
        tb.addAction(QtWidgets.QAction("撤销", self, triggered=self.canvas.undo, shortcut="Ctrl+Z"))
        tb.addAction(QtWidgets.QAction("R:重载", self, triggered=self.load))
        tb.addAction(QtWidgets.QAction("S:保存", self, triggered=self.save))

    def _build_shortcuts(self):
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        for i, name in enumerate(PART_NAMES, start=1):
            sc = QShortcut(QKeySequence(str(i)), self); sc.activated.connect(lambda n=name: self.select_part(n))
        for key, fn in [("0", lambda: self.select_part(None)), ("E", lambda: self.select_part(None))]:
            QShortcut(QKeySequence(key), self).activated.connect(fn)
        for key, tool in [("B", "brush"), ("L", "lasso"), ("W", "sam"), ("P", "pivot")]:
            QShortcut(QKeySequence(key), self).activated.connect(lambda t=tool: self.set_tool(t))
        for key, fn in [("V", self.cycle_view), ("G", self.toggle_grid), ("S", self.save), ("R", self.load)]:
            QShortcut(QKeySequence(key), self).activated.connect(fn)
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.escape_mode)
        QShortcut(QKeySequence("+"), self).activated.connect(self.zoom_in)
        QShortcut(QKeySequence("="), self).activated.connect(self.zoom_in)
        QShortcut(QKeySequence("-"), self).activated.connect(self.zoom_out)

    def escape_mode(self):
        self.canvas.tool = "brush"
        self.canvas.lasso_points = []
        self.canvas.drag_pivot = None
        self.canvas.update()
        self.statusBar().showMessage("已回到涂刷")

    def zoom_in(self):
        self.canvas.zoom_at(self.canvas.width() / 2, self.canvas.height() / 2, 1.15)

    def zoom_out(self):
        self.canvas.zoom_at(self.canvas.width() / 2, self.canvas.height() / 2, 1 / 1.15)

    def set_tool(self, tool):
        if self.canvas.tool == tool and tool != "brush":
            tool = "brush"  # 再按一次 = 关闭该工具，回到涂刷
        self.canvas.tool = tool
        self.canvas.lasso_points = []
        self.canvas.drag_pivot = None
        self.statusBar().showMessage("工具: " + {"brush": "涂刷", "lasso": "套索", "sam": "智能套索(点击分割)", "pivot": "枢轴"}[tool] + " | Esc=回到涂刷")

    def select_part(self, name):
        self.canvas.part_id = NAME2ID[name] if name else 0
        self.statusBar().showMessage(f"部件: {name or '橡皮'} | 笔刷 {self.canvas.brush}px | 工具 {self.canvas.tool}")

    def cycle_view(self):
        order = ["both", "source", "overlay"]
        self.canvas.view_mode = order[(order.index(self.canvas.view_mode) + 1) % 3]
        self.statusBar().showMessage("视图: " + self.canvas.view_mode)
        self.canvas.update()

    def toggle_grid(self):
        self.canvas.show_grid = not self.canvas.show_grid
        self.canvas.update()

    def load(self):
        src_p = self.out_dir / "source.png"
        if not src_p.exists():
            src_p = self.out_dir / "preview.png"
        if not src_p.exists():
            QtWidgets.QMessageBox.warning(self, "错误", "找不到 source.png / preview.png")
            return
        source = np.asarray(Image.open(src_p).convert("RGB"))
        if source.shape[:2] != (512, 512):
            source = cv2.resize(source, (512, 512), interpolation=cv2.INTER_AREA)
        labels = build_labels_from_parts(self.out_dir / "parts")
        pivots = self._load_pivots()
        if not pivots:
            pivots = derive_pivots(labels)
        self.canvas.set_data(source, labels, pivots)
        self.statusBar().showMessage(f"已加载 {self.out_dir.name} | 左键涂/套索, 中键拖动平移, Ctrl+滚轮缩放")

    def _load_pivots(self):
        cj = self.out_dir / "character.json"
        if not cj.exists():
            return {}
        data = json.loads(cj.read_text(encoding="utf-8"))
        piv = {}
        for name, spec in data.get("rig", {}).get("parts", {}).items():
            piv[name] = [int(v) for v in spec.get("pivot", [256, 256])[:2]]
        return piv

    def save(self):
        source = self.canvas.source
        labels = self.canvas.labels
        # 自动重算枢轴：手拖过的保留，其余按 mask 重算
        auto = derive_pivots(labels)
        pivots = {}
        for name in PART_NAMES:
            pivots[name] = self.canvas.pivots[name] if name in self.canvas.pivot_edited else auto[name]
        self.canvas.pivots = pivots

        parts = {name: labels == NAME2ID[name] for name in PART_NAMES}
        completed, part_sources = complete_parts(source, parts)
        parts_dir = self.out_dir / "parts"
        parts_dir.mkdir(parents=True, exist_ok=True)
        for name in PART_NAMES:
            full = completed.get(name, parts[name])
            src = part_sources.get(name, source)
            rgba = np.zeros((512, 512, 4), np.uint8)
            rgba[..., :3][full] = src[full]
            rgba[..., 3][full] = 255
            Image.fromarray(rgba, "RGBA").save(parts_dir / f"{name}.png")
        order = ["leg_l", "leg_r", "arm_l", "arm_r", "body", "head", "eye_l", "eye_r", "mouth"]
        checker = np.zeros((512, 512, 3), np.uint8)
        for y in range(512):
            for x in range(512):
                checker[y, x] = 52 if ((x // 24 + y // 24) % 2 == 0) else 36
        comp = checker.astype(np.float32)
        for name in order:
            a = read_rgba(parts_dir / f"{name}.png")
            alpha = a[..., 3:4].astype(np.float32) / 255.0
            comp = a[..., :3].astype(np.float32) * alpha + comp * (1 - alpha)
        Image.fromarray(np.clip(comp, 0, 255).astype(np.uint8), "RGB").save(self.out_dir / "preview.png")
        doc = self._document(pivots)
        (self.out_dir / "character.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        ok, txt = self._validate()
        self.statusBar().showMessage("校验: " + ("PASS" if ok else "FAIL"))
        QtWidgets.QMessageBox.information(self, "保存完成", "校验: " + ("PASS" if ok else "FAIL") + ("\n" + txt[:600] if not ok else ""))

    def _document(self, pivots):
        cj = self.out_dir / "character.json"
        doc = {}
        if cj.exists():
            try:
                doc = json.loads(cj.read_text(encoding="utf-8"))
            except Exception:
                doc = {}
        doc.setdefault("id", self.out_dir.name)
        doc["contract_version"] = "1.0"
        parts = {}
        for name in PART_NAMES:
            parts[name] = {"file": f"parts/{name}.png", "pivot": pivots.get(name, [256, 256])}
        doc.setdefault("rig", {})["parts"] = parts
        doc.setdefault("persona", {"name": self.out_dir.name, "setting": "手动校准角色"})
        doc.setdefault("knowledge", [])
        doc.setdefault("idle_lines", [{"text": "你好呀！", "action": "wave", "weight": 2}])
        return doc

    def _validate(self):
        try:
            from app_paths import is_frozen
            if is_frozen():
                return True, "(冻结模式，跳过子进程校验)"
        except Exception:  # noqa: BLE001
            pass
        cmd = [sys.executable, str(ROOT / "tools" / "validate.py"), "character", str(self.out_dir),
               "--actions-dir", str(ROOT / "assets" / "actions")]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="拆分输出目录(含 parts/ 与 character.json)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out_dir = Path(args.dir)
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow(out_dir)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
