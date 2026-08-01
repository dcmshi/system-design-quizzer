from datetime import datetime, timezone

from ulid import ULID

from quizzer.srs.algorithm import CardState, apply_review, initial_state, utc_today
from quizzer.srs.repository import SrsRepository
from quizzer.storage.question_repo import QuestionRepository


class SrsService:
    def __init__(
        self,
        srs_repo: SrsRepository,
        question_repo: QuestionRepository,
    ) -> None:
        self._srs = srs_repo
        self._questions = question_repo

    def create_session(
        self, n: int, document_id: str | None = None
    ) -> dict:
        questions = self._srs.get_due_questions(n, document_id=document_id)
        session_id = str(ULID())
        started_at = datetime.now(timezone.utc).isoformat()
        self._srs.create_session(
            id=session_id,
            question_count=len(questions),
            started_at=started_at,
            question_ids=[q["id"] for q in questions],
        )
        return {
            "session_id": session_id,
            "questions": questions,
            "started_at": started_at,
        }

    def submit_review(
        self,
        session_id: str,
        question_id: str,
        selected_index: int,
    ) -> dict | None:
        session = self._srs.get_session(session_id)
        if session is None:
            return None

        # Reject reviews for questions that weren't dealt into the session
        # (legacy sessions have no question_ids — accept any, as before).
        member_ids = session.get("question_ids")
        if member_ids is not None and question_id not in member_ids:
            return None

        q = self._questions.get_by_id(question_id)
        if q is None:
            return None

        correct = q["correct_index"] == selected_index
        rating = 5 if correct else 0

        # Load or initialise card state
        card = self._srs.get_card(question_id)
        now = datetime.now(timezone.utc)
        today = utc_today()

        if card is None:
            state, _ = initial_state(today)
            created_at = now.isoformat()
        else:
            state = CardState(
                ease_factor=card["ease_factor"],
                interval_days=card["interval_days"],
                repetitions=card["repetitions"],
            )
            created_at = card["created_at"]

        new_state, next_due = apply_review(state, rating, today)

        self._srs.upsert_card(
            question_id=question_id,
            ease_factor=new_state.ease_factor,
            interval_days=new_state.interval_days,
            repetitions=new_state.repetitions,
            due_date=next_due.isoformat(),
            last_reviewed=now.isoformat(),
            created_at=created_at,
        )

        self._srs.add_review(
            id=str(ULID()),
            session_id=session_id,
            question_id=question_id,
            rating=rating,
            was_correct=correct,
            ease_factor_after=new_state.ease_factor,
            interval_after=new_state.interval_days,
            reviewed_at=now.isoformat(),
        )

        return {
            "correct": correct,
            "correct_index": q["correct_index"],
            "explanation": q["explanation"],
            "next_due": next_due.isoformat(),
            "interval_days": new_state.interval_days,
            "ease_factor": round(new_state.ease_factor, 4),
        }

    def finish_session(self, session_id: str) -> dict | None:
        session = self._srs.get_session(session_id)
        if session is None:
            return None

        finished_at = datetime.now(timezone.utc).isoformat()
        self._srs.finish_session(session_id, finished_at)

        reviews = self._srs.get_reviews_for_session(session_id)
        n_correct = sum(1 for r in reviews if r["was_correct"])
        return {
            "session_id": session_id,
            "finished_at": finished_at,
            "n_reviewed": len(reviews),
            "n_correct": n_correct,
            "n_wrong": len(reviews) - n_correct,
        }

    def get_due_info(self, document_id: str | None = None) -> dict:
        counts = self._srs.due_count(document_id=document_id)
        total = counts["due_count"] + counts["new_count"]
        return {**counts, "total_actionable": total}

    def get_due_info_by_document(self) -> list[dict]:
        return [
            {
                "document_id": document_id,
                **counts,
                "total_actionable": counts["due_count"] + counts["new_count"],
            }
            for document_id, counts in self._srs.due_counts_by_document().items()
        ]

    def get_session(self, session_id: str) -> dict | None:
        session = self._srs.get_session(session_id)
        if session is None:
            return None
        reviews = self._srs.get_reviews_for_session(session_id)
        return {**session, "reviews": reviews}
