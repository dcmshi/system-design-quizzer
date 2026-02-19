import hashlib
import re


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fingerprint(text: str) -> str:
    normalized = _normalize_text(text)
    return hashlib.sha256(normalized.encode()).hexdigest()


def is_duplicate(text: str, existing_fingerprints: set[str]) -> bool:
    return fingerprint(text) in existing_fingerprints
