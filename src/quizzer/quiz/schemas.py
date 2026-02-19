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


class StatusUpdateRequest(BaseModel):
    status: Literal["approved", "edited"]


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
