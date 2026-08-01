import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from quizzer.database import init_db
from quizzer.generation.factory import create_llm_client
from quizzer.quiz import deps
from quizzer.quiz.service import QuizService
from quizzer.quiz.session_service import QuizSessionService
from quizzer.srs.repository import SrsRepository
from quizzer.srs.service import SrsService
from quizzer.storage.document_repo import DocumentRepository
from quizzer.storage.question_repo import QuestionRepository
from quizzer.storage.session_repo import SessionRepository

_STATIC_DIR = Path(__file__).parent / "static"

# Some Windows installs map .js to application/javascript, which Starlette does
# not tag with a charset; the page scripts contain non-ASCII text.
mimetypes.add_type("text/javascript", ".js")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Repos take no explicit connection: each resolves a per-thread connection
    # at call time, so these shared singletons are safe under concurrent requests.
    deps._service = QuizService(
        question_repo=QuestionRepository(),
        document_repo=DocumentRepository(),
        llm_client=create_llm_client(),
    )
    deps._srs_service = SrsService(
        srs_repo=SrsRepository(),
        question_repo=QuestionRepository(),
    )
    deps._quiz_session_service = QuizSessionService(
        session_repo=SessionRepository(),
        question_repo=QuestionRepository(),
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
