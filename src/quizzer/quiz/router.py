import csv
import io
import json as _json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from quizzer.quiz.schemas import (
    AnswerRequest,
    AnswerResponse,
    DocumentSummary,
    ExportPayload,
    HealthResponse,
    ImportResult,
    PaginatedQuestions,
    QuestionAnswer,
    QuestionDetail,
    QuestionEditRequest,
    QuestionSummary,
    QuizAnswerRequest,
    QuizAnswerResponse,
    QuizFinishResponse,
    QuizResponse,
    QuizSessionResponse,
    StartQuizSessionRequest,
    StatusUpdateRequest,
    WeakCountResponse,
)
from quizzer.quiz.service import QuizService
from quizzer.quiz.session_service import QuizSessionService

router = APIRouter(prefix="/api/v1")


def _get_service() -> QuizService:
    # Imported here to avoid circular imports; app.py sets this on startup
    from quizzer.quiz.app import get_service
    return get_service()


def _get_quiz_session_service() -> QuizSessionService:
    from quizzer.quiz.app import get_quiz_session_service
    return get_quiz_session_service()


@router.get("/quiz/weak-count", response_model=WeakCountResponse)
def get_weak_count(
    difficulty: str | None = Query(None),
    document_id: list[str] | None = Query(default=None),
    svc: QuizSessionService = Depends(_get_quiz_session_service),
):
    count = svc.get_weak_count(difficulty, document_id or None)
    return WeakCountResponse(weak_count=count)


@router.post("/quiz/sessions", response_model=QuizSessionResponse, status_code=201)
def create_quiz_session(
    body: StartQuizSessionRequest,
    svc: QuizSessionService = Depends(_get_quiz_session_service),
):
    result = svc.create_session(
        body.n,
        body.difficulty,
        body.document_ids or None,
        body.tag,
        weak=body.weak,
    )
    questions = [
        QuestionSummary(
            id=q["id"],
            question=q["question"],
            options=q["options"],
            difficulty=q["difficulty"],
            source_document_id=q["source_document_id"],
            status=q["status"],
        )
        for q in result["questions"]
    ]
    return QuizSessionResponse(
        session_id=result["session_id"],
        questions=questions,
        started_at=result["started_at"],
    )


@router.post("/quiz/sessions/{session_id}/answers", response_model=QuizAnswerResponse)
def submit_quiz_answer(
    session_id: str,
    body: QuizAnswerRequest,
    svc: QuizSessionService = Depends(_get_quiz_session_service),
):
    result = svc.submit_answer(session_id, body.question_id, body.selected_index)
    if result is None:
        raise HTTPException(status_code=404, detail="Session or question not found")
    return QuizAnswerResponse(**result)


@router.post("/quiz/sessions/{session_id}/finish", response_model=QuizFinishResponse)
def finish_quiz_session(
    session_id: str,
    svc: QuizSessionService = Depends(_get_quiz_session_service),
):
    result = svc.finish_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return QuizFinishResponse(**result)


@router.get("/quiz/sessions/{session_id}", response_model=dict)
def get_quiz_session(
    session_id: str,
    svc: QuizSessionService = Depends(_get_quiz_session_service),
):
    result = svc.get_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.get("/questions", response_model=PaginatedQuestions)
def list_questions(
    difficulty: str | None = Query(None),
    status: str | None = Query(None),
    document_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    svc: QuizService = Depends(_get_service),
):
    items, total = svc.list_questions(
        difficulty=difficulty,
        status=status,
        document_id=document_id,
        limit=limit,
        offset=offset,
    )
    summaries = [
        QuestionSummary(
            id=q["id"],
            question=q["question"],
            options=q["options"],
            difficulty=q["difficulty"],
            source_document_id=q["source_document_id"],
            status=q["status"],
        )
        for q in items
    ]
    return PaginatedQuestions(items=summaries, total=total, limit=limit, offset=offset)


@router.get("/questions/export")
def export_questions(
    format: str = Query("json", pattern="^(json|csv)$"),
    status: str | None = Query(None),
    document_id: list[str] | None = Query(default=None),
    svc: QuizService = Depends(_get_service),
):
    data = svc.export_data(status, document_id or None)
    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "id", "question", "option_a", "option_b", "option_c", "option_d",
            "correct_index", "explanation", "difficulty", "status",
            "source_document_id", "document_title",
            "fingerprint", "model", "prompt_version", "created_at",
        ])
        writer.writeheader()
        doc_map = {d["id"]: d["title"] for d in data["documents"]}
        for q in data["questions"]:
            opts = q["options"]
            writer.writerow({
                "id": q["id"],
                "question": q["question"],
                "option_a": opts[0],
                "option_b": opts[1],
                "option_c": opts[2],
                "option_d": opts[3],
                "correct_index": q["correct_index"],
                "explanation": q["explanation"],
                "difficulty": q["difficulty"],
                "status": q["status"],
                "source_document_id": q["source_document_id"],
                "document_title": doc_map.get(q["source_document_id"], ""),
                "fingerprint": q["fingerprint"],
                "model": q["model"],
                "prompt_version": q["prompt_version"],
                "created_at": q["created_at"],
            })
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="quizzer-export.csv"'},
        )
    return StreamingResponse(
        iter([_json.dumps(data, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="quizzer-export.json"'},
    )


@router.post("/questions/import", response_model=ImportResult)
def import_questions(
    payload: ExportPayload,
    svc: QuizService = Depends(_get_service),
):
    result = svc.import_data(payload.model_dump())
    return ImportResult(**result)


@router.get("/questions/{question_id}/answer", response_model=QuestionAnswer)
def get_question_answer(
    question_id: str,
    svc: QuizService = Depends(_get_service),
):
    q = svc.get_question(question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return QuestionAnswer(
        id=q["id"],
        question=q["question"],
        options=q["options"],
        correct_index=q["correct_index"],
        explanation=q["explanation"],
        difficulty=q["difficulty"],
    )


@router.get("/questions/{question_id}", response_model=QuestionDetail)
def get_question(
    question_id: str,
    svc: QuizService = Depends(_get_service),
):
    q = svc.get_question(question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return QuestionDetail(
        id=q["id"],
        question=q["question"],
        options=q["options"],
        difficulty=q["difficulty"],
        source_document_id=q["source_document_id"],
        source_chunk_id=q["source_chunk_id"],
        status=q["status"],
        model=q["model"],
        prompt_version=q["prompt_version"],
        created_at=q["created_at"],
        times_answered=q.get("times_answered", 0),
        times_correct=q.get("times_correct", 0),
        hit_rate=q.get("hit_rate"),
    )


@router.post("/questions/{question_id}/answer", response_model=AnswerResponse)
def submit_answer(
    question_id: str,
    body: AnswerRequest,
    svc: QuizService = Depends(_get_service),
):
    result = svc.check_answer(question_id, body.selected_index)
    if result is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return AnswerResponse(**result)


@router.put("/questions/{question_id}", response_model=QuestionDetail)
def edit_question(
    question_id: str,
    body: QuestionEditRequest,
    svc: QuizService = Depends(_get_service),
):
    updated = svc.edit_question(
        question_id,
        question=body.question,
        options=body.options,
        correct_index=body.correct_index,
        explanation=body.explanation,
        difficulty=body.difficulty,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Question not found")
    q = svc.get_question(question_id)
    return QuestionDetail(**q)


@router.patch("/questions/{question_id}/status", response_model=dict)
def update_status(
    question_id: str,
    body: StatusUpdateRequest,
    svc: QuizService = Depends(_get_service),
):
    updated = svc.update_status(question_id, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"id": question_id, "status": body.status}


@router.get("/tags", response_model=list[str])
def list_tags(svc: QuizService = Depends(_get_service)):
    return svc.list_tags()


@router.get("/quiz", response_model=QuizResponse)
def get_quiz(
    n: int = Query(5, ge=1, le=50),
    difficulty: str | None = Query(None),
    document_id: list[str] | None = Query(default=None),
    tag: str | None = Query(None),
    svc: QuizService = Depends(_get_service),
):
    items = svc.get_quiz_sample(n, difficulty, document_id or None, tag)
    questions = [
        QuestionSummary(
            id=q["id"],
            question=q["question"],
            options=q["options"],
            difficulty=q["difficulty"],
            source_document_id=q["source_document_id"],
            status=q["status"],
        )
        for q in items
    ]
    return QuizResponse(questions=questions, requested=n, returned=len(questions))


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(svc: QuizService = Depends(_get_service)):
    docs = svc.list_documents()
    return [DocumentSummary(**d) for d in docs]


@router.get("/health", response_model=HealthResponse)
def health(svc: QuizService = Depends(_get_service)):
    result = svc.health()
    return HealthResponse(**result)
