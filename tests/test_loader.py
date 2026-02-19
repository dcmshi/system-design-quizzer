from pathlib import Path

import pytest

from quizzer.ingestion.loader import load_document


def _write_md(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_load_basic_document(tmp_path):
    md = _write_md(
        tmp_path,
        "article.md",
        "---\ntitle: Test Article\nsource: blog\ntags: [systems, databases]\n---\n\nContent here.",
    )
    doc = load_document(md)
    assert doc.title == "Test Article"
    assert doc.source == "blog"
    assert doc.tags == ["systems", "databases"]
    assert "Content here." in doc.content
    assert doc.id  # has a ULID


def test_load_document_without_frontmatter(tmp_path):
    md = _write_md(tmp_path, "no-fm.md", "Just plain content with no frontmatter.")
    doc = load_document(md)
    assert doc.title  # falls back to filename
    assert "plain content" in doc.content


def test_load_document_strips_html(tmp_path):
    md = _write_md(
        tmp_path,
        "html.md",
        "---\ntitle: HTML Test\nsource: test\n---\n\n<p>Paragraph</p> and <b>bold</b>.",
    )
    doc = load_document(md)
    assert "<p>" not in doc.content
    assert "Paragraph" in doc.content


def test_load_document_collapses_blank_lines(tmp_path):
    md = _write_md(
        tmp_path,
        "blanks.md",
        "---\ntitle: Blanks\nsource: test\n---\n\nPara one.\n\n\n\n\nPara two.",
    )
    doc = load_document(md)
    assert "\n\n\n" not in doc.content


def test_source_path_is_relative(tmp_path, monkeypatch):
    from quizzer import config
    monkeypatch.setattr(config.settings, "content_dir", tmp_path)

    md = _write_md(tmp_path, "article.md", "---\ntitle: T\nsource: s\n---\nBody.")
    doc = load_document(md)
    assert doc.source_path == "article.md"
