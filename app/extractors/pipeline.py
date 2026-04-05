"""HTTP fetching and extraction pipeline."""

from __future__ import annotations

import time
from datetime import datetime, UTC
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from app.cleaners import clean_text
from app.exceptions import ExtractionError, FetchError
from app.extractors.ao3 import ao3_extract, is_ao3_url
from app.extractors.base import generic_extract
from app.schemas import ExtractedDocument
from app.utils import write_text


def fetch_html(
    url: str,
    user_agent: str,
    timeout_seconds: int,
    max_retries: int,
) -> str:
    headers = {"User-Agent": user_agent}
    attempt = 0
    while True:
        try:
            response = requests.get(url, headers=headers, timeout=timeout_seconds)
            if response.status_code == 403:
                raise FetchError("目标页面返回 403，可能不可公开访问或禁止抓取。")
            if response.status_code == 429:
                raise FetchError("目标页面返回 429，请稍后重试，当前不会继续重试。")
            if response.status_code >= 500:
                raise FetchError(
                    f"目标站点返回 {response.status_code}，服务暂时不可用。"
                )
            if response.status_code >= 400:
                raise FetchError(
                    f"请求失败，HTTP {response.status_code}。请确认 URL 是否公开可访问。"
                )
            return response.text
        except requests.Timeout as exc:
            if attempt >= max_retries:
                raise FetchError("请求超时，请稍后重试或检查目标站点响应速度。") from exc
        except requests.RequestException as exc:
            if attempt >= max_retries:
                raise FetchError(f"网络请求失败：{exc}") from exc
        attempt += 1
        time.sleep(min(2**attempt, 2))


def extract_document(
    url: str,
    outdir: Path,
    user_agent: str,
    timeout_seconds: int = 20,
    max_retries: int = 1,
    save_raw_html: bool = True,
) -> ExtractedDocument:
    html = fetch_html(url, user_agent, timeout_seconds, max_retries)
    raw_html_path: str | None = None
    if save_raw_html:
        raw_html_file = outdir / "raw.html"
        write_text(raw_html_file, html)
        raw_html_path = str(raw_html_file)

    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else "Untitled").strip()
    site_type = "ao3" if is_ao3_url(url) else "generic"

    raw_text = ""
    if is_ao3_url(url):
        raw_text = ao3_extract(soup)
        if not raw_text:
            raw_text = generic_extract(soup)
    else:
        raw_text = generic_extract(soup)
        if not raw_text and is_ao3_url(url):
            raw_text = ao3_extract(soup)

    if not raw_text or len(raw_text.strip()) < 20:
        raise ExtractionError("未能提取到有效正文，页面可能不是公开正文页或结构已变化。")

    cleaned_text = clean_text(raw_text)
    return ExtractedDocument(
        title=title,
        source_url=url,
        raw_html_path=raw_html_path,
        raw_text=raw_text,
        cleaned_text=cleaned_text,
        metadata={
            "site_type": site_type,
            "fetched_at": datetime.now(UTC).isoformat(),
        },
    )
