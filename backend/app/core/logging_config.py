import logging
import os
import time
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from queue import Queue

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5

_listener: QueueListener | None = None


def setup_logging(level: int = logging.INFO) -> None:
    """Add async rotating file logging alongside uvicorn's default console output.

    Instead of replacing the root logger's handlers (which breaks uvicorn's
    console output under --reload), we add a QueueHandler that feeds a
    RotatingFileHandler via a QueueListener.  This way:
      - Console output works as usual (managed by uvicorn)
      - All log records are also written to ``logs/app.log``
      - File writes are non-blocking (queued)

    Log timestamps: dev uses local timezone, other envs use UTC (consistent with frontend).
    """
    global _listener

    os.makedirs(LOG_DIR, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if os.environ.get("OPENCOLAB_ENV", "dev") != "dev":
        fmt.converter = time.gmtime

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(level)

    log_queue: Queue = Queue(-1)
    queue_handler = QueueHandler(log_queue)

    _listener = QueueListener(log_queue, file_handler, respect_handler_level=True)
    _listener.start()

    # Add file logging to root logger (don't clear existing handlers)
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(queue_handler)

    # Capture uvicorn loggers into the file without duplicating via propagation
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.addHandler(queue_handler)
        uv_logger.propagate = False

    # Quiet noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)


def shutdown_logging() -> None:
    """Stop the queue listener (call on app shutdown)."""
    global _listener
    if _listener:
        _listener.stop()
        _listener = None
