"""Unit tests for the html_to_md preprocessing script's pure helpers.

Only the dependency-free helpers are exercised here (bs4/markdownify are
imported lazily inside convert()/article_to_markdown() and are optional extras).
"""

import sys
from pathlib import Path

import frontmatter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from html_to_md import build_frontmatter  # noqa: E402


def _roundtrip(fm: str) -> frontmatter.Post:
    return frontmatter.loads(fm + "\n\n# Body\n\ntext")


def test_build_frontmatter_plain_title():
    post = _roundtrip(build_frontmatter("Consistent Hashing", "https://ex.com/a", ["system-design"]))
    assert post["title"] == "Consistent Hashing"
    assert post["source"] == "ByteByteGo"
    assert post["url"] == "https://ex.com/a"
    assert post["tags"] == ["system-design"]


def test_build_frontmatter_title_with_double_quotes():
    """Regression: a title containing quotes must still yield valid YAML."""
    title = 'What is a "Load Balancer"?'
    post = _roundtrip(build_frontmatter(title, "", ["system-design"]))
    assert post["title"] == title


def test_build_frontmatter_title_with_backslash():
    title = r'Path C:\temp and a "quote"'
    post = _roundtrip(build_frontmatter(title, "", []))
    assert post["title"] == title


def test_build_frontmatter_omits_url_when_empty():
    fm = build_frontmatter("T", "", ["a"])
    assert "url:" not in fm
    assert _roundtrip(fm)["title"] == "T"
