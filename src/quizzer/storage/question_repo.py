import json
import random as _random
import sqlite3
from typing import Literal

from quizzer.database import get_shared_connection


class QuestionRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        # An explicit connection (tests) is used as-is; otherwise resolve a
        # per-thread connection lazily so the shared app services are thread-safe.
        self._explicit_conn = conn

    @property
    def _conn(self) -> sqlite3.Connection:
        return self._explicit_conn if self._explicit_conn is not None else get_shared_connection()

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
        q: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
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
        if model:
            filters.append("model = ?")
            params.append(model)
        if prompt_version:
            filters.append("prompt_version = ?")
            params.append(prompt_version)
        search_clause, search_params = self._search_filter(q)
        if search_clause:
            filters.append(search_clause)
            params.extend(search_params)

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

    def bulk_update_status(self, ids: list[str], status: str) -> int:
        if not ids:
            return 0
        placeholders = ",".join(["?"] * len(ids))
        cur = self._conn.execute(
            f"UPDATE questions SET status = ? WHERE id IN ({placeholders})",
            [status, *ids],
        )
        self._conn.commit()
        return cur.rowcount

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

    @staticmethod
    def _search_filter(q: str | None) -> tuple[str, list]:
        if q and q.strip():
            # Escape LIKE wildcards so a literal % or _ in the query is matched
            # literally rather than acting as a pattern.
            escaped = (
                q.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            term = f"%{escaped}%"
            return (
                "(LOWER(question) LIKE LOWER(?) ESCAPE '\\' "
                "OR LOWER(explanation) LIKE LOWER(?) ESCAPE '\\')",
                [term, term],
            )
        return ("", [])

    @staticmethod
    def _difficulty_filter(difficulty: str | None, alias: str = "") -> tuple[str, list]:
        if difficulty:
            prefix = f"{alias}." if alias else ""
            return (f"{prefix}difficulty = ?", [difficulty])
        return ("", [])

    @staticmethod
    def _document_ids_filter(document_ids: list[str] | None, alias: str = "") -> tuple[str, list]:
        if document_ids:
            prefix = f"{alias}." if alias else ""
            placeholders = ",".join(["?"] * len(document_ids))
            return (f"{prefix}source_document_id IN ({placeholders})", list(document_ids))
        return ("", [])

    def get_random_sample(
        self,
        n: int,
        difficulty: str | None = None,
        document_ids: list[str] | None = None,
        tag: str | None = None,
    ) -> list[dict]:
        filters: list[str] = ["q.status != 'rejected'"]
        params: list = []

        diff_clause, diff_params = self._difficulty_filter(difficulty, "q")
        if diff_clause:
            filters.append(diff_clause)
            params.extend(diff_params)

        doc_clause, doc_params = self._document_ids_filter(document_ids, "q")
        if doc_clause:
            filters.append(doc_clause)
            params.extend(doc_params)

        if tag:
            filters.append("EXISTS (SELECT 1 FROM json_each(d.tags) WHERE value = ?)")
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

    def list_all_for_export(
        self,
        status: str | None = None,
        document_ids: list[str] | None = None,
    ) -> list[dict]:
        # Rejected questions are excluded by default, but an explicit status
        # filter (including 'rejected') takes precedence.
        filters: list[str] = []
        params: list = []
        if status:
            filters.append("status = ?")
            params.append(status)
        else:
            filters.append("status != 'rejected'")
        doc_clause, doc_params = self._document_ids_filter(document_ids)
        if doc_clause:
            filters.append(doc_clause)
            params.extend(doc_params)
        where = "WHERE " + " AND ".join(filters)
        rows = self._conn.execute(
            f"SELECT * FROM questions {where} ORDER BY created_at", params
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def _weak_filters(
        self,
        difficulty: str | None,
        document_ids: list[str] | None,
    ) -> tuple[str, list]:
        filters: list[str] = ["q.status != 'rejected'"]
        params: list = []

        diff_clause, diff_params = self._difficulty_filter(difficulty, "q")
        if diff_clause:
            filters.append(diff_clause)
            params.extend(diff_params)

        doc_clause, doc_params = self._document_ids_filter(document_ids, "q")
        if doc_clause:
            filters.append(doc_clause)
            params.extend(doc_params)

        return "WHERE " + " AND ".join(filters), params

    _WEAK_CTE = """
        WITH combined AS (
            SELECT question_id, is_correct  AS correct FROM quiz_answers
            UNION ALL
            SELECT question_id, was_correct AS correct FROM srs_reviews
        ),
        hit_rates AS (
            SELECT question_id,
                   COUNT(*)                            AS times_answered,
                   SUM(correct)                        AS times_correct,
                   CAST(SUM(correct) AS REAL) / COUNT(*) AS hit_rate
            FROM combined
            GROUP BY question_id
        )
    """

    def get_weak_sample(
        self,
        n: int,
        difficulty: str | None = None,
        document_ids: list[str] | None = None,
    ) -> list[dict]:
        """Return up to n questions from the bottom-quartile by hit rate."""
        where, params = self._weak_filters(difficulty, document_ids)
        rows = self._conn.execute(
            f"{self._WEAK_CTE}"
            f"SELECT q.* FROM questions q "
            f"JOIN hit_rates h ON q.id = h.question_id "
            f"{where} ORDER BY h.hit_rate ASC",
            params,
        ).fetchall()
        all_q = [self._row_to_dict(r) for r in rows]
        if not all_q:
            return []
        cutoff = max(1, len(all_q) // 4)
        pool = all_q[:cutoff]
        _random.shuffle(pool)
        return pool[:n]

    def get_weak_count(
        self,
        difficulty: str | None = None,
        document_ids: list[str] | None = None,
    ) -> int:
        """Return the size of the bottom-quartile pool (0 if no history)."""
        where, params = self._weak_filters(difficulty, document_ids)
        row = self._conn.execute(
            f"{self._WEAK_CTE}"
            f"SELECT COUNT(*) AS total FROM questions q "
            f"JOIN hit_rates h ON q.id = h.question_id "
            f"{where}",
            params,
        ).fetchone()
        total = row["total"] if row else 0
        return max(1, total // 4) if total > 0 else 0

    def get_hit_rate(self, question_id: str) -> dict:
        """Return answer counts across both quiz_answers and srs_reviews."""
        row = self._conn.execute(
            """
            SELECT
                COALESCE(SUM(cnt), 0)     AS times_answered,
                COALESCE(SUM(correct), 0) AS times_correct
            FROM (
                SELECT COUNT(*)        AS cnt,
                       SUM(is_correct) AS correct
                FROM quiz_answers
                WHERE question_id = ?
                UNION ALL
                SELECT COUNT(*)         AS cnt,
                       SUM(was_correct) AS correct
                FROM srs_reviews
                WHERE question_id = ?
            )
            """,
            (question_id, question_id),
        ).fetchone()
        times_answered = row["times_answered"] if row else 0
        times_correct  = row["times_correct"]  if row else 0
        hit_rate = (times_correct / times_answered) if times_answered > 0 else None
        return {
            "times_answered": times_answered,
            "times_correct":  times_correct,
            "hit_rate":       hit_rate,
        }

    def count_questions(
        self,
        *,
        difficulty: str | None = None,
        status: str | None = None,
        document_id: str | None = None,
        q: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
    ) -> int:
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
        if model:
            filters.append("model = ?")
            params.append(model)
        if prompt_version:
            filters.append("prompt_version = ?")
            params.append(prompt_version)
        search_clause, search_params = self._search_filter(q)
        if search_clause:
            filters.append(search_clause)
            params.extend(search_params)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        row = self._conn.execute(
            f"SELECT COUNT(*) as cnt FROM questions {where}", params
        ).fetchone()
        return row["cnt"] if row else 0

    def list_distinct_models(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT model FROM questions WHERE model != '' ORDER BY model"
        ).fetchall()
        return [r["model"] for r in rows]

    def list_distinct_prompt_versions(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT prompt_version FROM questions WHERE prompt_version != '' ORDER BY prompt_version"
        ).fetchall()
        return [r["prompt_version"] for r in rows]

    def get_texts_for_similarity(self, document_ids: list[str] | None = None) -> list[dict]:
        """Return {id, question} for all non-rejected questions (optionally scoped to documents)."""
        filters: list[str] = ["status != 'rejected'"]
        params: list = []
        doc_clause, doc_params = self._document_ids_filter(document_ids)
        if doc_clause:
            filters.append(doc_clause)
            params.extend(doc_params)
        where = "WHERE " + " AND ".join(filters)
        rows = self._conn.execute(
            f"SELECT id, question FROM questions {where}", params
        ).fetchall()
        return [{"id": r["id"], "question": r["question"]} for r in rows]

    def count_by_documents(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT source_document_id, COUNT(*) as cnt FROM questions "
            "WHERE status != 'rejected' GROUP BY source_document_id"
        ).fetchall()
        return {r["source_document_id"]: r["cnt"] for r in rows}

    def count_by_document(self, document_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM questions "
            "WHERE source_document_id = ? AND status != 'rejected'",
            (document_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def delete(self, question_id: str) -> bool:
        # srs_reviews and quiz_answers have no CASCADE so delete them first
        self._conn.execute("DELETE FROM srs_reviews WHERE question_id = ?", (question_id,))
        self._conn.execute("DELETE FROM quiz_answers WHERE question_id = ?", (question_id,))
        cur = self._conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        self._conn.commit()
        return cur.rowcount > 0

    @staticmethod
    def _row_to_dict(row) -> dict:
        d = dict(row)
        d["options"] = json.loads(d["options"])
        return d
