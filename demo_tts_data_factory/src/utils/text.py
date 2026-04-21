"""Text utilities."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime


def make_case_id(text: str, prefix: str = "case") -> str:
    normalized = re.sub(r"\s+", "", text)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}_{digest}"
