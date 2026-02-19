from typing import Literal

from pydantic import BaseModel, field_validator


class RawMCQ(BaseModel):
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    difficulty: Literal["easy", "medium", "hard"]
    source_chunk_id: str

    @field_validator("options")
    @classmethod
    def must_have_four_options(cls, v: list[str]) -> list[str]:
        if len(v) != 4:
            raise ValueError(f"Expected 4 options, got {len(v)}")
        return v

    @field_validator("correct_index")
    @classmethod
    def must_be_valid_index(cls, v: int) -> int:
        if v not in (0, 1, 2, 3):
            raise ValueError(f"correct_index must be 0-3, got {v}")
        return v


class GenerationResult(BaseModel):
    chunk_id: str
    document_id: str
    questions: list[RawMCQ]
    raw_response: str
    model: str
    prompt_version: str
