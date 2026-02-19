from pathlib import Path

import frontmatter
from ulid import ULID

from quizzer.config import settings
from quizzer.ingestion.cleaner import clean_text
from quizzer.ingestion.models import Document


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
