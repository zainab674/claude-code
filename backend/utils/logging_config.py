"""
Structured JSON logging — outputs log lines as JSON for
Datadog, CloudWatch, Papertrail, Logtail, etc.

Set LOG_FORMAT=json in .env to enable.
Default is human-readable for development.
"""
import os
import sys
import json
import time
import logging
import traceback
from datetime import datetime
from typing import Optional

LOG_FORMAT = os.getenv("LOG_FORMAT", "text")   # text | json
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
SERVICE_NAME = "payrollos"
SERVICE_VERSION = "1.0.0"


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON for log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        log = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "env": os.getenv("APP_ENV", "development"),
        }

        # Add extra fields set via logger.info("msg", extra={"user_id": "..."})
        for key, val in record.__dict__.items():
            if key not in (
                "args", "asctime", "created", "exc_info", "exc_text",
                "filename", "funcName", "id", "levelname", "levelno",
                "lineno", "module", "msecs", "message", "msg", "name",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "thread", "threadName",
            ):
                log[key] = val

        # Exception info
        if record.exc_info:
            log["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        # Source location (only for warnings+)
        if record.levelno >= logging.WARNING:
            log["source"] = {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
            }

        return json.dumps(log, default=str)


class TextFormatter(logging.Formatter):
    """Colored human-readable format for development."""

    COLORS = {
        "DEBUG":    "\033[36m",    # cyan
        "INFO":     "\033[32m",    # green
        "WARNING":  "\033[33m",    # yellow
        "ERROR":    "\033[31m",    # red
        "CRITICAL": "\033[35m",    # magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.utcnow().strftime("%H:%M:%S")
        level = f"{color}{self.BOLD}{record.levelname:<8}{self.RESET}"
        name = f"\033[90m{record.name}\033[0m"
        msg = record.getMessage()

        line = f"{ts} {level} {name} — {msg}"

        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)

        return line


def setup_logging():
    """Configure logging for the entire application."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Remove existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    if LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter())

    root.addHandler(handler)

    # Suppress noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    logger = logging.getLogger("payrollos.startup")
    logger.info(f"Logging configured: level={LOG_LEVEL} format={LOG_FORMAT}")
    return logger
