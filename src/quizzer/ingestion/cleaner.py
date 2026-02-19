import re
import unicodedata


def clean_text(raw: str) -> str:
    # NFC Unicode normalization
    text = unicodedata.normalize("NFC", raw)
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse 3+ consecutive blank lines → 2 blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    return text.strip()
