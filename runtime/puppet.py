# -*- coding: utf-8 -*-
"""PyQt5 cut-out 渲染与透明桌宠窗口。"""
from __future__ import annotations

import time
from typing import Mapping

from PyQt5.QtCore import QPoint, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QImage, QPainter, QPen, QTransform
from PyQt5.QtWidgets import QApplication, QMenu, QWidget

from .action import ActionLibrary, ActionPlayer
from .contract import Character, build_node_graph
from .transform import Affine, Pose, compute_global_transforms, scale_around


def render_parts(
    painter: QPainter,
    character: Character,
    pose: Pose | None = None,
    debug_pivots: bool = False,
    display_scale: float = 1.0,
) -> None:
    """按契约 z 顺序绘制所有部件，并应用父子层级变换。"""
    parents, pivots = build_node_graph(character)
    transforms = compute_global_transforms(parents, pivots, pose)
    display_transform = scale_around(character.anchor, display_scale)

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    for part in character.parts_by_z:
        transform = display_transform.multiply(transforms[part.name])
        painter.save()
        painter.setTransform(transform.to_qtransform())
        painter.drawPixmap(0, 0, character.pixmaps[part.name])
        painter.restore()

    if debug_pivots:
        painter.setTransform(QTransform())
        _draw_pivots(painter, character, transforms, display_transform)
    painter.restore()


def _draw_pivots(
    painter: QPainter,
    character: Character,
    transforms: Mapping[str, Affine],
    display_transform: Affine,
) -> None:
    marker_pen = QPen(QColor(255, 72, 72, 235), 2)
    root_pen = QPen(QColor(255, 210, 70, 235), 2)
    text_pen = QPen(QColor(255, 255, 255, 240))
    painter.setFont(QFont("Microsoft YaHei", 8))

    for name, part in character.parts.items():
        x, y = display_transform.multiply(transforms[name]).map_point(*part.pivot)
        painter.setPen(marker_pen)
        painter.drawLine(int(x - 7), int(y), int(x + 7), int(y))
        painter.drawLine(int(x), int(y - 7), int(x), int(y + 7))
        painter.drawEllipse(QPoint(int(x), int(y)), 4, 4)
        painter.setPen(text_pen)
        painter.drawText(int(x + 9), int(y - 9), name)

    x, y = display_transform.multiply(transforms["root"]).map_point(*character.anchor)
    painter.setPen(root_pen)
    painter.drawLine(int(x - 9), int(y), int(x + 9), int(y))
    painter.drawLine(int(x), int(y - 9), int(x), int(y + 9))
    painter.drawEllipse(QPoint(int(x), int(y)), 5, 5)
    painter.setPen(text_pen)
    painter.drawText(int(x + 11), int(y - 11), "root")


def render_to_image(
    character: Character,
    pose: Pose | None = None,
    debug_pivots: bool = False,
    display_scale: float = 1.0,
) -> QImage:
    image = QImage(
        character.canvas_width,
        character.canvas_height,
        QImage.Format_ARGB32_Premultiplied,
    )
    image.fill(Qt.transparent)
    painter = QPainter(image)
    try:
        render_parts(painter, character, pose, debug_pivots, display_scale)
    finally:
        painter.end()
    return image


def checkerboard_image(image: QImage, cell: int = 32) -> QImage:
    """给透明快照加棋盘格背景，便于人工检查。"""
    result = QImage(image.size(), QImage.Format_ARGB32_Premultiplied)
    painter = QPainter(result)
    try:
        painter.fillRect(result.rect(), QColor(34, 38, 46))
        for y in range(0, result.height(), cell):
            for x in range(0, result.width(), cell):
                if (x // cell + y // cell) % 2 == 0:
                    painter.fillRect(x, y, cell, cell, QColor(44, 49, 59))
        painter.drawImage(0, 0, image)
    finally:
        painter.end()
    return result


class PetWindow(QWidget):
    """512x512 透明、无边框、置顶的桌宠窗口。"""

    def __init__(
        self,
        character: Character,
        pose: Pose | None = None,
        debug_pivots: bool = False,
        display_scale: float = 1.0,
        action_library: ActionLibrary | None = None,
        initial_action_id: str | None = None,
        start_animation: bool = True,
    ) -> None:
        super().__init__()
        self.character = character
        self.static_pose = dict(pose or {})
        self.debug_pivots = debug_pivots
        self.display_scale = display_scale
        self.action_library = action_library
        self.player: ActionPlayer | None = None
        self.current_action_id: str | None = None
        self.idle_action_id = (
            action_library.default_idle_id if action_library is not None else None
        )
        self._last_tick = time.perf_counter()
        self._drag_offset: QPoint | None = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFixedSize(character.canvas_width, character.canvas_height)
        self.setWindowTitle(f"Window Pet - {character.name}")

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

        if action_library is not None and start_animation:
            target = initial_action_id or self.idle_action_id
            if target:
                self.play_action(target)

    @property
    def current_pose(self) -> Pose:
        if self.player is not None:
            return self.player.pose
        return self.static_pose

    def play_action(self, action_id: str) -> bool:
        if self.action_library is None:
            return False
        action = self.action_library.get(action_id)
        if action is None:
            return False
        self.static_pose = {}
        if self.player is None:
            self.player = ActionPlayer(action)
        else:
            self.player.play(action)
        self.current_action_id = action_id
        self._last_tick = time.perf_counter()
        if not self._timer.isActive():
            self._timer.start()
        self.update()
        return True

    def _tick(self) -> None:
        now = time.perf_counter()
        dt = now - self._last_tick
        self._last_tick = now
        if self.player is None:
            return
        finished = self.player.update(dt)
        if finished:
            if self.idle_action_id and self.idle_action_id != self.current_action_id:
                self.play_action(self.idle_action_id)
            else:
                self.player.stop()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            render_parts(
                painter,
                self.character,
                self.current_pose,
                self.debug_pivots,
                self.display_scale,
            )
        finally:
            painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_offset = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        action_menu = menu.addMenu("播放动作")

        if self.action_library is not None:
            if self.idle_action_id:
                idle_item = action_menu.addAction("回到待机")
                idle_item.setCheckable(True)
                idle_item.setChecked(self.current_action_id == self.idle_action_id)
                idle_item.triggered.connect(
                    lambda checked=False: self.play_action(self.idle_action_id)
                )
                action_menu.addSeparator()

            for action in self.action_library.items():
                label = (
                    f"{action.display_name} ({action.id})"
                    if action.display_name != action.id
                    else action.id
                )
                item = action_menu.addAction(label)
                item.setCheckable(True)
                item.setChecked(self.current_action_id == action.id)
                item.triggered.connect(
                    lambda checked=False, action_id=action.id: self.play_action(action_id)
                )
        else:
            empty_item = action_menu.addAction("无可用动作")
            empty_item.setEnabled(False)

        menu.addSeparator()
        toggle_action = menu.addAction(
            "隐藏枢轴" if self.debug_pivots else "显示枢轴"
        )
        chat_action = menu.addAction("聊天")
        clear_history_action = menu.addAction("清空记忆")
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        chosen = menu.exec_(event.globalPos())

        if chosen == toggle_action:
            self.debug_pivots = not self.debug_pivots
            self.update()
        elif chosen == chat_action:
            self.on_chat()
        elif chosen == clear_history_action:
            self.on_clear_history()
        elif chosen == quit_action:
            QApplication.instance().quit()

    def on_chat(self) -> None:
        """打开聊天输入（子类可覆盖）。"""

    def on_clear_history(self) -> None:
        """清空对话记忆（子类可覆盖）。"""

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            QApplication.instance().quit()
            return
        if event.key() == Qt.Key_P:
            self.debug_pivots = not self.debug_pivots
            self.update()
            return
        if (
            self.action_library is not None
            and Qt.Key_1 <= event.key() <= Qt.Key_9
        ):
            index = event.key() - Qt.Key_1
            actions = self.action_library.items()
            if index < len(actions):
                self.play_action(actions[index].id)
                return
        super().keyPressEvent(event)


def position_window(
    window: PetWindow,
    margin_right: int = 40,
    margin_bottom: int = 20,
) -> None:
    screen = QApplication.primaryScreen()
    if screen is None:
        return
    geometry = screen.availableGeometry()
    x = geometry.right() - window.width() + 1 - margin_right
    y = geometry.bottom() - window.height() + 1 - margin_bottom
    window.move(max(geometry.left(), x), max(geometry.top(), y))