import json
import sqlite3
from datetime import date

from quizzer.database import get_connection


class SrsRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    # ------------------------------------------------------------------
    # srs_cards
    # ------------------------------------------------------------------

    def get_card(self, question_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM srs_cards WHERE question_id = ?", (question_id,)
        ).fetchone()
        return dict(row) if row else None

    def upsert_card(
        self,
        *,
        question_id: str,
        ease_factor: float,
        interval_days: int,
        repetitions: int,
        due_date: str,
        last_reviewed: str,
        created_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO srs_cards
                (question_id, ease_factor, interval_days, repetitions,
                 due_date, last_reviewed, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(question_id) DO UPDATE SET
                ease_factor   = excluded.ease_factor,
                interval_days = excluded.interval_days,
                repetitions   = excluded.repetitions,
                due_date      = excluded.due_date,
                last_reviewed = excluded.last_reviewed
            """,
            (question_id, ease_factor, interval_days, repetitions,
             due_date, last_reviewed, created_at),
        )
        self._conn.commit()

    def get_due_questions(
        self,
        n: int,
        document_id: str | None = None,
        today: str | None = None,
    ) -> list[dict]:
        """Return up to *n* questions that are due or new, ordered due-first."""
        cutoff = today or date.today().isoformat()
        # Build params in the exact order the placeholders appear in the SQL:
        # 1) document_id (WHERE), 2) cutoff (due-date AND), 3) n (LIMIT).
        filters = ["q.status != 'rejected'"]
        params: list = []
        if document_id:
            filters.append("q.source_document_id = ?")
            params.append(document_id)
        where = "WHERE " + " AND ".join(filters)
        params.append(cutoff)
        params.append(n)
        rows = self._conn.execute(
            f"""
            SELECT q.*, c.ease_factor, c.interval_days, c.repetitions,
                   c.due_date, c.last_reviewed
            FROM questions q
            LEFT JOIN srs_cards c ON q.id = c.question_id
            {where}
              AND (c.question_id IS NULL OR c.due_date <= ?)
            ORDER BY
                CASE WHEN c.question_id IS NOT NULL THEN 0 ELSE 1 END,
                c.due_date ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def due_count(self, document_id: str | None = None, today: str | None = None) -> dict:
        cutoff = today or date.today().isoformat()
        params_due: list = [cutoff]
        params_new: list = []
        doc_filter = ""
        if document_id:
            doc_filter = "AND q.source_document_id = ?"
            params_due.append(document_id)
            params_new.append(document_id)

        due_row = self._conn.execute(
            f"""
            SELECT COUNT(*) AS cnt FROM questions q
            JOIN srs_cards c ON q.id = c.question_id
            WHERE c.due_date <= ? AND q.status != 'rejected' {doc_filter}
            """,
            params_due,
        ).fetchone()

        new_row = self._conn.execute(
            f"""
            SELECT COUNT(*) AS cnt FROM questions q
            LEFT JOIN srs_cards c ON q.id = c.question_id
            WHERE c.question_id IS NULL AND q.status != 'rejected' {doc_filter}
            """,
            params_new,
        ).fetchone()

        return {
            "due_count": due_row["cnt"] if due_row else 0,
            "new_count": new_row["cnt"] if new_row else 0,
        }

    # ------------------------------------------------------------------
    # srs_sessions
    # ------------------------------------------------------------------

    def create_session(self, *, id: str, question_count: int, started_at: str) -> dict:
        self._conn.execute(
            "INSERT INTO srs_sessions (id, question_count, started_at) VALUES (?, ?, ?)",
            (id, question_count, started_at),
        )
        self._conn.commit()
        return {"id": id, "question_count": question_count, "started_at": started_at, "finished_at": None}

    def finish_session(self, session_id: str, finished_at: str) -> bool:
        cur = self._conn.execute(
            "UPDATE srs_sessions SET finished_at = ? WHERE id = ?",
            (finished_at, session_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_session(self, session_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM srs_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # srs_reviews
    # ------------------------------------------------------------------

    def add_review(
        self,
        *,
        id: str,
        session_id: str,
        question_id: str,
        rating: int,
        was_correct: bool,
        ease_factor_after: float,
        interval_after: int,
        reviewed_at: str,
    ) -> dict:
        self._conn.execute(
            """
            INSERT INTO srs_reviews
                (id, session_id, question_id, rating, was_correct,
                 ease_factor_after, interval_after, reviewed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (id, session_id, question_id, rating, int(was_correct),
             ease_factor_after, interval_after, reviewed_at),
        )
        self._conn.commit()
        return {
            "id": id,
            "session_id": session_id,
            "question_id": question_id,
            "rating": rating,
            "was_correct": was_correct,
            "ease_factor_after": ease_factor_after,
            "interval_after": interval_after,
            "reviewed_at": reviewed_at,
        }

    def get_reviews_for_session(self, session_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM srs_reviews WHERE session_id = ? ORDER BY reviewed_at",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row) -> dict:
        d = dict(row)
        if "options" in d and isinstance(d["options"], str):
            d["options"] = json.loads(d["options"])
        return d
