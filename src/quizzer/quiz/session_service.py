from datetime import datetime, timezone

from ulid import ULID

from quizzer.storage.question_repo import QuestionRepository
from quizzer.storage.session_repo import SessionRepository


class QuizSessionService:
    def __init__(
        self,
        session_repo: SessionRepository,
        question_repo: QuestionRepository,
    ) -> None:
        self._sessions = session_repo
        self._questions = question_repo

    def get_weak_count(
        self,
        difficulty: str | None = None,
        document_ids: list[str] | None = None,
    ) -> int:
        return self._questions.get_weak_count(difficulty, document_ids or None)

    def create_session(
        self,
        n: int,
        difficulty: str | None,
        document_ids: list[str] | None,
        tag: str | None,
        weak: bool = False,
    ) -> dict:
        if weak:
            questions = self._questions.get_weak_sample(
                n, difficulty, document_ids or None
            )
        else:
            questions = self._questions.get_random_sample(
                n, difficulty, document_ids or None, tag
            )
        session_id = str(ULID())
        started_at = datetime.now(timezone.utc).isoformat()
        self._sessions.create_session(
            id=session_id,
            question_count=len(questions),
            difficulty=difficulty,
            tag=tag,
            document_ids=document_ids or None,
            started_at=started_at,
        )
        return {
            "session_id": session_id,
            "questions": questions,
            "started_at": started_at,
        }

    def submit_answer(
        self,
        session_id: str,
        question_id: str,
        selected_index: int,
    ) -> dict | None:
        session = self._sessions.get_session(session_id)
        if session is None:
            return None

        q = self._questions.get_by_id(question_id)
        if q is None:
            return None

        correct = q["correct_index"] == selected_index
        self._sessions.add_answer(
            id=str(ULID()),
            session_id=session_id,
            question_id=question_id,
            selected_index=selected_index,
            is_correct=correct,
            answered_at=datetime.now(timezone.utc).isoformat(),
        )
        return {
            "correct": correct,
            "correct_index": q["correct_index"],
            "explanation": q["explanation"],
        }

    def finish_session(self, session_id: str) -> dict | None:
        session = self._sessions.get_session(session_id)
        if session is None:
            return None

        finished_at = datetime.now(timezone.utc).isoformat()
        self._sessions.finish_session(session_id, finished_at)

        answers = self._sessions.get_answers_for_session(session_id)
        n_answered = len(answers)
        n_correct = sum(1 for a in answers if a["is_correct"])
        n_wrong = n_answered - n_correct
        # Clamp: a client may answer the same question more than once, so
        # n_answered can exceed the question count — never report negative skips.
        n_skipped = max(0, session["question_count"] - n_answered)

        return {
            "session_id": session_id,
            "finished_at": finished_at,
            "n_answered": n_answered,
            "n_correct": n_correct,
            "n_wrong": n_wrong,
            "n_skipped": n_skipped,
        }

    def get_session(self, session_id: str) -> dict | None:
        session = self._sessions.get_session(session_id)
        if session is None:
            return None
        answers = self._sessions.get_answers_for_session(session_id)
        return {**session, "answers": answers}
