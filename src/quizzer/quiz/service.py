import re as _re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal

from quizzer.generation.base import LLMClient
from quizzer.generation.factory import create_llm_client
from quizzer.ingestion.models import Chunk, Document
from quizzer.storage.document_repo import DocumentRepository
from quizzer.storage.question_repo import QuestionRepository

_STOP = frozenset({
    'the', 'and', 'for', 'that', 'this', 'with', 'are', 'was', 'were',
    'has', 'have', 'had', 'not', 'but', 'from', 'they', 'will', 'when',
    'which', 'what', 'how', 'why', 'can', 'its', 'their', 'each', 'about',
    'you', 'your', 'does', 'used', 'use', 'using', 'would', 'should',
})


def _tokenize(text: str) -> frozenset[str]:
    tokens = _re.sub(r'[^\w\s]', '', text.lower()).split()
    return frozenset(t for t in tokens if len(t) >= 3 and t not in _STOP)


def _jaccard(a: frozenset, b: frozenset) -> float:
    union = len(a | b)
    return len(a & b) / union if union else 0.0


class QuizService:
    def __init__(
        self,
        question_repo: QuestionRepository,
        document_repo: DocumentRepository,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.questions = question_repo
        self.documents = document_repo
        self._llm = llm_client or create_llm_client()

    def list_questions(
        self,
        difficulty: str | None = None,
        status: str | None = None,
        document_id: str | None = None,
        q: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        items = self.questions.list_questions(
            difficulty=difficulty,
            status=status,
            document_id=document_id,
            q=q,
            model=model,
            prompt_version=prompt_version,
            limit=limit,
            offset=offset,
        )
        total = self.questions.count_questions(
            difficulty=difficulty,
            status=status,
            document_id=document_id,
            q=q,
            model=model,
            prompt_version=prompt_version,
        )
        return items, total

    def list_models(self) -> list[str]:
        return self.questions.list_distinct_models()

    def list_prompt_versions(self) -> list[str]:
        return self.questions.list_distinct_prompt_versions()

    def get_question(self, question_id: str) -> dict | None:
        q = self.questions.get_by_id(question_id)
        if q is None:
            return None
        return {**q, **self.questions.get_hit_rate(question_id)}

    def get_quiz_sample(
        self,
        n: int,
        difficulty: str | None = None,
        document_ids: list[str] | None = None,
        tag: str | None = None,
    ) -> list[dict]:
        return self.questions.get_random_sample(n, difficulty, document_ids, tag)

    def list_tags(self) -> list[str]:
        return self.documents.list_all_tags()

    def check_answer(self, question_id: str, selected_index: int) -> dict | None:
        q = self.questions.get_by_id(question_id)
        if q is None:
            return None
        correct = q["correct_index"] == selected_index
        return {
            "correct": correct,
            "correct_index": q["correct_index"],
            "explanation": q["explanation"],
        }

    def edit_question(
        self,
        question_id: str,
        *,
        question: str,
        options: list[str],
        correct_index: int,
        explanation: str,
        difficulty: str,
    ) -> bool:
        updated = self.questions.update_question(
            question_id,
            question=question,
            options=options,
            correct_index=correct_index,
            explanation=explanation,
            difficulty=difficulty,
        )
        if updated:
            self.questions.update_status(question_id, "edited")
        return updated

    def update_status(
        self, question_id: str, status: Literal["approved", "edited", "rejected"]
    ) -> bool:
        return self.questions.update_status(question_id, status)

    def bulk_update_status(self, ids: list[str], status: str) -> int:
        return self.questions.bulk_update_status(ids, status)

    def delete_question(self, question_id: str) -> bool:
        return self.questions.delete(question_id)

    def get_document_by_id(self, document_id: str) -> dict | None:
        docs = self.documents.get_by_ids([document_id])
        if not docs:
            return None
        doc = docs[0]
        return {"id": doc.id, "title": doc.title, "source_path": doc.source_path}

    def list_documents(self) -> list[dict]:
        docs = self.documents.list_all()
        counts = self.questions.count_by_documents()
        chunk_stats = self.documents.get_chunk_stats_by_document()
        return [
            {
                "id": doc.id,
                "title": doc.title,
                "source": doc.source,
                "tags": doc.tags,
                "source_path": doc.source_path,
                "created_at": doc.created_at,
                "question_count": counts.get(doc.id, 0),
                "chunk_count": chunk_stats.get(doc.id, {}).get("chunk_count", 0),
                "word_count": chunk_stats.get(doc.id, {}).get("total_words", 0),
            }
            for doc in docs
        ]

    def export_data(
        self,
        status: str | None = None,
        document_ids: list[str] | None = None,
    ) -> dict:
        questions = self.questions.list_all_for_export(status, document_ids)
        doc_ids = list({q["source_document_id"] for q in questions})
        documents = self.documents.get_by_ids(doc_ids)
        return {
            "version": "1",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "documents": [
                {
                    "id": d.id,
                    "title": d.title,
                    "source": d.source,
                    "content": d.content,
                    "tags": d.tags,
                    "source_path": d.source_path,
                    "created_at": d.created_at,
                }
                for d in documents
            ],
            "questions": questions,
        }

    def import_data(self, payload: dict) -> dict:
        imported = skipped = 0
        errors: list[str] = []
        for doc_data in payload.get("documents", []):
            self.documents.upsert(Document(**doc_data))
        existing_fps = self.questions.get_all_fingerprints()
        for q in payload.get("questions", []):
            try:
                self.documents.upsert_chunk(Chunk(
                    id=q["source_chunk_id"],
                    document_id=q["source_document_id"],
                    content="",
                    word_count=0,
                    chunk_index=0,
                    created_at=q["created_at"],
                ))
                if q["fingerprint"] in existing_fps:
                    skipped += 1
                    continue
                self.questions.insert(
                    id=q["id"],
                    question=q["question"],
                    options=q["options"],
                    correct_index=q["correct_index"],
                    explanation=q["explanation"],
                    difficulty=q["difficulty"],
                    source_document_id=q["source_document_id"],
                    source_chunk_id=q["source_chunk_id"],
                    fingerprint=q["fingerprint"],
                    model=q["model"],
                    prompt_version=q["prompt_version"],
                    created_at=q["created_at"],
                    status=q["status"],
                )
                existing_fps.add(q["fingerprint"])
                imported += 1
            except Exception as e:
                errors.append(f"Question {q.get('id', '?')}: {e}")
        return {"imported": imported, "skipped": skipped, "errors": errors}

    def find_near_duplicates(
        self,
        threshold: float = 0.5,
        document_ids: list[str] | None = None,
    ) -> list[dict]:
        rows = self.questions.get_texts_for_similarity(document_ids)
        tokenized = [(r["id"], r["question"], _tokenize(r["question"])) for r in rows]

        # Inverted index: token -> question indices. Two questions can only have
        # non-zero Jaccard similarity if they share a token, so we score just
        # those candidate pairs instead of every O(n^2) pair.
        postings: dict[str, list[int]] = defaultdict(list)
        for idx, (_id, _q, toks) in enumerate(tokenized):
            for tok in toks:
                postings[tok].append(idx)

        candidates: set[tuple[int, int]] = set()
        for indices in postings.values():
            for a in range(len(indices)):
                for b in range(a + 1, len(indices)):
                    candidates.add((indices[a], indices[b]))

        pairs: list[dict] = []
        for i, j in candidates:
            id_a, q_a, tok_a = tokenized[i]
            id_b, q_b, tok_b = tokenized[j]
            sim = _jaccard(tok_a, tok_b)
            if sim >= threshold:
                pairs.append({
                    "id_a": id_a,
                    "question_a": q_a,
                    "id_b": id_b,
                    "question_b": q_b,
                    "similarity": round(sim, 3),
                })
        # Deterministic ordering: strongest first, then by id for ties.
        pairs.sort(key=lambda p: (-p["similarity"], p["id_a"], p["id_b"]))
        return pairs

    def health(self) -> dict:
        db_ok = True
        try:
            self.questions.get_all_fingerprints()
        except Exception:
            db_ok = False

        llm_ok = self._llm.health_check()

        return {
            "status": "ok" if (db_ok and llm_ok) else "degraded",
            "db": "connected" if db_ok else "error",
            "llm": "connected" if llm_ok else "unreachable",
        }
