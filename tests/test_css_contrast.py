"""WCAG contrast checks for the shared palette.

The tokens in app.css are the whole colour vocabulary of the three pages, so
checking the pairs that actually appear catches a regression at the source
rather than needing a screenshot diff.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP_CSS = Path(__file__).parents[1] / "src" / "quizzer" / "quiz" / "static" / "css" / "app.css"

AA_NORMAL = 4.5   # body text
AA_LARGE = 3.0    # >= 24px, or >= 18.7px bold — also the bar for UI borders


def _tokens() -> dict[str, str]:
    root = re.search(r":root\s*\{(.*?)\}", APP_CSS.read_text(encoding="utf-8"), re.S)
    assert root, "app.css has no :root block"
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", root.group(1)))


def _luminance(colour: str) -> float:
    channels = [int(colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    a, b = _luminance(foreground), _luminance(background)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# (description, foreground token or literal, background token, minimum)
PAIRS = [
    ("body text on the page",            "text",        "bg",        AA_NORMAL),
    ("body text on a card",              "text",        "surface",   AA_NORMAL),
    ("muted labels on the page",         "text-muted",  "bg",        AA_NORMAL),
    ("muted labels on a card",           "text-muted",  "surface",   AA_NORMAL),
    ("muted labels on an inset panel",   "text-muted",  "surface2",  AA_NORMAL),
    ("accent text on a card",            "accent-text", "surface",   AA_NORMAL),
    ("accent text on an inset panel",    "accent-text", "surface2",  AA_NORMAL),
    ("white on a filled button",         "#ffffff",     "accent-fill", AA_NORMAL),
    ("white on a hovered filled button", "#ffffff",     "accent-hover", AA_NORMAL),
    ("display numerals on a card",       "accent",      "surface",   AA_LARGE),
    ("accent borders on a card",         "accent",      "surface",   AA_LARGE),
]


@pytest.mark.parametrize("description,fg,bg,minimum", PAIRS)
def test_palette_pair_meets_wcag_aa(description: str, fg: str, bg: str, minimum: float):
    tokens = _tokens()
    foreground = fg if fg.startswith("#") else tokens[fg]
    background = tokens[bg]
    ratio = contrast(foreground, background)
    assert ratio >= minimum, (
        f"{description}: {foreground} on {background} is {ratio:.2f}:1, needs {minimum}:1"
    )


def test_keyboard_focus_is_always_visible():
    """A border-colour shift is easy to miss and buttons had no focus style at
    all, so the shared sheet owns one ring and nothing suppresses it."""
    css_dir = APP_CSS.parent
    assert re.search(r":focus-visible\s*\{[^}]*outline:", APP_CSS.read_text(encoding="utf-8"))

    suppressed = [
        path.name for path in sorted(css_dir.glob("*.css"))
        if re.search(r"outline:\s*(none|0)\b", path.read_text(encoding="utf-8"))
    ]
    assert suppressed == []


def test_no_page_dims_small_text_with_opacity():
    """Half-opacity muted text was 2.35:1. Dim small text by choosing a colour
    that still passes, not by fading one that does."""
    css_dir = APP_CSS.parent
    offenders = []
    for path in sorted(css_dir.glob("*.css")):
        for rule in re.findall(r"([^{}]+)\{([^{}]*)\}", path.read_text(encoding="utf-8")):
            selector, body = rule
            opacity = re.search(r"(?<![\w-])opacity:\s*([\d.]+)", body)
            size = re.search(r"font-size:\s*([\d.]+)rem", body)
            # opacity:0 is a show/hide state (the toast), not dimmed text.
            if opacity and 0 < float(opacity.group(1)) < 1 and size and float(size.group(1)) < 1:
                offenders.append(f"{path.name}: {selector.strip()}")
    assert offenders == []
