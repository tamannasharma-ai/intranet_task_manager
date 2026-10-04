import json
import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status_code", "duration_ms", "client_ip", "event"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("continuum")
    if logger.handlers:
        return logger

    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    formatter = JsonFormatter()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    default_log_file = Path(__file__).resolve().parent.parent / "logs" / "continuum.log"
    log_file = os.getenv("LOG_FILE", "" if os.getenv("VERCEL") == "1" else str(default_log_file)).strip()
    if log_file:
        try:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError:
            logger.exception("Unable to configure file logging; continuing with stdout")

    logger.propagate = False
    return logger


logger = configure_logging()
