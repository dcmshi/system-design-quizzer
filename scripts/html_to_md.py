#!/usr/bin/env python3
"""Convert a saved ByteByteGo HTML page to a clean Markdown article.

Usage:
    uv run python scripts/html_to_md.py content/some-article.html
    uv run python scripts/html_to_md.py content/some-article.html -o content/bytebytego/some-article.md

The script targets the <article> element inside #content, strips images
(keeping their alt text as figure captions), removes nav chrome, and emits
a .md file with YAML frontmatter compatible with the ingest pipeline.
"""

import argparse
import re
import sys
from pathlib import Path


def extract_source_url(html: str) -> str:
    m = re.search(r"saved from url=\(\d+\)(https?://\S+)", html)
    return m.group(1) if m else ""


def clean_article(article, bs) -> None:
    """Remove noise elements from the parsed article tag in-place."""
    # Drop navigation, sidebars, footers, prev/next buttons
    for sel in [
        "nav", "footer", "aside",
        "[class*='nav']", "[class*='sidebar']",
        "[class*='breadcrumb']", "[class*='pagination']",
        "[class*='prevNext']", "[class*='footer']",
    ]:
        for el in article.select(sel):
            el.decompose()

    # Replace <figure>/<img> with a plain caption paragraph so the text
    # still describes the diagram without broken image references.
    for figure in article.find_all("figure"):
        img = figure.find("img")
        alt = (img.get("alt") or "").strip() if img else ""
        if alt:
            caption = alt if len(alt) <= 200 else alt[:197] + "..."
            new_p = bs.new_tag("p")
            new_p.string = f"[Figure: {caption}]"
            figure.replace_with(new_p)
        else:
            figure.decompose()

    # Strip bare <img> tags outside figures
    for img in article.find_all("img"):
        alt = (img.get("alt") or "").strip()
        if alt:
            new_p = bs.new_tag("p")
            new_p.string = f"[Figure: {alt}]"
            img.replace_with(new_p)
        else:
            img.decompose()

    # Convert <a href="..."> → keep text, drop href (links point to bytebytego.com)
    for a in article.find_all("a"):
        a.unwrap()


def article_to_markdown(article_html: str) -> str:
    import markdownify

    md = markdownify.markdownify(
        article_html,
        heading_style="ATX",
        bullets="-",
        newline_style="backslash",
    )
    # Collapse 3+ blank lines to 2
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def build_frontmatter(title: str, source_url: str, tags: list[str]) -> str:
    tag_list = ", ".join(f'"{t}"' for t in tags)
    lines = [
        "---",
        f'title: "{title}"',
        f'source: "ByteByteGo"',
    ]
    if source_url:
        lines.append(f'url: "{source_url}"')
    lines.append(f"tags: [{tag_list}]")
    lines.append("---")
    return "\n".join(lines)


def convert(html_path: Path, output_path: Path) -> None:
    from bs4 import BeautifulSoup

    html = html_path.read_text(encoding="utf-8")
    source_url = extract_source_url(html)

    bs = BeautifulSoup(html, "html.parser")

    # Locate the article element
    article = bs.find("article")
    if not article:
        article = bs.find("div", id="content") or bs.body
    if not article:
        print("ERROR: Could not locate article content.", file=sys.stderr)
        sys.exit(1)

    # Extract title before mutating the tree
    h1 = article.find("h1")
    title = h1.get_text(strip=True) if h1 else html_path.stem.replace("-", " ").title()

    # Remove the <header> block (chapter number + h1) — we'll emit # title ourselves
    header = article.find("header")
    if header:
        header.decompose()
    elif h1:
        h1.decompose()

    clean_article(article, bs)

    md_body = article_to_markdown(str(article))

    frontmatter = build_frontmatter(title, source_url, ["system-design"])
    output = f"{frontmatter}\n\n# {title}\n\n{md_body}\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")
    print(f"Written {len(output):,} chars -> {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Convert a saved ByteByteGo HTML page to Markdown.")
    parser.add_argument("html_file", type=Path, help="Path to the saved .html file")
    parser.add_argument(
        "-o", "--output", type=Path,
        help="Output .md path (default: content/bytebytego/<stem>.md)",
    )
    args = parser.parse_args()

    html_path: Path = args.html_file
    if not html_path.exists():
        print(f"ERROR: File not found: {html_path}", file=sys.stderr)
        sys.exit(1)

    output_path: Path = args.output or Path("content/bytebytego") / f"{html_path.stem}.md"
    convert(html_path, output_path)


if __name__ == "__main__":
    main()
