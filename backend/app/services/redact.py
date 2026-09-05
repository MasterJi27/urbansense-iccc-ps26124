"""Strip secrets from log records before they leave the process."""

from __future__ import annotations

import logging
import re

_PATTERNS = (
    re.compile(r"(subscription-key=)[^&\s]+", re.I),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-+=/]+", re.I),
    re.compile(r"(password['\"]?\s*[:=]\s*)\S+", re.I),
    re.compile(r"(postgresql(?:\+\w+)?:\/\/[^:]+:)[^@]+", re.I),
    re.compile(r"(AZURE_MAPS_SUBSCRIPTION_KEY['\"]?\s*[:=]\s*)\S+", re.I),
)


def redact_text(text: str) -> str:
    out = text
    for pat in _PATTERNS:
        out = pat.sub(r"\1[redacted]", out)
    return out


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(redact_text(a) if isinstance(a, str) else a for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: redact_text(v) if isinstance(v, str) else v for k, v in record.args.items()}
        return True


def install_redact_filter() -> None:
    filt = RedactFilter()
    logging.getLogger().addFilter(filt)
    logging.getLogger("urbansense").addFilter(filt)
    logging.getLogger("uvicorn.access").addFilter(filt)
