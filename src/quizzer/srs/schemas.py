from pydantic import BaseModel, Field

from quizzer.quiz.schemas import QuestionSummary


class StartSessionRequest(BaseModel):
    n: int = Field(10, ge=1, le=50)
    document_ids: list[str] = Field(default_factory=list)


class SrsSessionResponse(BaseModel):
    session_id: str
    questions: list[QuestionSummary]
    started_at: str


class SrsReviewRequest(BaseModel):
    question_id: str
    selected_index: int = Field(..., ge=0, le=3)


class SrsReviewResponse(BaseModel):
    correct: bool
    correct_index: int
    explanation: str
    next_due: str        # ISO date "YYYY-MM-DD"
    interval_days: int
    ease_factor: float


class SrsFinishResponse(BaseModel):
    session_id: str
    finished_at: str
    n_reviewed: int
    n_correct: int
    n_wrong: int


class SrsDueResponse(BaseModel):
    due_count: int
    new_count: int
    total_actionable: int  # due + new


class SrsDocumentDue(SrsDueResponse):
    document_id: str


class SrsReviewRecord(BaseModel):
    id: str
    session_id: str
    question_id: str
    rating: int
    was_correct: bool
    ease_factor_after: float
    interval_after: int
    reviewed_at: str


class SrsSessionDetail(BaseModel):
    id: str
    question_count: int
    question_ids: list[str] | None = None  # None for pre-migration sessions
    started_at: str
    finished_at: str | None
    reviews: list[SrsReviewRecord]
