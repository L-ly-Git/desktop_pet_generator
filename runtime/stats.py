# -*- coding: utf-8 -*-
"""运行时性能采样：FPS、帧时间、CPU、工作集内存。"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from PyQt5.QtCore import QTimer

try:
    import win32api
    import win32process
except ImportError:  # pragma: no cover - 非 Windows / 缺少 pywin32
    win32api = None
    win32process = None


@dataclass
class StatsSnapshot:
    time_s: float
    fps: float
    avg_frame_ms: float
    p95_frame_ms: float
    max_frame_ms: float
    cpu_percent: float
    rss_mb: float


@dataclass
class StatsSummary:
    duration_s: float
    samples: int
    avg_fps: float
    min_fps: float
    avg_frame_ms: float
    p95_frame_ms: float
    max_frame_ms: float
    avg_cpu_percent: float
    max_cpu_percent: float
    rss_start_mb: float
    rss_end_mb: float
    rss_peak_mb: float
    rss_growth_mb: float


class RuntimeMonitor:
    """给 DesktopPetWindow 附加性能采样，不修改渲染/动作逻辑。"""

    def __init__(self, window, interval_s: float = 1.0) -> None:
        self.window = window
        self.interval_s = max(0.2, float(interval_s))
        self.snapshots: list[StatsSnapshot] = []
        self._frame_intervals: list[float] = []
        self._last_frame: float | None = None
        self._last_sample: float | None = None
        self._last_cpu: float | None = None
        self._start_time: float | None = None
        self._rss_start = self._rss_mb()
        self._rss_peak = self._rss_start
        self._connected = False

        self._timer = QTimer(window)
        self._timer.setInterval(int(self.interval_s * 1000))
        self._timer.timeout.connect(self._sample)

    def start(self) -> None:
        now = time.perf_counter()
        self._start_time = now
        self._last_sample = now
        self._last_frame = None
        self._last_cpu = self._cpu_seconds()
        self._rss_start = self._rss_mb()
        self._rss_peak = self._rss_start
        self._frame_intervals.clear()
        self.snapshots.clear()
        if hasattr(self.window, "_timer") and not self._connected:
            self.window._timer.timeout.connect(self._on_frame)
            self._connected = True
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        if self._connected and hasattr(self.window, "_timer"):
            try:
                self.window._timer.timeout.disconnect(self._on_frame)
            except TypeError:
                pass
            self._connected = False

    def _on_frame(self) -> None:
        now = time.perf_counter()
        if self._last_frame is not None:
            self._frame_intervals.append(now - self._last_frame)
        self._last_frame = now

    def _sample(self) -> None:
        if self._start_time is None or self._last_sample is None:
            return
        now = time.perf_counter()
        elapsed = max(1e-9, now - self._last_sample)
        intervals = self._frame_intervals
        self._frame_intervals = []

        if intervals:
            avg_frame_ms = statistics.fmean(intervals) * 1000.0
            sorted_intervals = sorted(intervals)
            p95_index = min(
                len(sorted_intervals) - 1,
                max(0, int(len(sorted_intervals) * 0.95) - 1),
            )
            p95_frame_ms = sorted_intervals[p95_index] * 1000.0
            max_frame_ms = max(intervals) * 1000.0
            fps = len(intervals) / elapsed
        else:
            avg_frame_ms = p95_frame_ms = max_frame_ms = 0.0
            fps = 0.0

        cpu_now = self._cpu_seconds()
        cpu_percent = 0.0
        if (
            self._last_cpu is not None
            and cpu_now >= self._last_cpu
            and elapsed > 0
        ):
            cpu_percent = (cpu_now - self._last_cpu) / elapsed * 100.0
        self._last_cpu = cpu_now

        rss_mb = self._rss_mb()
        self._rss_peak = max(self._rss_peak, rss_mb)
        self.snapshots.append(
            StatsSnapshot(
                time_s=now - self._start_time,
                fps=fps,
                avg_frame_ms=avg_frame_ms,
                p95_frame_ms=p95_frame_ms,
                max_frame_ms=max_frame_ms,
                cpu_percent=cpu_percent,
                rss_mb=rss_mb,
            )
        )
        self._last_sample = now

    def summary(self) -> StatsSummary:
        if not self.snapshots:
            return StatsSummary(
                duration_s=0.0,
                samples=0,
                avg_fps=0.0,
                min_fps=0.0,
                avg_frame_ms=0.0,
                p95_frame_ms=0.0,
                max_frame_ms=0.0,
                avg_cpu_percent=0.0,
                max_cpu_percent=0.0,
                rss_start_mb=self._rss_start,
                rss_end_mb=self._rss_start,
                rss_peak_mb=self._rss_start,
                rss_growth_mb=0.0,
            )
        fps_values = [snapshot.fps for snapshot in self.snapshots]
        cpu_values = [snapshot.cpu_percent for snapshot in self.snapshots]
        rss_end = self.snapshots[-1].rss_mb
        return StatsSummary(
            duration_s=self.snapshots[-1].time_s,
            samples=len(self.snapshots),
            avg_fps=statistics.fmean(fps_values),
            min_fps=min(fps_values),
            avg_frame_ms=statistics.fmean(
                [snapshot.avg_frame_ms for snapshot in self.snapshots]
            ),
            p95_frame_ms=max(
                snapshot.p95_frame_ms for snapshot in self.snapshots
            ),
            max_frame_ms=max(
                snapshot.max_frame_ms for snapshot in self.snapshots
            ),
            avg_cpu_percent=statistics.fmean(cpu_values),
            max_cpu_percent=max(cpu_values),
            rss_start_mb=self._rss_start,
            rss_end_mb=rss_end,
            rss_peak_mb=self._rss_peak,
            rss_growth_mb=rss_end - self._rss_start,
        )

    @staticmethod
    def _cpu_seconds() -> float:
        if win32api is None or win32process is None:
            return 0.0
        try:
            handle = win32api.GetCurrentProcess()
            times = win32process.GetProcessTimes(handle)
            return (times["KernelTime"] + times["UserTime"]) / 10_000_000.0
        except Exception:
            return 0.0

    @staticmethod
    def _rss_mb() -> float:
        if win32api is None or win32process is None:
            return 0.0
        try:
            handle = win32api.GetCurrentProcess()
            info = win32process.GetProcessMemoryInfo(handle)
            return info["WorkingSetSize"] / (1024 * 1024)
        except Exception:
            return 0.0