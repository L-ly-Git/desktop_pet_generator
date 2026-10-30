# -*- coding: utf-8 -*-
"""1-D 桌面交互窗口：气泡、待机调度、点击穿透、拖拽、点击互动、行走。"""
from __future__ import annotations

import math
import random
import time
from typing import Mapping

from PIL import Image
from PyQt5.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor, QFont, QImage, QPainter
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLineEdit, QWidget

from .action import ActionLibrary
from .chat import AIClient, load_config as load_chat_config
from .bubble import bubble_max_width, draw_speech_bubble
from .clickthrough import ClickThroughManager
from .contract import Character, build_node_graph
from .idle import IdleScheduler
from .puppet import PetWindow, render_parts
from .transform import Affine, Pose, compute_global_transforms, scale_around

try:
    import win32api
    import win32con
except ImportError:  # pragma: no cover - 非 Windows / 缺少 pywin32
    win32api = None
    win32con = None

WALK_SPEED = 160.0
WALK_STOP_DISTANCE = 3.0
MIDDLE_POLL_MS = 30
CLICK_DRAG_THRESHOLD = 4


def load_part_bboxes(
    character: Character,
) -> dict[str, tuple[int, int, int, int]]:
    """读取每个部件 PNG 的可见 alpha 包围盒，用于气泡定位与命中测试。"""
    bboxes: dict[str, tuple[int, int, int, int]] = {}
    for name, part in character.parts.items():
        try:
            with Image.open(part.file) as image:
                bbox = image.convert("RGBA").getchannel("A").getbbox()
        except (OSError, ValueError):
            bbox = None
        if bbox is None:
            bbox = (0, 0, character.canvas_width, character.canvas_height)
        bboxes[name] = tuple(int(value) for value in bbox)
    return bboxes


def _mapped_rect(
    transform: Affine,
    source_bbox: tuple[int, int, int, int],
) -> QRect:
    x0, y0, x1, y1 = source_bbox
    points = [
        transform.map_point(x0, y0),
        transform.map_point(x1, y0),
        transform.map_point(x0, y1),
        transform.map_point(x1, y1),
    ]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    left = int(math.floor(min(xs)))
    top = int(math.floor(min(ys)))
    right = int(math.ceil(max(xs)))
    bottom = int(math.ceil(max(ys)))
    return QRect(left, top, max(1, right - left), max(1, bottom - top))


def part_visible_rect(
    character: Character,
    node: str,
    pose: Pose | None,
    display_scale: float,
    part_bboxes: Mapping[str, tuple[int, int, int, int]],
) -> QRect:
    if node not in character.parts:
        return QRect()
    parents, pivots = build_node_graph(character)
    transforms = compute_global_transforms(parents, pivots, pose)
    display = scale_around(character.anchor, display_scale)
    source = part_bboxes.get(
        node, (0, 0, character.canvas_width, character.canvas_height)
    )
    return _mapped_rect(display.multiply(transforms[node]), source)


def character_visible_rect(
    character: Character,
    pose: Pose | None,
    display_scale: float,
    part_bboxes: Mapping[str, tuple[int, int, int, int]],
) -> QRect:
    parents, pivots = build_node_graph(character)
    transforms = compute_global_transforms(parents, pivots, pose)
    display = scale_around(character.anchor, display_scale)
    union: QRect | None = None
    for name in character.parts:
        source = part_bboxes.get(name)
        if source is None:
            continue
        rect = _mapped_rect(display.multiply(transforms[name]), source)
        union = rect if union is None else union.united(rect)
    return union if union is not None else QRect(0, 0, 1, 1)


def bubble_lifetime(text: str) -> float:
    return min(9.5, 4.0 + max(0, len(text.strip()) - 15) * 0.2)


def render_desktop_image(
    character: Character,
    pose: Pose | None = None,
    display_scale: float = 1.0,
    bubble_text: str | None = None,
    debug_pivots: bool = False,
) -> QImage:
    """把角色和可选气泡渲染为透明 QImage（用于快照预览）。"""
    image = QImage(
        character.canvas_width,
        character.canvas_height,
        QImage.Format_ARGB32_Premultiplied,
    )
    image.fill(Qt.transparent)
    painter = QPainter(image)
    try:
        render_parts(painter, character, pose, debug_pivots, display_scale)
        if bubble_text:
            part_bboxes = load_part_bboxes(character)
            character_rect = character_visible_rect(
                character, pose, display_scale, part_bboxes
            )
            draw_speech_bubble(
                painter,
                bubble_text,
                character_rect,
                QRect(0, 0, character.canvas_width, character.canvas_height),
                max_width=bubble_max_width(character_rect),
            )
    finally:
        painter.end()
    return image
class ChatInputWindow(QWidget):
    """常驻对话输入框：无边框小窗口，Enter 发送，Esc 关闭。"""

    submitted = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(
            "QLineEdit { background: rgba(255,255,255,0.96); border: 1.5px solid #8ab4f8; "
            "border-radius: 9px; padding: 4px 8px; font-size: 12px; color: #333333; "
            "selection-background-color: #cce0ff; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("说点什么… (Enter 发送 / Esc 关闭)")
        self.edit.returnPressed.connect(self._submit)
        layout.addWidget(self.edit)
        self.resize(240, 32)

    def _submit(self) -> None:
        text = self.edit.text().strip()
        if text:
            self.submitted.emit(text)
            self.edit.clear()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def show_input(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()


class DesktopPetWindow(PetWindow):
    """在 PetWindow 基础上增加 1-D 交互能力。"""

    def __init__(
        self,
        character: Character,
        pose: Pose | None = None,
        debug_pivots: bool = False,
        display_scale: float = 1.0,
        action_library: ActionLibrary | None = None,
        initial_action_id: str | None = None,
        start_animation: bool = True,
        enable_idle: bool = True,
        enable_click_through: bool = True,
        idle_min: float = 12.0,
        idle_max: float = 25.0,
        idle_rng: random.Random | None = None,
        history_path: Path | None = None,
        memory_path: Path | None = None,
    ) -> None:
        super().__init__(
            character,
            pose=pose,
            debug_pivots=debug_pivots,
            display_scale=display_scale,
            action_library=action_library,
            initial_action_id=initial_action_id,
            start_animation=start_animation,
        )
        self._part_bboxes = load_part_bboxes(character)
        self._cropped_pixmaps = self._build_cropped_pixmaps(character)
        self._bubble_text: str | None = None
        self._bubble_visible = False
        self._bubble_font = QFont("Microsoft YaHei", 10)
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self.clear_bubble)

        self._idle_enabled = enable_idle
        self._idle_scheduler = IdleScheduler(
            character.idle_lines,
            min_delay=idle_min,
            max_delay=idle_max,
            rng=idle_rng,
        )
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_timeout)

        self._click_through = (
            ClickThroughManager(self, self.is_over_character)
            if enable_click_through
            else None
        )
        self._left_down = False
        self._dragging = False
        self._press_global: QPoint | None = None
        self._menu_open = False
        self._timers_started = False

        self._walk_target: QPoint | None = None
        self._last_walk_tick = time.perf_counter()
        self._middle_down = False
        self._middle_timer = QTimer(self)
        self._middle_timer.setInterval(MIDDLE_POLL_MS)
        self._middle_timer.timeout.connect(self._poll_middle_button)
        self._walk_action_available = bool(
            action_library is not None
            and action_library.get("walk") is not None
        )
        self._ai_client = AIClient(
            load_chat_config(), character.persona, character.knowledge,
            history_path=history_path, memory_path=memory_path,
        )
        self._ai_client.reply_ready.connect(self._on_ai_reply)
        self._ai_client.reply_failed.connect(self._on_ai_fail)
        self._chat_input = ChatInputWindow()
        self._chat_input.submitted.connect(self._on_chat_submit)

    def on_chat(self) -> None:
        self.toggle_chat_input()

    def toggle_chat_input(self) -> None:
        if self._chat_input.isVisible():
            self._chat_input.hide()
        else:
            rect = self.character_rect()
            global_pos = self.mapToGlobal(QPoint(rect.center().x(), rect.bottom()))
            screen = QApplication.primaryScreen().availableGeometry()
            x = global_pos.x() - self._chat_input.width() // 2
            x = max(screen.left(), min(screen.right() - self._chat_input.width(), x))
            y = global_pos.y() + 6  # 角色下方 6px
            y = min(screen.bottom() - self._chat_input.height() - 4, y)
            self._chat_input.move(x, max(screen.top(), y))
            self._chat_input.show_input()

    def _on_chat_submit(self, text: str) -> None:
        self.show_bubble("……")
        self._ai_client.ask(text)

    def on_clear_history(self) -> None:
        self._ai_client.clear_history()
        self.show_bubble("记忆已清空~")

    def _on_ai_reply(self, text: str, action: str) -> None:
        self.show_bubble(text)
        if action and self.action_library is not None and self.action_library.get(action) is not None:
            self.play_action(action)

    def _on_ai_fail(self, text: str) -> None:
        self.show_bubble(text)

    @property
    def bubble_text(self) -> str | None:
        return self._bubble_text if self._bubble_visible else None

    def character_rect(self) -> QRect:
        return character_visible_rect(
            self.character,
            self.current_pose,
            self.display_scale,
            self._part_bboxes,
        )

    def is_over_character(self, point: QPoint) -> bool:
        return self.character_rect().adjusted(-10, -10, 10, 10).contains(point)

    def _build_cropped_pixmaps(self, character: Character) -> dict:
        cropped = {}
        for name in character.parts:
            bbox = self._part_bboxes.get(name)
            if bbox is None:
                bbox = (0, 0, character.canvas_width, character.canvas_height)
            x0, y0, x1, y1 = bbox
            width = max(1, x1 - x0)
            height = max(1, y1 - y0)
            cropped[name] = (
                character.pixmaps[name].copy(QRect(x0, y0, width, height)),
                x0,
                y0,
            )
        return cropped

    def _render_parts_fast(self, painter: QPainter) -> None:
        parents, pivots = build_node_graph(self.character)
        transforms = compute_global_transforms(
            parents, pivots, self.current_pose
        )
        display = scale_around(self.character.anchor, self.display_scale)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        for part in self.character.parts_by_z:
            pixmap, offset_x, offset_y = self._cropped_pixmaps[part.name]
            transform = (
                display.multiply(transforms[part.name])
                .multiply(Affine.translate(offset_x, offset_y))
            )
            painter.save()
            painter.setTransform(transform.to_qtransform())
            painter.drawPixmap(0, 0, pixmap)
            painter.restore()
        painter.restore()

    def show_bubble(self, text: str, lifetime: float | None = None) -> None:
        text = (text or "").strip()
        if not text:
            self.clear_bubble()
            return
        self._bubble_text = text
        self._bubble_visible = True
        duration = lifetime if lifetime is not None else bubble_lifetime(text)
        self._bubble_timer.start(max(500, int(duration * 1000)))
        self.update()

    def clear_bubble(self) -> None:
        self._bubble_timer.stop()
        self._bubble_text = None
        self._bubble_visible = False
        self.update()

    def trigger_idle_line(self) -> bool:
        line = self._idle_scheduler.pick_line()
        if line is None:
            return False
        action = (
            self.action_library.get(line.action)
            if self.action_library is not None
            else None
        )
        if action is not None:
            self.play_action(line.action)
        self.show_bubble(line.text)
        return True

    def _schedule_next_idle(self) -> None:
        if not self._idle_enabled or not self._idle_scheduler.has_lines:
            return
        delay = max(0.1, self._idle_scheduler.next_delay())
        self._idle_timer.start(int(delay * 1000))

    def _on_idle_timeout(self) -> None:
        if not self._idle_enabled:
            return
        if self._walk_target is not None:
            self._idle_timer.start(1000)
            return
        if self._bubble_visible:
            self._idle_timer.start(1000)
            return
        if (
            self.player is not None
            and self.player.playing
            and self.current_action_id != self.idle_action_id
        ):
            self._idle_timer.start(1000)
            return
        self.trigger_idle_line()
        self._schedule_next_idle()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._timers_started:
            return
        self._timers_started = True
        if self._click_through is not None:
            self._click_through.start()
        self._middle_timer.start()
        self._schedule_next_idle()

    def closeEvent(self, event) -> None:
        self._idle_timer.stop()
        self._bubble_timer.stop()
        self._middle_timer.stop()
        if self._click_through is not None:
            self._click_through.stop()
        if self._timer.isActive():
            self._timer.stop()
        super().closeEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            if self.debug_pivots:
                render_parts(
                    painter,
                    self.character,
                    self.current_pose,
                    True,
                    self.display_scale,
                )
            else:
                self._render_parts_fast(painter)
            if self._bubble_visible and self._bubble_text:
                character_rect = self.character_rect()
                draw_speech_bubble(
                    painter,
                    self._bubble_text,
                    character_rect,
                    self.rect(),
                    self._bubble_font,
                    max_width=bubble_max_width(character_rect),
                )
        finally:
            painter.end()
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.RightButton:
            self._chat_input.hide()
        if event.button() == Qt.LeftButton:
            self._left_down = True
            self._press_global = event.globalPos()
            self._dragging = False
            self._cancel_walk()
            if self._click_through is not None:
                self._click_through.set_suspended(True)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._left_down and self._press_global is not None:
            delta = event.globalPos() - self._press_global
            if (
                not self._dragging
                and delta.manhattanLength() >= CLICK_DRAG_THRESHOLD
            ):
                self._dragging = True
                self.clear_bubble()
            if self._dragging:
                super().mouseMoveEvent(event)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            was_dragging = self._dragging
            self._left_down = False
            self._dragging = False
            self._press_global = None
            if self._click_through is not None:
                self._click_through.set_suspended(False)
            super().mouseReleaseEvent(event)
            if not was_dragging:
                self.trigger_idle_line()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.toggle_chat_input()
            event.accept()
            return
        self._chat_input.hide()
        before_action = self.current_action_id
        self._menu_open = True
        if self._click_through is not None:
            self._click_through.set_suspended(True)
        try:
            super().contextMenuEvent(event)
        finally:
            self._menu_open = False
            if self._click_through is not None:
                self._click_through.set_suspended(False)
            if self.current_action_id != before_action:
                self.clear_bubble()

    def _cancel_walk(self) -> None:
        if self._walk_target is None:
            return
        self._walk_target = None
        if (
            self.action_library is not None
            and self.current_action_id == "walk"
            and self.idle_action_id
        ):
            self.play_action(self.idle_action_id)

    def _poll_middle_button(self) -> None:
        if win32api is None or win32con is None:
            return
        try:
            down = bool(
                win32api.GetAsyncKeyState(win32con.VK_MBUTTON) & 0x8000
            )
        except Exception:
            self._middle_timer.stop()
            return
        if down and not self._middle_down:
            if not self._left_down and not self._dragging:
                cursor = QCursor.pos()
                self.walk_to(cursor.x(), cursor.y())
        self._middle_down = down

    def walk_to(self, screen_x: int, screen_y: int) -> None:
        """把角色可见中心移动到屏幕坐标 (screen_x, screen_y)。"""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        character_rect = self.character_rect()
        if character_rect.isNull():
            return
        half_w = character_rect.width() / 2.0
        half_h = character_rect.height() / 2.0
        cx = max(
            geometry.left() + half_w,
            min(geometry.right() - half_w, float(screen_x)),
        )
        cy = max(
            geometry.top() + half_h,
            min(geometry.bottom() - half_h, float(screen_y)),
        )
        target_x = cx - character_rect.center().x()
        target_y = cy - character_rect.center().y()
        self._walk_target = QPoint(
            int(round(target_x)), int(round(target_y))
        )
        self._last_walk_tick = time.perf_counter()
        self.clear_bubble()
        if not self._timer.isActive():
            self._last_tick = time.perf_counter()
            self._timer.start()
        if self._walk_action_available:
            self.play_action("walk")

    def _walk_step(self) -> None:
        if self._walk_target is None:
            return
        now = time.perf_counter()
        dt = max(0.0, now - self._last_walk_tick)
        self._last_walk_tick = now
        current = self.pos()
        target = self._walk_target
        dx = target.x() - current.x()
        dy = target.y() - current.y()
        distance = math.hypot(dx, dy)
        if distance <= WALK_STOP_DISTANCE:
            self.move(target)
            self._walk_target = None
            if self.idle_action_id:
                self.play_action(self.idle_action_id)
            return
        step = min(distance, WALK_SPEED * dt)
        if step <= 0:
            return
        nx = current.x() + dx / distance * step
        ny = current.y() + dy / distance * step
        self.move(int(round(nx)), int(round(ny)))

    def _tick(self) -> None:
        super()._tick()
        self._walk_step()