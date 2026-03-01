"""Performance measurement helpers for deterministic profiling.

These helpers avoid changing business logic paths and only observe timings and
resource usage. They are intentionally lightweight so they can be used in tests,
benchmarks, and production instrumentation without introducing side effects.
"""

from __future__ import annotations

import functools
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, TypeVar

from media_manager.app.core.logging_config import get_logger

try:
    import psutil
except Exception:  # pragma: no cover - optional dependency fallback
    psutil = None  # type: ignore[assignment]

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class PerformanceSnapshot:
    """A single point-in-time process resource snapshot."""

    wall_time_s: float
    cpu_user_s: float | None
    cpu_system_s: float | None
    rss_bytes: int | None
    io_read_bytes: int | None
    io_write_bytes: int | None


@dataclass(frozen=True)
class PerformanceResult:
    """Delta between two snapshots suitable for logs and benchmark output."""

    label: str
    wall_time_s: float
    cpu_user_s: float | None
    cpu_system_s: float | None
    rss_bytes: int | None
    io_read_bytes: int | None
    io_write_bytes: int | None

    def to_dict(self) -> dict[str, float | int | str | None]:
        return {
            "label": self.label,
            "wall_time_s": self.wall_time_s,
            "cpu_user_s": self.cpu_user_s,
            "cpu_system_s": self.cpu_system_s,
            "rss_bytes": self.rss_bytes,
            "io_read_bytes": self.io_read_bytes,
            "io_write_bytes": self.io_write_bytes,
        }


def _snapshot() -> PerformanceSnapshot:
    """Capture process resources.

    When psutil is not available we still report deterministic wall-time fields,
    and leave process-specific metrics as None.
    """

    now = perf_counter()
    if psutil is None:
        return PerformanceSnapshot(
            wall_time_s=now,
            cpu_user_s=None,
            cpu_system_s=None,
            rss_bytes=None,
            io_read_bytes=None,
            io_write_bytes=None,
        )

    process = psutil.Process()
    cpu_times = process.cpu_times()
    io_counters = process.io_counters() if hasattr(process, "io_counters") else None
    memory = process.memory_info()
    return PerformanceSnapshot(
        wall_time_s=now,
        cpu_user_s=float(cpu_times.user),
        cpu_system_s=float(cpu_times.system),
        rss_bytes=int(memory.rss),
        io_read_bytes=int(io_counters.read_bytes) if io_counters else None,
        io_write_bytes=int(io_counters.write_bytes) if io_counters else None,
    )


def _delta(label: str, start: PerformanceSnapshot, end: PerformanceSnapshot) -> PerformanceResult:
    def _sub(a: float | int | None, b: float | int | None) -> float | int | None:
        if a is None or b is None:
            return None
        return b - a

    return PerformanceResult(
        label=label,
        wall_time_s=end.wall_time_s - start.wall_time_s,
        cpu_user_s=_sub(start.cpu_user_s, end.cpu_user_s),
        cpu_system_s=_sub(start.cpu_system_s, end.cpu_system_s),
        rss_bytes=end.rss_bytes,
        io_read_bytes=_sub(start.io_read_bytes, end.io_read_bytes),
        io_write_bytes=_sub(start.io_write_bytes, end.io_write_bytes),
    )


@contextmanager
def measure_block(label: str, *, phase: str = "-", action: str = "PERF"):
    """Measure a code block and emit a structured perf log on exit."""

    start = _snapshot()
    try:
        yield
    finally:
        result = _delta(label, start, _snapshot())
        logger.info(
            "Perf metric",
            extra={
                "phase": phase,
                "action": action,
                "codes_extracted": (
                    f"label={result.label},"
                    f"wall_s={result.wall_time_s:.6f},"
                    f"cpu_user_s={result.cpu_user_s},"
                    f"cpu_system_s={result.cpu_system_s},"
                    f"rss={result.rss_bytes},"
                    f"io_r={result.io_read_bytes},"
                    f"io_w={result.io_write_bytes}"
                ),
            },
        )


def profile_performance(label: str, *, phase: str = "-", action: str = "PERF") -> Callable[[F], F]:
    """Decorator that profiles a function and emits structured performance logs."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any):
            start = _snapshot()
            try:
                return func(*args, **kwargs)
            finally:
                result = _delta(label, start, _snapshot())
                logger.info(
                    "Perf metric",
                    extra={
                        "phase": phase,
                        "action": action,
                        "codes_extracted": (
                            f"label={result.label},"
                            f"wall_s={result.wall_time_s:.6f},"
                            f"cpu_user_s={result.cpu_user_s},"
                            f"cpu_system_s={result.cpu_system_s},"
                            f"rss={result.rss_bytes},"
                            f"io_r={result.io_read_bytes},"
                            f"io_w={result.io_write_bytes}"
                        ),
                    },
                )

        return wrapper  # type: ignore[return-value]

    return decorator

