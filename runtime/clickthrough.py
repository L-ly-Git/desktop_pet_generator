# -*- coding: utf-8 -*-
"""Windows 鼠标点击穿透管理。

原理与根目录 main.py 一致：
    鼠标在角色上 -> 关闭 WS_EX_TRANSPARENT，窗口接收点击；
    鼠标在透明区域 -> 打开 WS_EX_TRANSPARENT，点击穿透到桌面。
"""
from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import QPoint, QTimer
from PyQt5.QtGui import QCursor

try:
    import win32api
    import win32con
    import win32gui
except ImportError:  # pragma: no cover - 非 Windows / 缺少 pywin32
    win32api = None
    win32con = None
    win32gui = None


class ClickThroughManager:
    def __init__(
        self,
        widget,
        hit_test: Callable[[QPoint], bool],
        interval_ms: int = 16,
    ) -> None:
        self.widget = widget
        self.hit_test = hit_test
        self.interval_ms = interval_ms
        self.hwnd: int | None = None
        self._click_through: bool | None = None
        self._suspended = False
        self.timer = QTimer(widget)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self.poll)

    @property
    def available(self) -> bool:
        return (
            win32api is not None
            and win32con is not None
            and win32gui is not None
        )

    def start(self) -> None:
        if not self.available:
            return
        self.hwnd = int(self.widget.winId())
        self._click_through = None
        self.poll()
        if not self.timer.isActive():
            self.timer.start()

    def stop(self) -> None:
        self.timer.stop()
        self.hwnd = None

    def set_suspended(self, suspended: bool) -> None:
        """拖动或菜单打开时临时关闭穿透。"""
        self._suspended = suspended
        if suspended:
            self._apply(False)
        else:
            self.poll()

    def poll(self) -> None:
        if not self.available or self.hwnd is None:
            return
        if self._suspended:
            self._apply(False)
            return
        if not self.widget.isVisible():
            return
        local = self.widget.mapFromGlobal(QCursor.pos())
        inside = self.widget.rect().contains(local)
        hit = inside and self.hit_test(local)
        self._apply(not hit)

    def _apply(self, enabled: bool) -> None:
        if not self.available or self.hwnd is None:
            return
        if enabled == self._click_through:
            return
        try:
            style = win32gui.GetWindowLong(
                self.hwnd, win32con.GWL_EXSTYLE
            )
            style |= win32con.WS_EX_LAYERED
            if enabled:
                style |= win32con.WS_EX_TRANSPARENT
            else:
                style &= ~win32con.WS_EX_TRANSPARENT
            win32api.SetWindowLong(
                self.hwnd, win32con.GWL_EXSTYLE, style
            )
            self._click_through = enabled
        except Exception:
            self.timer.stop()