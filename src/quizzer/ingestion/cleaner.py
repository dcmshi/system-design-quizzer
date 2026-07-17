import re
import unicodedata

# Only strip real HTML tags. A bare `<[^>]+>` would eat any `<`…`>` span,
# destroying prose like "latency < 100ms … p99 > 250ms" and generics like
# Map<String, User>, so we whitelist tag names instead.
_HTML_TAG_NAMES = (
    "a|abbr|article|aside|b|blockquote|br|caption|cite|code|col|colgroup|dd|del|details|div|dl|dt|"
    "em|figcaption|figure|footer|h[1-6]|header|hr|i|iframe|img|ins|kbd|li|main|mark|nav|ol|p|"
    "picture|pre|q|s|section|small|source|span|strong|sub|summary|sup|table|tbody|td|tfoot|th|"
    "thead|tr|u|ul|video"
)
_HTML_TAG_RE = re.compile(rf"</?(?:{_HTML_TAG_NAMES})(?=[\s/>])[^>\n]*>", re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def clean_text(raw: str) -> str:
    # NFC Unicode normalization
    text = unicodedata.normalize("NFC", raw)
    # Strip HTML comments and tags
    text = _HTML_COMMENT_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    # Collapse 3+ consecutive blank lines → 2 blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    return text.strip()
