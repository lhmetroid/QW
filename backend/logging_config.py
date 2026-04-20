import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler


SENSITIVE_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|pwd|encoding_aes_key)(['\"\s:=]+)([^'\"\s,}]+)"), r"\1\2***"),
    (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._\-]+"), r"\1***"),
    (re.compile(r"\b1[3-9]\d{9}\b"), "***PHONE***"),
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "***EMAIL***"),
]


def sanitize_text(value):
    """Mask secrets and common personal identifiers before writing production logs."""
    if value is None:
        return value
    text = str(value)
    for pattern, replacement in SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class DesensitizeFilter(logging.Filter):
    def filter(self, record):
        if str(os.getenv("LOG_DESENSITIZE_ENABLED", "true")).lower() in {"0", "false", "no"}:
            return True
        record.msg = sanitize_text(record.msg)
        if record.args:
            record.args = tuple(sanitize_text(arg) if isinstance(arg, str) else arg for arg in record.args)
        return True


def setup_logging():
    """Configure console and rotating file logs once."""
    root = logging.getLogger()
    if getattr(root, "_qw_logging_configured", False):
        return

    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "app.log")

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root.setLevel(logging.INFO)
    desensitize_filter = DesensitizeFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(desensitize_filter)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(desensitize_filter)

    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(file_handler)
    root._qw_logging_configured = True
