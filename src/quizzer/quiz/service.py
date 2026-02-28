from datetime import datetime, timezone
from typing import Literal

from quizzer.generation.ollama_client import OllamaClient
from quizzer.ingestion.models import Chunk, Document
from quizzer.storage.document_repo import DocumentRepository
from quizzer.storage.question_repo import QuestionRepository


class QuizService:
    def __init__(
        self,
        question_repo: QuestionRepository,
        document_repo: DocumentRepository,
        ollama_client: OllamaClient | None = None,
    ) -> None:
        self.questions = question_repo
        self.documents = document_repo
        self._ollama = ollama_client or OllamaClient()

    def list_questions(
        self,
        difficulty: str | None = None,
        status: str | None = None,
        document_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        items = self.questions.list_questions(
            difficulty=difficulty,
            status=status,
            document_id=document_id,
            limit=limit,
            offset=offset,
        )
        total = self.questions.count_questions(
            difficulty=difficulty,
            status=status,
            document_id=document_id,
        )
        return items, total

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

    def list_documents(self) -> list[dict]:
        docs = self.documents.list_all()
        counts = self.questions.count_by_documents()
        return [
            {
                "id": doc.id,
                "title": doc.title,
                "source": doc.source,
                "tags": doc.tags,
                "source_path": doc.source_path,
                "created_at": doc.created_at,
                "question_count": counts.get(doc.id, 0),
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

    def health(self) -> dict:
        db_ok = True
        try:
            self.questions.get_all_fingerprints()
        except Exception:
            db_ok = False

        ollama_ok = self._ollama.health_check()

        return {
            "status": "ok" if (db_ok and ollama_ok) else "degraded",
            "db": "connected" if db_ok else "error",
            "ollama": "connected" if ollama_ok else "unreachable",
        }
