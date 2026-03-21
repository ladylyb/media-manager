from __future__ import annotations

from collections import deque
import logging

LOG_BUFFER: deque[str] = deque(maxlen=1000)


class InMemoryLogHandler(logging.Handler):
    """Capture formatted log lines for lightweight in-process polling."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            LOG_BUFFER.append(self.format(record))
        except Exception:
            # Logging capture must never interfere with the main pipeline.
            return


def register_in_memory_log_handler(formatter: logging.Formatter | None = None) -> None:
    """Attach a single in-memory handler to the root logger."""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, InMemoryLogHandler):
            if formatter is not None:
                handler.setFormatter(formatter)
            return

    handler = InMemoryLogHandler()
    if formatter is not None:
        handler.setFormatter(formatter)
    root_logger.addHandler(handler)


def get_buffered_logs(limit: int | None = None) -> list[str]:
    """Return a stable newest-last snapshot of recent formatted log lines."""
    snapshot = list(LOG_BUFFER)
    if limit is None:
        return snapshot
    return snapshot[-limit:]
