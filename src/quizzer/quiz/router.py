from fastapi import APIRouter, Depends, HTTPException, Query

from quizzer.quiz.schemas import (
    AnswerRequest,
    AnswerResponse,
    DocumentSummary,
    HealthResponse,
    PaginatedQuestions,
    QuestionAnswer,
    QuestionDetail,
    QuestionEditRequest,
    QuestionSummary,
    QuizResponse,
    StatusUpdateRequest,
)
from quizzer.quiz.service import QuizService

router = APIRouter(prefix="/api/v1")


def _get_service() -> QuizService:
    # Imported here to avoid circular imports; app.py sets this on startup
    from quizzer.quiz.app import get_service
    return get_service()


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
    document_id: str | None = Query(None),
    tag: str | None = Query(None),
    svc: QuizService = Depends(_get_service),
):
    items = svc.get_quiz_sample(n, difficulty, document_id, tag)
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
