"""Base extraction helpers."""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

COMMON_CONTAINER_SELECTORS = [
    "article",
    "main",
    '[role="main"]',
    ".article-content",
    ".post-content",
    ".entry-content",
    ".content",
]

NOISE_SELECTORS = [
    "script",
    "style",
    "nav",
    "footer",
    "header",
    "noscript",
    "aside",
    "form",
]


def prune_noise(soup: BeautifulSoup) -> None:
    for selector in NOISE_SELECTORS:
        for node in soup.select(selector):
            node.decompose()


def extract_text_from_container(container: Tag) -> str:
    blocks: list[str] = []
    for node in container.find_all(["p", "div", "blockquote", "li"]):
        text = node.get_text(" ", strip=True)
        if text:
            blocks.append(text)

    if not blocks:
        text = container.get_text("\n", strip=True)
        return text.strip()
    return "\n\n".join(blocks).strip()


def generic_extract(soup: BeautifulSoup) -> str:
    prune_noise(soup)
    for selector in COMMON_CONTAINER_SELECTORS:
        container = soup.select_one(selector)
        if container:
            text = extract_text_from_container(container)
            if text:
                return text

    body = soup.body or soup
    return extract_text_from_container(body)
