import json
import sqlite3

from quizzer.database import get_connection
from quizzer.ingestion.models import Chunk, Document


class DocumentRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def upsert(self, doc: Document) -> None:
        self._conn.execute(
            """
            INSERT INTO documents (id, title, source, content, tags, source_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_path) DO UPDATE SET
                title = excluded.title,
                source = excluded.source,
                content = excluded.content,
                tags = excluded.tags,
                created_at = excluded.created_at
            """,
            (
                doc.id,
                doc.title,
                doc.source,
                doc.content,
                json.dumps(doc.tags),
                doc.source_path,
                doc.created_at,
            ),
        )
        self._conn.commit()

    def upsert_chunk(self, chunk: Chunk) -> None:
        self._conn.execute(
            """
            INSERT INTO chunks (id, document_id, content, word_count, chunk_index, heading, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                chunk.id,
                chunk.document_id,
                chunk.content,
                chunk.word_count,
                chunk.chunk_index,
                chunk.heading,
                chunk.created_at,
            ),
        )
        self._conn.commit()

    def get_by_source_path(self, source_path: str) -> Document | None:
        row = self._conn.execute(
            "SELECT * FROM documents WHERE source_path = ?", (source_path,)
        ).fetchone()
        if row is None:
            return None
        return Document(
            id=row["id"],
            title=row["title"],
            source=row["source"],
            content=row["content"],
            tags=json.loads(row["tags"]),
            source_path=row["source_path"],
            created_at=row["created_at"],
        )

    def list_all(self) -> list[Document]:
        rows = self._conn.execute("SELECT * FROM documents ORDER BY created_at").fetchall()
        return [
            Document(
                id=r["id"],
                title=r["title"],
                source=r["source"],
                content=r["content"],
                tags=json.loads(r["tags"]),
                source_path=r["source_path"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def list_all_tags(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT value FROM documents, json_each(documents.tags) ORDER BY value"
        ).fetchall()
        return [r["value"] for r in rows]

    def list_chunks(self, document_id: str) -> list[Chunk]:
        rows = self._conn.execute(
            "SELECT * FROM chunks WHERE document_id = ? ORDER BY chunk_index", (document_id,)
        ).fetchall()
        return [
            Chunk(
                id=r["id"],
                document_id=r["document_id"],
                content=r["content"],
                word_count=r["word_count"],
                chunk_index=r["chunk_index"],
                heading=r["heading"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
