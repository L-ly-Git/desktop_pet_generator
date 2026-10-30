# -*- coding: utf-8 -*-
"""桌宠气泡绘制：贴在角色右上角，放不下时自动翻到左上角。"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPolygon,
)

BUBBLE_BG = QColor(248, 252, 255, 245)
BUBBLE_BORDER = QColor(149, 199, 236, 240)
BUBBLE_TEXT = QColor(53, 80, 107, 255)
BUBBLE_SHADOW = QColor(0, 0, 0, 40)
BUBBLE_RADIUS = 12
BUBBLE_PADDING = 7
BUBBLE_MIN_WIDTH = 52
BUBBLE_MIN_HEIGHT = 30
BUBBLE_MAX_WIDTH = 150
BUBBLE_OVERLAP_X = 12
BUBBLE_OVERLAP_Y = 10
TAIL_BASE = 24
TAIL_DEEP = 10


@dataclass
class BubbleLayout:
    bubble_rect: QRect
    text_rect: QRect
    tail: QPolygon
    tail_left: bool



def bubble_max_width(character_rect: QRect) -> int:
    return max(96, min(BUBBLE_MAX_WIDTH, int(round(character_rect.width() * 1.7))))

def layout_bubble(
    text: str,
    character_rect: QRect,
    bounds: QRect,
    font: QFont,
    max_width: int = BUBBLE_MAX_WIDTH,
) -> BubbleLayout:
    metrics = QFontMetrics(font)
    max_text_width = max(40, max_width - BUBBLE_PADDING * 2)
    measured = metrics.boundingRect(
        QRect(0, 0, max_text_width, 1000),
        Qt.TextWordWrap | Qt.AlignLeft,
        text,
    )
    text_width = max(
        BUBBLE_MIN_WIDTH - BUBBLE_PADDING * 2,
        min(max_text_width, measured.width()),
    )
    text_height = max(metrics.height(), measured.height())
    bubble_width = max(
        BUBBLE_MIN_WIDTH,
        min(max_width, text_width + BUBBLE_PADDING * 2),
    )
    bubble_height = max(
        BUBBLE_MIN_HEIGHT,
        text_height + BUBBLE_PADDING * 2,
    )

    # 参考 main.py 的 place_bubble：默认贴角色右上角，右边放不下就翻到左上角。
    tail_left = True
    x = character_rect.right() - BUBBLE_OVERLAP_X
    if x + bubble_width > bounds.right() - 4:
        tail_left = False
        x = character_rect.left() - bubble_width + BUBBLE_OVERLAP_X
    x = max(bounds.left() + 4, min(bounds.right() - bubble_width - 3, x))

    bottom = character_rect.top() + BUBBLE_OVERLAP_Y
    y = bottom - bubble_height
    y = max(bounds.top() + 4, min(bounds.bottom() - bubble_height - 3, y))

    bubble_rect = QRect(int(x), int(y), int(bubble_width), int(bubble_height))
    text_rect = bubble_rect.adjusted(
        BUBBLE_PADDING,
        BUBBLE_PADDING,
        -BUBBLE_PADDING,
        -BUBBLE_PADDING,
    )

    tail_y = bubble_rect.bottom()
    if tail_left:
        x1 = bubble_rect.left() + 14
        x2 = x1 + TAIL_BASE
        tip_x = bubble_rect.left() + 4
    else:
        x2 = bubble_rect.right() - 14
        x1 = x2 - TAIL_BASE
        tip_x = bubble_rect.right() - 4
    tail = QPolygon(
        [
            QPoint(x1, tail_y),
            QPoint(x2, tail_y),
            QPoint(tip_x, tail_y + TAIL_DEEP),
        ]
    )
    return BubbleLayout(bubble_rect, text_rect, tail, tail_left)


def draw_speech_bubble(
    painter: QPainter,
    text: str,
    character_rect: QRect,
    bounds: QRect,
    font: QFont | None = None,
    max_width: int = BUBBLE_MAX_WIDTH,
) -> BubbleLayout:
    font = font or QFont("Microsoft YaHei", 10)
    layout = layout_bubble(text, character_rect, bounds, font, max_width)

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)

    shadow_rect = layout.bubble_rect.translated(1, 2)
    painter.setPen(Qt.NoPen)
    painter.setBrush(BUBBLE_SHADOW)
    painter.drawRoundedRect(shadow_rect, BUBBLE_RADIUS, BUBBLE_RADIUS)

    painter.setPen(QPen(BUBBLE_BORDER, 2))
    painter.setBrush(BUBBLE_BG)
    painter.drawRoundedRect(layout.bubble_rect, BUBBLE_RADIUS, BUBBLE_RADIUS)

    p0 = layout.tail.at(0)
    p1 = layout.tail.at(1)
    p2 = layout.tail.at(2)
    tail_path = QPainterPath()
    tail_path.moveTo(p0.x(), p0.y())
    tail_path.lineTo(p1.x(), p1.y())
    tail_path.lineTo(p2.x(), p2.y())
    tail_path.closeSubpath()
    painter.setPen(QPen(BUBBLE_BORDER, 2))
    painter.setBrush(BUBBLE_BG)
    painter.drawPath(tail_path)

    painter.setPen(BUBBLE_TEXT)
    painter.setFont(font)
    painter.drawText(
        layout.text_rect,
        Qt.TextWordWrap | Qt.AlignCenter,
        text,
    )
    painter.restore()
    return layout