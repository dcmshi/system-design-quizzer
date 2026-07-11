from pathlib import Path

import frontmatter
from ulid import ULID

from quizzer.config import settings
from quizzer.ingestion.cleaner import clean_text
from quizzer.ingestion.models import Document


def resolve_source_path(source_path: str) -> Path:
    """Resolve a stored ``source_path`` back to a real filesystem path.

    Paths are stored relative to ``settings.content_dir`` (see ``load_document``),
    so a bare ``Path(source_path)`` will not resolve from the process CWD. Prefer
    ``content_dir / source_path`` when it exists; fall back to the raw path for
    absolute paths or documents stored outside the content directory.
    """
    raw = Path(source_path)
    if raw.is_absolute():
        return raw
    candidate = settings.content_dir / raw
    if candidate.exists():
        return candidate
    return raw


def load_document(path: Path) -> Document:
    post = frontmatter.load(str(path))

    title: str = post.get("title", path.stem.replace("-", " ").title())
    source: str = post.get("source", "unknown")
    tags: list[str] = post.get("tags", [])

    content = clean_text(post.content)

    try:
        relative_path = str(path.relative_to(settings.content_dir))
    except ValueError:
        relative_path = str(path)

    return Document(
        id=str(ULID()),
        title=title,
        source=source,
        content=content,
        tags=tags if isinstance(tags, list) else [tags],
        source_path=relative_path,
    )
