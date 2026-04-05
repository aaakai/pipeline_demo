"""AO3-specific extraction rules."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup


def is_ao3_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "archiveofourown.org" in host


def _normalize_ao3_text(text: str) -> str:
    text = re.sub(r"^\s*Chapter Text\s*", "", text)
    return text.strip()


def _extract_blocks(container) -> str:
    blocks: list[str] = []
    for node in container.find_all(["p", "blockquote", "li"]):
        text = node.get_text(" ", strip=True)
        if text:
            blocks.append(text)

    if not blocks:
        return _normalize_ao3_text(container.get_text("\n", strip=True))
    return _normalize_ao3_text("\n\n".join(blocks))


def ao3_extract(soup: BeautifulSoup) -> str:
    # Prefer the chapter/article body and avoid front/end notes that also use .userstuff.
    preferred_selectors = [
        "#chapters [role='article'].userstuff",
        "#chapters .userstuff[role='article']",
        "#chapters .chapter .chapter-content .userstuff",
        ".preface + .userstuff",
        "div[role='article'].userstuff",
    ]
    for selector in preferred_selectors:
        containers = soup.select(selector)
        for container in containers:
            classes = container.get("class", [])
            if "notes" in classes or "summary" in classes:
                continue
            text = _extract_blocks(container)
            if text:
                return text
    return ""
