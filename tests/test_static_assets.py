"""The static pages reference their CSS and JS by URL, so a wrong href only
shows up as a 404 in the browser. These tests fetch every referenced asset."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quizzer.quiz.app import create_app

STATIC_DIR = Path(__file__).parents[1] / "src" / "quizzer" / "quiz" / "static"
PAGES = ["/", "/review/", "/sources/"]

ASSET_REF = re.compile(r'(?:href|src)="(/(?:css/|js/|favicon)[^"]+)"')


@pytest.fixture()
def client() -> TestClient:
    # StaticFiles is mounted in create_app(), so no lifespan is needed here.
    return TestClient(create_app())


@pytest.mark.parametrize("page", PAGES)
def test_page_is_served(client: TestClient, page: str):
    resp = client.get(page)
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" in resp.text


@pytest.mark.parametrize("page", PAGES)
def test_every_referenced_asset_resolves(client: TestClient, page: str):
    refs = ASSET_REF.findall(client.get(page).text)
    assert refs, f"{page} references no extracted assets"
    for ref in refs:
        resp = client.get(ref)
        assert resp.status_code == 200, f"{page} -> {ref}"
        if ref.endswith((".css", ".js")):
            # Both carry non-ASCII text and are parsed with the declared charset.
            assert "charset=utf-8" in resp.headers["content-type"], ref


@pytest.mark.parametrize("page", PAGES)
def test_pages_carry_no_inline_style_or_script_blocks(client: TestClient, page: str):
    """CSS and JS live in shared files so the browser can cache them across pages."""
    html = client.get(page).text
    assert "<style>" not in html
    assert re.search(r"<script(?![^>]*\bsrc=)", html) is None


@pytest.mark.parametrize("page", PAGES)
def test_markup_carries_no_static_inline_styles(client: TestClient, page: str):
    """State belongs in classes the JS toggles, not in style strings — the two
    used to be mixed for the same elements."""
    styles = re.findall(r'style="([^"]*)"', client.get(page).text)
    # The progress bar's width is genuinely computed per question.
    assert [s for s in styles if not s.startswith("width:")] == []


def test_no_script_uses_the_non_standard_scroll_behavior():
    """'instant' is a Chromium-ism; other engines ignore the whole call."""
    for path in sorted((STATIC_DIR / "js").glob("*.js")):
        assert "'instant'" not in path.read_text(encoding="utf-8"), path.name


def test_no_script_writes_display_directly():
    for path in sorted((STATIC_DIR / "js").glob("*.js")):
        assert "style.display" not in path.read_text(encoding="utf-8"), path.name


@pytest.mark.parametrize("page", PAGES)
def test_cross_page_links_share_one_style(client: TestClient, page: str):
    """Each page used to hand-roll its own link row."""
    html = client.get(page).text
    assert 'class="nav-links' in html
    assert html.count('class="back-link"') >= 2


@pytest.mark.parametrize("page", PAGES)
def test_page_declares_a_favicon_and_description(client: TestClient, page: str):
    """Without an icon link every load 404s on /favicon.ico."""
    html = client.get(page).text
    assert '<link rel="icon" href="/favicon.svg"' in html
    description = re.search(r'<meta name="description" content="([^"]+)"', html)
    assert description and len(description.group(1)) > 40


def test_no_page_falls_back_to_favicon_ico(client: TestClient):
    assert client.get("/favicon.ico").status_code == 404
    assert client.get("/favicon.svg").status_code == 200


def test_quiz_page_centres_without_clipping_tall_content():
    """align-items:center on a flex body pushes the top of an over-tall card
    out of scroll reach; auto margins on the child centre without clipping."""
    css = (STATIC_DIR / "css" / "quiz.css").read_text(encoding="utf-8")
    body = re.search(r"^body \{(.*?)\}", css, re.S | re.M).group(1)
    app = re.search(r"^#app \{(.*?)\}", css, re.S | re.M).group(1)

    assert "align-items: center" not in body
    assert "justify-content: center" not in body
    assert "margin: auto" in app


def test_shared_stylesheet_is_the_only_token_block():
    """One :root block, so the palette cannot drift between pages again."""
    with_tokens = [
        path.name
        for path in sorted((STATIC_DIR / "css").glob("*.css"))
        if ":root" in path.read_text(encoding="utf-8")
    ]
    assert with_tokens == ["app.css"]
