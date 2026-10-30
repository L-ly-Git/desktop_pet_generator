# -*- coding: utf-8 -*-
"""动作加载、关键帧插值、缓动与播放状态。"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EASINGS = {"linear", "ease_in", "ease_out", "ease_in_out", "step"}
CHANNELS = {"tx", "ty", "rot", "sx", "sy"}
DEFAULT_EASING = "ease_in_out"


def apply_easing(name: str, t: float) -> float:
    """把 0..1 的线性进度转换为缓动进度。"""
    t = max(0.0, min(1.0, float(t)))
    if name == "ease_in":
        return t * t * t
    if name == "ease_out":
        return 1.0 - (1.0 - t) ** 3
    if name == "ease_in_out":
        return t * t * (3.0 - 2.0 * t)
    if name == "step":
        return 0.0
    return t


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


@dataclass(frozen=True)
class Keyframe:
    t: float
    v: float
    ease: str | None = None


@dataclass
class Action:
    id: str
    display_name: str
    duration: float
    loop: bool
    easing: str
    tracks: dict[str, dict[str, list[Keyframe]]]
    source: Path

    def sample(self, time: float) -> dict[str, dict[str, float]]:
        """在指定时间采样动作，返回 node -> channel -> value 的 pose。"""
        if self.loop and self.duration > 0:
            sample_time = float(time) % self.duration
        else:
            sample_time = max(0.0, min(float(time), self.duration))

        pose: dict[str, dict[str, float]] = {}
        for node, channels in self.tracks.items():
            node_pose: dict[str, float] = {}
            for channel, frames in channels.items():
                node_pose[channel] = self._sample_channel(frames, sample_time)
            pose[node] = node_pose
        return pose

    def _sample_channel(self, frames: list[Keyframe], time: float) -> float:
        if len(frames) == 1 or time <= frames[0].t:
            return frames[0].v
        if time >= frames[-1].t:
            return frames[-1].v
        for index in range(len(frames) - 1):
            start = frames[index]
            end = frames[index + 1]
            if start.t <= time <= end.t:
                span = end.t - start.t
                if span <= 0:
                    return end.v
                ratio = (time - start.t) / span
                ratio = apply_easing(start.ease or self.easing, ratio)
                return start.v + (end.v - start.v) * ratio
        return frames[-1].v


def _parse_keyframes(
    raw: Any,
    duration: float,
    *,
    action_id: str,
    node: str,
    channel: str,
    source: Path,
) -> list[Keyframe]:
    where = f"{source.name}:{action_id}.tracks.{node}.{channel}"
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{where} 必须是非空关键帧数组")
    frames: list[Keyframe] = []
    previous_t = -math.inf
    for index, item in enumerate(raw):
        fwhere = f"{where}[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{fwhere} 必须是对象")
        t = item.get("t")
        value = item.get("v")
        if not _is_number(t) or not _is_number(value):
            raise ValueError(f"{fwhere}.t/.v 必须是数字")
        t_value = float(t)
        v_value = float(value)
        if t_value < 0 or t_value > duration:
            raise ValueError(f"{fwhere}.t 超出 [0, {duration}]")
        if t_value <= previous_t:
            raise ValueError(f"{fwhere}.t 必须严格递增")
        if channel in ("sx", "sy") and v_value < 0:
            raise ValueError(f"{fwhere}.v 缩放不能为负数")
        ease = item.get("ease")
        if ease is not None and ease not in EASINGS:
            raise ValueError(f"{fwhere}.ease 不在允许列表: {ease!r}")
        frames.append(Keyframe(t_value, v_value, ease))
        previous_t = t_value
    return frames


def _parse_action(data: Any, source: Path) -> Action:
    if not isinstance(data, dict):
        raise ValueError(f"动作 {source.name}: 顶层必须是对象")
    action_id = data.get("id")
    if not isinstance(action_id, str) or not action_id:
        raise ValueError(f"动作 {source.name}: id 必须是非空字符串")
    duration = data.get("duration")
    if not _is_number(duration) or float(duration) <= 0:
        raise ValueError(f"动作 {source.name}: duration 必须大于 0")
    duration = float(duration)
    loop = data.get("loop")
    if not isinstance(loop, bool):
        raise ValueError(f"动作 {source.name}: loop 必须是布尔值")
    easing = data.get("easing", DEFAULT_EASING)
    if easing not in EASINGS:
        raise ValueError(f"动作 {source.name}: easing 不在允许列表: {easing!r}")
    display_name = data.get("display_name") or action_id
    tracks_raw = data.get("tracks")
    if not isinstance(tracks_raw, dict) or not tracks_raw:
        raise ValueError(f"动作 {source.name}: tracks 必须是非空对象")

    tracks: dict[str, dict[str, list[Keyframe]]] = {}
    for node, track_raw in tracks_raw.items():
        if not isinstance(node, str) or not node:
            raise ValueError(f"动作 {source.name}: tracks 的键必须是非空字符串")
        if not isinstance(track_raw, dict) or not track_raw:
            raise ValueError(f"动作 {source.name}: tracks.{node} 必须是非空对象")
        channels: dict[str, list[Keyframe]] = {}
        for channel, frames_raw in track_raw.items():
            if channel not in CHANNELS:
                raise ValueError(f"动作 {source.name}: 未知通道 {channel!r}")
            channels[channel] = _parse_keyframes(
                frames_raw,
                duration,
                action_id=action_id,
                node=node,
                channel=channel,
                source=source,
            )
        tracks[node] = channels
    return Action(
        id=action_id,
        display_name=str(display_name),
        duration=duration,
        loop=loop,
        easing=str(easing),
        tracks=tracks,
        source=source,
    )


@dataclass
class ActionLibrary:
    actions: dict[str, Action]

    @classmethod
    def load(cls, actions_dir: Path) -> "ActionLibrary":
        if not actions_dir.is_dir():
            raise FileNotFoundError(f"动作目录不存在: {actions_dir}")
        actions: dict[str, Action] = {}
        for path in sorted(actions_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            action = _parse_action(data, path)
            if action.id in actions:
                raise ValueError(f"动作 id 重复: {action.id!r}")
            actions[action.id] = action
        if not actions:
            raise ValueError(f"动作目录为空: {actions_dir}")
        return cls(actions=actions)

    def get(self, action_id: str) -> Action | None:
        return self.actions.get(action_id)

    def items(self) -> list[Action]:
        return sorted(self.actions.values(), key=lambda action: action.id)

    @property
    def default_idle_id(self) -> str | None:
        if "idle_breath" in self.actions:
            return "idle_breath"
        for action in self.items():
            if action.loop:
                return action.id
        return next(iter(self.actions), None)


@dataclass
class ActionPlayer:
    action: Action
    time: float = 0.0
    playing: bool = True
    finished: bool = False

    def play(self, action: Action) -> None:
        self.action = action
        self.time = 0.0
        self.playing = True
        self.finished = False

    def stop(self) -> None:
        self.playing = False

    def update(self, dt: float) -> bool:
        """推进时间；非循环动作刚结束时返回 True。"""
        if not self.playing:
            return False
        self.time += max(0.0, float(dt))
        if self.action.loop:
            self.time %= self.action.duration
            return False
        if self.time >= self.action.duration:
            self.time = self.action.duration
            self.playing = False
            self.finished = True
            return True
        return False

    @property
    def pose(self) -> dict[str, dict[str, float]]:
        return self.action.sample(self.time)