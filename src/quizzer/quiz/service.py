import json
from typing import Literal

from quizzer.generation.ollama_client import OllamaClient
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
        # Simple total count (separate query would be needed for true pagination)
        all_items = self.questions.list_questions(
            difficulty=difficulty,
            status=status,
            document_id=document_id,
            limit=10_000,
            offset=0,
        )
        return items, len(all_items)

    def get_question(self, question_id: str) -> dict | None:
        return self.questions.get_by_id(question_id)

    def get_quiz_sample(self, n: int, difficulty: str | None = None) -> list[dict]:
        return self.questions.get_random_sample(n, difficulty)

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

    def update_status(
        self, question_id: str, status: Literal["approved", "edited"]
    ) -> bool:
        return self.questions.update_status(question_id, status)

    def list_documents(self) -> list[dict]:
        docs = self.documents.list_all()
        result = []
        for doc in docs:
            count = self.questions.count_by_document(doc.id)
            result.append({
                "id": doc.id,
                "title": doc.title,
                "source": doc.source,
                "tags": doc.tags,
                "source_path": doc.source_path,
                "created_at": doc.created_at,
                "question_count": count,
            })
        return result

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
