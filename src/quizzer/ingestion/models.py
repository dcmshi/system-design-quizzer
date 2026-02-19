from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Document(BaseModel):
    id: str
    title: str
    source: str
    content: str
    tags: list[str] = Field(default_factory=list)
    source_path: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class Chunk(BaseModel):
    id: str
    document_id: str
    content: str
    word_count: int
    chunk_index: int
    heading: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
