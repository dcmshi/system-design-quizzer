from fastapi import APIRouter, Depends, HTTPException, Query

from quizzer.quiz.schemas import QuestionSummary
from quizzer.srs.schemas import (
    SrsDueResponse,
    SrsFinishResponse,
    SrsReviewRequest,
    SrsReviewResponse,
    SrsSessionResponse,
    StartSessionRequest,
)
from quizzer.srs.service import SrsService

router = APIRouter(prefix="/api/v1/srs", tags=["srs"])


def _get_srs_service() -> SrsService:
    from quizzer.quiz.app import get_srs_service
    return get_srs_service()


@router.post("/sessions", response_model=SrsSessionResponse, status_code=201)
def start_session(
    body: StartSessionRequest,
    svc: SrsService = Depends(_get_srs_service),
):
    result = svc.create_session(body.n, document_id=body.document_id)
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
    return SrsSessionResponse(
        session_id=result["session_id"],
        questions=questions,
        started_at=result["started_at"],
    )


@router.post("/sessions/{session_id}/reviews", response_model=SrsReviewResponse)
def submit_review(
    session_id: str,
    body: SrsReviewRequest,
    svc: SrsService = Depends(_get_srs_service),
):
    result = svc.submit_review(session_id, body.question_id, body.selected_index)
    if result is None:
        raise HTTPException(status_code=404, detail="Session or question not found")
    return SrsReviewResponse(**result)


@router.post("/sessions/{session_id}/finish", response_model=SrsFinishResponse)
def finish_session(
    session_id: str,
    svc: SrsService = Depends(_get_srs_service),
):
    result = svc.finish_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SrsFinishResponse(**result)


@router.get("/sessions/{session_id}", response_model=dict)
def get_session(
    session_id: str,
    svc: SrsService = Depends(_get_srs_service),
):
    result = svc.get_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.get("/due", response_model=SrsDueResponse)
def get_due(
    document_id: str | None = Query(None),
    svc: SrsService = Depends(_get_srs_service),
):
    return SrsDueResponse(**svc.get_due_info(document_id=document_id))
