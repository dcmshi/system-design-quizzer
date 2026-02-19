from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from quizzer.database import init_db, get_connection
from quizzer.generation.ollama_client import OllamaClient
from quizzer.quiz.service import QuizService
from quizzer.storage.document_repo import DocumentRepository
from quizzer.storage.question_repo import QuestionRepository

_STATIC_DIR = Path(__file__).parent / "static"

_service: QuizService | None = None


def get_service() -> QuizService:
    if _service is None:
        raise RuntimeError("Service not initialized — lifespan not run?")
    return _service


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _service
    init_db()
    conn = get_connection()
    _service = QuizService(
        question_repo=QuestionRepository(conn),
        document_repo=DocumentRepository(conn),
        ollama_client=OllamaClient(),
    )
    yield
    # Cleanup (optional — process will exit anyway)
    _service = None


def create_app() -> FastAPI:
    app = FastAPI(
        title="System Design Quizzer",
        version="0.1.0",
        lifespan=lifespan,
    )
    from quizzer.quiz.router import router
    app.include_router(router)
    if _STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
    return app


app = create_app()
