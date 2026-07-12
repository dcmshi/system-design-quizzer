import json
import sqlite3

from quizzer.database import get_shared_connection


class SessionRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._explicit_conn = conn

    @property
    def _conn(self) -> sqlite3.Connection:
        return self._explicit_conn if self._explicit_conn is not None else get_shared_connection()

    def create_session(
        self,
        *,
        id: str,
        question_count: int,
        difficulty: str | None,
        tag: str | None,
        document_ids: list[str] | None,
        started_at: str,
    ) -> dict:
        self._conn.execute(
            """
            INSERT INTO quiz_sessions
                (id, question_count, difficulty, tag, document_ids, started_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                id,
                question_count,
                difficulty,
                tag,
                json.dumps(document_ids) if document_ids is not None else None,
                started_at,
            ),
        )
        self._conn.commit()
        return self.get_session(id)

    def finish_session(self, session_id: str, finished_at: str) -> bool:
        cur = self._conn.execute(
            "UPDATE quiz_sessions SET finished_at = ? WHERE id = ?",
            (finished_at, session_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_session(self, session_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM quiz_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["document_ids"] = json.loads(d["document_ids"]) if d["document_ids"] else None
        return d

    def add_answer(
        self,
        *,
        id: str,
        session_id: str,
        question_id: str,
        selected_index: int,
        is_correct: bool,
        answered_at: str,
    ) -> dict:
        self._conn.execute(
            """
            INSERT INTO quiz_answers
                (id, session_id, question_id, selected_index, is_correct, answered_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (id, session_id, question_id, selected_index, 1 if is_correct else 0, answered_at),
        )
        self._conn.commit()
        return {
            "id": id,
            "session_id": session_id,
            "question_id": question_id,
            "selected_index": selected_index,
            "is_correct": is_correct,
            "answered_at": answered_at,
        }

    def get_answers_for_session(self, session_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM quiz_answers WHERE session_id = ? ORDER BY answered_at",
            (session_id,),
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["is_correct"] = bool(d["is_correct"])
            result.append(d)
        return result
