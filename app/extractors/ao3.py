"""AO3-specific extraction rules."""

from __future__ import annotations

from urllib.parse import urlparse

from bs4 import BeautifulSoup


def is_ao3_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "archiveofourown.org" in host


def ao3_extract(soup: BeautifulSoup) -> str:
    # AO3 chapter content typically lives in .userstuff under chapter content.
    preferred_selectors = [
        "#chapters .chapter .userstuff",
        ".chapter .userstuff",
        "#workskin .userstuff",
        ".preface + .userstuff",
    ]
    for selector in preferred_selectors:
        container = soup.select_one(selector)
        if container:
            blocks: list[str] = []
            for node in container.find_all(["p", "blockquote", "li"]):
                text = node.get_text(" ", strip=True)
                if text:
                    blocks.append(text)
            text = "\n\n".join(blocks).strip()
            if text:
                return text
    return ""
