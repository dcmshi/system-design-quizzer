from typing import Literal

from pydantic import BaseModel, Field


class QuestionSummary(BaseModel):
    id: str
    question: str
    options: list[str]
    difficulty: str
    source_document_id: str
    status: str


class QuestionDetail(BaseModel):
    id: str
    question: str
    options: list[str]
    difficulty: str
    source_document_id: str
    source_chunk_id: str
    status: str
    model: str
    prompt_version: str
    created_at: str
    times_answered: int = 0
    times_correct: int = 0
    hit_rate: float | None = None


class QuestionAnswer(BaseModel):
    id: str
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    difficulty: str


class AnswerRequest(BaseModel):
    selected_index: int = Field(..., ge=0, le=3)


class AnswerResponse(BaseModel):
    correct: bool
    correct_index: int
    explanation: str


class QuestionEditRequest(BaseModel):
    question: str
    options: list[str] = Field(..., min_length=4, max_length=4)
    correct_index: int = Field(..., ge=0, le=3)
    explanation: str
    difficulty: str


class StatusUpdateRequest(BaseModel):
    status: Literal["approved", "edited", "rejected"]


class DocumentSummary(BaseModel):
    id: str
    title: str
    source: str
    tags: list[str]
    source_path: str
    created_at: str
    question_count: int


class HealthResponse(BaseModel):
    status: str
    db: str
    ollama: str


class PaginatedQuestions(BaseModel):
    items: list[QuestionSummary]
    total: int
    limit: int
    offset: int


class QuizResponse(BaseModel):
    questions: list[QuestionSummary]
    requested: int
    returned: int


class ExportDocument(BaseModel):
    id: str
    title: str
    source: str
    content: str
    tags: list[str]
    source_path: str
    created_at: str


class ExportQuestion(BaseModel):
    id: str
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    difficulty: str
    source_document_id: str
    source_chunk_id: str
    status: str
    fingerprint: str
    model: str
    prompt_version: str
    created_at: str


class ExportPayload(BaseModel):
    version: str
    exported_at: str
    documents: list[ExportDocument]
    questions: list[ExportQuestion]


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]


class StartQuizSessionRequest(BaseModel):
    n: int = Field(5, ge=1, le=50)
    difficulty: str | None = None
    tag: str | None = None
    document_ids: list[str] = Field(default_factory=list)


class QuizSessionResponse(BaseModel):
    session_id: str
    questions: list[QuestionSummary]
    started_at: str


class QuizAnswerRequest(BaseModel):
    question_id: str
    selected_index: int = Field(..., ge=0, le=3)


class QuizAnswerResponse(BaseModel):
    correct: bool
    correct_index: int
    explanation: str


class QuizFinishResponse(BaseModel):
    session_id: str
    finished_at: str
    n_answered: int
    n_correct: int
    n_wrong: int
    n_skipped: int
