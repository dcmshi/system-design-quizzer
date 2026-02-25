from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from quizzer.database import init_db, get_connection
from quizzer.generation.ollama_client import OllamaClient
from quizzer.quiz.service import QuizService
from quizzer.srs.repository import SrsRepository
from quizzer.srs.service import SrsService
from quizzer.storage.document_repo import DocumentRepository
from quizzer.storage.question_repo import QuestionRepository

_STATIC_DIR = Path(__file__).parent / "static"

_service: QuizService | None = None
_srs_service: SrsService | None = None


def get_service() -> QuizService:
    if _service is None:
        raise RuntimeError("Service not initialized — lifespan not run?")
    return _service


def get_srs_service() -> SrsService:
    if _srs_service is None:
        raise RuntimeError("SRS service not initialized — lifespan not run?")
    return _srs_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _service, _srs_service
    init_db()
    conn = get_connection()
    _service = QuizService(
        question_repo=QuestionRepository(conn),
        document_repo=DocumentRepository(conn),
        ollama_client=OllamaClient(),
    )
    _srs_service = SrsService(
        srs_repo=SrsRepository(conn),
        question_repo=QuestionRepository(conn),
    )
    yield
    # Cleanup (optional — process will exit anyway)
    _service = None
    _srs_service = None


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
