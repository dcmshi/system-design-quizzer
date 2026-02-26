import json
import sqlite3
from typing import Literal

from quizzer.database import get_connection


class QuestionRecord:
    __slots__ = (
        "id", "question", "options", "correct_index", "explanation",
        "difficulty", "source_document_id", "source_chunk_id", "status",
        "fingerprint", "model", "prompt_version", "created_at",
    )

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class QuestionRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def insert(
        self,
        *,
        id: str,
        question: str,
        options: list[str],
        correct_index: int,
        explanation: str,
        difficulty: str,
        source_document_id: str,
        source_chunk_id: str,
        fingerprint: str,
        model: str,
        prompt_version: str,
        created_at: str,
        status: str = "generated",
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO questions (
                id, question, options, correct_index, explanation, difficulty,
                source_document_id, source_chunk_id, status, fingerprint,
                model, prompt_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id, question, json.dumps(options), correct_index, explanation,
                difficulty, source_document_id, source_chunk_id, status,
                fingerprint, model, prompt_version, created_at,
            ),
        )
        self._conn.commit()

    def get_by_id(self, question_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM questions WHERE id = ?", (question_id,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_questions(
        self,
        *,
        difficulty: str | None = None,
        status: str | None = None,
        document_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        filters: list[str] = []
        params: list = []
        if difficulty:
            filters.append("difficulty = ?")
            params.append(difficulty)
        if status:
            filters.append("status = ?")
            params.append(status)
        if document_id:
            filters.append("source_document_id = ?")
            params.append(document_id)

        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        params.extend([limit, offset])
        rows = self._conn.execute(
            f"SELECT * FROM questions {where} ORDER BY created_at LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_question(
        self,
        question_id: str,
        *,
        question: str,
        options: list[str],
        correct_index: int,
        explanation: str,
        difficulty: str,
    ) -> bool:
        cur = self._conn.execute(
            """UPDATE questions SET question=?, options=?, correct_index=?,
               explanation=?, difficulty=? WHERE id=?""",
            (question, json.dumps(options), correct_index, explanation, difficulty, question_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def update_status(
        self, question_id: str, status: Literal["generated", "approved", "edited", "rejected"]
    ) -> bool:
        cur = self._conn.execute(
            "UPDATE questions SET status = ? WHERE id = ?", (status, question_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def counts_by_status(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM questions GROUP BY status"
        ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}

    def counts_by_difficulty(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT difficulty, COUNT(*) as cnt FROM questions GROUP BY difficulty"
        ).fetchall()
        return {r["difficulty"]: r["cnt"] for r in rows}

    def get_all_fingerprints(self) -> set[str]:
        rows = self._conn.execute("SELECT fingerprint FROM questions").fetchall()
        return {r["fingerprint"] for r in rows}

    def get_random_sample(
        self,
        n: int,
        difficulty: str | None = None,
        document_ids: list[str] | None = None,
        tag: str | None = None,
    ) -> list[dict]:
        filters: list[str] = ["q.status != 'rejected'"]
        params: list = []

        if difficulty:
            filters.append("q.difficulty = ?")
            params.append(difficulty)
        if document_ids:
            placeholders = ",".join(["?"] * len(document_ids))
            filters.append(f"q.source_document_id IN ({placeholders})")
            params.extend(document_ids)
        if tag:
            filters.append(
                "EXISTS (SELECT 1 FROM json_each(d.tags) WHERE value = ?)"
            )
            params.append(tag)

        where = "WHERE " + " AND ".join(filters)
        params.append(n)

        if tag:
            sql = (
                f"SELECT q.* FROM questions q "
                f"JOIN documents d ON q.source_document_id = d.id "
                f"{where} ORDER BY RANDOM() LIMIT ?"
            )
        else:
            sql = f"SELECT q.* FROM questions q {where} ORDER BY RANDOM() LIMIT ?"

        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count_by_document(self, document_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM questions WHERE source_document_id = ?",
            (document_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    @staticmethod
    def _row_to_dict(row) -> dict:
        d = dict(row)
        d["options"] = json.loads(d["options"])
        return d
