from __future__ import annotations

from quizzer.quiz.service import QuizService
from quizzer.quiz.session_service import QuizSessionService
from quizzer.srs.service import SrsService

_service: QuizService | None = None
_srs_service: SrsService | None = None
_quiz_session_service: QuizSessionService | None = None


def get_service() -> QuizService:
    if _service is None:
        raise RuntimeError("Service not initialized — lifespan not run?")
    return _service


def get_srs_service() -> SrsService:
    if _srs_service is None:
        raise RuntimeError("SRS service not initialized — lifespan not run?")
    return _srs_service


def get_quiz_session_service() -> QuizSessionService:
    if _quiz_session_service is None:
        raise RuntimeError("QuizSessionService not initialized — lifespan not run?")
    return _quiz_session_service
