from pathlib import Path

import pytest


@pytest.fixture()
def ao3_html() -> str:
    return (Path(__file__).parent / "fixtures" / "ao3_chapter.html").read_text(
        encoding="utf-8"
    )


@pytest.fixture()
def generic_html() -> str:
    return (Path(__file__).parent / "fixtures" / "generic_article.html").read_text(
        encoding="utf-8"
    )
