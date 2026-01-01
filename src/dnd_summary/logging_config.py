from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from dnd_summary.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if settings.log_format == "json":
        handlers[0].setFormatter(JsonFormatter())
    else:
        handlers[0].setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        handlers=handlers,
    )
