# -*- coding: utf-8 -*-
"""待机台词调度：按权重随机选择 idle_lines。"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class IdleLine:
    text: str
    action: str
    weight: float


class IdleScheduler:
    """从角色的 idle_lines 中按权重抽取台词。"""

    def __init__(
        self,
        idle_lines: Iterable[Any],
        *,
        min_delay: float = 12.0,
        max_delay: float = 25.0,
        rng: random.Random | None = None,
    ) -> None:
        self._rng = rng or random.Random()
        self.min_delay = max(0.0, float(min_delay))
        self.max_delay = max(self.min_delay, float(max_delay))
        self.lines = self._parse_lines(idle_lines)
        self._last_text: str | None = None

    @staticmethod
    def _parse_lines(idle_lines: Iterable[Any]) -> list[IdleLine]:
        lines: list[IdleLine] = []
        if not isinstance(idle_lines, (list, tuple)):
            return lines
        for item in idle_lines:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            action = item.get("action")
            weight = item.get("weight", 1)
            if not isinstance(text, str) or not text.strip():
                continue
            if not isinstance(action, str) or not action.strip():
                continue
            if (
                not isinstance(weight, (int, float))
                or isinstance(weight, bool)
                or float(weight) <= 0
            ):
                continue
            lines.append(
                IdleLine(
                    text=text.strip(),
                    action=action.strip(),
                    weight=float(weight),
                )
            )
        return lines

    @property
    def has_lines(self) -> bool:
        return bool(self.lines)

    def pick_line(self) -> IdleLine | None:
        if not self.lines:
            return None
        weights = [line.weight for line in self.lines]
        chosen = self._rng.choices(self.lines, weights=weights, k=1)[0]
        if len(self.lines) > 1:
            for _ in range(2):
                if chosen.text != self._last_text:
                    break
                chosen = self._rng.choices(self.lines, weights=weights, k=1)[0]
        self._last_text = chosen.text
        return chosen

    def next_delay(self) -> float:
        return self._rng.uniform(self.min_delay, self.max_delay)