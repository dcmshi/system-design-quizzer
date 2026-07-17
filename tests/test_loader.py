from pathlib import Path


from quizzer.ingestion.loader import load_document, resolve_source_path


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


def test_resolve_source_path_roundtrips_through_content_dir(tmp_path, monkeypatch):
    """A stored content-relative path (nested under content_dir) must resolve back."""
    from quizzer import config
    monkeypatch.setattr(config.settings, "content_dir", tmp_path)

    # simulate a nested article
    nested = tmp_path / "example" / "a.md"
    nested.parent.mkdir()
    nested.write_text("---\ntitle: A\nsource: s\n---\nBody.", encoding="utf-8")

    doc = load_document(nested)
    assert doc.source_path == str(Path("example") / "a.md")
    resolved = resolve_source_path(doc.source_path)
    assert resolved.exists()
    assert resolved == nested


def test_resolve_source_path_returns_raw_when_absent(tmp_path, monkeypatch):
    from quizzer import config
    monkeypatch.setattr(config.settings, "content_dir", tmp_path)
    resolved = resolve_source_path("does/not/exist.md")
    assert not resolved.exists()


def test_resolve_source_path_keeps_absolute(tmp_path):
    md = _write_md(tmp_path, "abs.md", "---\ntitle: T\n---\nBody.")
    resolved = resolve_source_path(str(md))
    assert resolved == md
    assert resolved.exists()
