"""Process-wide logging setup.

LOG_FORMAT=json emits one JSON object per line (for GitHub Actions / Render log search);
anything else emits readable text. LOG_LEVEL defaults to INFO. Extra fields passed via
``logger.info("msg", extra={"fields": {...}})`` are included in both formats.
"""

import json
import logging
import os
import sys
import datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}) or {})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    def __init__(self):
        super().__init__("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        fields = getattr(record, "fields", None)
        if fields:
            text += " " + " ".join(f"{k}={v}" for k, v in fields.items())
        return text


def configure_logging(level: str | None = None, fmt: str | None = None) -> None:
    level = (level or os.environ.get("LOG_LEVEL") or "INFO").upper()
    fmt = (fmt or os.environ.get("LOG_FORMAT") or "text").lower()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # The driver logs every routing-table refresh at INFO; keep it to warnings.
    logging.getLogger("neo4j").setLevel(max(logging.WARNING, root.level))
    # Query notifications (e.g. "property key does not exist" on a fresh graph) are not job problems.
    logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
