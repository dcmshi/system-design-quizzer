from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from quizzer.database import init_db, get_connection
from quizzer.generation.ollama_client import OllamaClient
from quizzer.quiz import deps
from quizzer.quiz.service import QuizService
from quizzer.quiz.session_service import QuizSessionService
from quizzer.srs.repository import SrsRepository
from quizzer.srs.service import SrsService
from quizzer.storage.document_repo import DocumentRepository
from quizzer.storage.question_repo import QuestionRepository
from quizzer.storage.session_repo import SessionRepository

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    conn = get_connection()
    deps._service = QuizService(
        question_repo=QuestionRepository(conn),
        document_repo=DocumentRepository(conn),
        ollama_client=OllamaClient(),
    )
    deps._srs_service = SrsService(
        srs_repo=SrsRepository(conn),
        question_repo=QuestionRepository(conn),
    )
    deps._quiz_session_service = QuizSessionService(
        session_repo=SessionRepository(conn),
        question_repo=QuestionRepository(conn),
    )
    yield
    # Cleanup (optional — process will exit anyway)
    deps._service = None
    deps._srs_service = None
    deps._quiz_session_service = None


def create_app() -> FastAPI:
    app = FastAPI(
        title="System Design Quizzer",
        version="0.1.0",
        lifespan=lifespan,
    )
    from quizzer.quiz.router import router
    from quizzer.srs.router import router as srs_router
    app.include_router(router)
    app.include_router(srs_router)
    if _STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
    return app


app = create_app()
