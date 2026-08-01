from fastapi import APIRouter, Depends, HTTPException, Query

from quizzer.quiz.schemas import QuestionSummary
from quizzer.srs.schemas import (
    SrsDocumentDue,
    SrsDueResponse,
    SrsFinishResponse,
    SrsReviewRequest,
    SrsReviewResponse,
    SrsSessionDetail,
    SrsSessionResponse,
    StartSessionRequest,
)
from quizzer.quiz import deps
from quizzer.srs.service import SrsService

router = APIRouter(prefix="/api/v1/srs", tags=["srs"])


def _get_srs_service() -> SrsService:
    return deps.get_srs_service()


@router.post("/sessions", response_model=SrsSessionResponse, status_code=201)
def start_session(
    body: StartSessionRequest,
    svc: SrsService = Depends(_get_srs_service),
):
    result = svc.create_session(body.n, document_ids=body.document_ids or None)
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


@router.get("/sessions/{session_id}", response_model=SrsSessionDetail)
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
    document_id: list[str] | None = Query(default=None),
    svc: SrsService = Depends(_get_srs_service),
):
    return SrsDueResponse(**svc.get_due_info(document_ids=document_id or None))


@router.get("/due/by-document", response_model=list[SrsDocumentDue])
def get_due_by_document(svc: SrsService = Depends(_get_srs_service)):
    return [SrsDocumentDue(**row) for row in svc.get_due_info_by_document()]
