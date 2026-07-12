import json

import pytest

from quizzer.generation.generator import MCQGenerator, _parse_questions, _question_count
from quizzer.generation.models import RawMCQ
from quizzer.ingestion.models import Chunk


def _make_chunk(word_count: int = 500) -> Chunk:
    return Chunk(
        id="CHUNK001",
        document_id="DOC001",
        content=" ".join(["word"] * word_count),
        word_count=word_count,
        chunk_index=0,
    )


# --- Question count ---

def test_question_count_small():
    assert _question_count(300) == 1


def test_question_count_medium():
    assert _question_count(500) == 2


def test_question_count_large():
    assert _question_count(700) == 3


# --- Parse questions ---

def test_parse_direct_json():
    raw = json.dumps({
        "questions": [{
            "question": "What is X?",
            "options": ["A", "B", "C", "D"],
            "correct_index": 0,
            "explanation": "A is correct because it directly addresses the definition of X.",
            "difficulty": "easy",
            "source_chunk_id": "CHUNK001",
        }]
    })
    results = _parse_questions(raw, "CHUNK001")
    assert len(results) == 1
    assert results[0].question == "What is X?"


def test_parse_extracts_from_prose():
    json_block = json.dumps({
        "questions": [{
            "question": "What is Y?",
            "options": ["A", "B", "C", "D"],
            "correct_index": 1,
            "explanation": "B is the correct answer because Y is defined as B in the content.",
            "difficulty": "medium",
            "source_chunk_id": "CHUNK001",
        }]
    })
    raw = f"Here is some prose. {json_block} More text."
    results = _parse_questions(raw, "CHUNK001")
    assert len(results) == 1


def test_parse_invalid_json_returns_empty():
    results = _parse_questions("not json at all", "CHUNK001")
    assert results == []


def test_parse_top_level_array():
    """Regression: LLMs sometimes return a bare array instead of {"questions": [...]}."""
    raw = json.dumps([
        {
            "question": "What is X?",
            "options": ["A", "B", "C", "D"],
            "correct_index": 0,
            "explanation": "A is correct because it directly addresses the definition of X.",
            "difficulty": "easy",
            "source_chunk_id": "CHUNK001",
        },
        {
            "question": "What is Y?",
            "options": ["A", "B", "C", "D"],
            "correct_index": 1,
            "explanation": "B is correct because Y is defined as B in the provided content.",
            "difficulty": "medium",
            "source_chunk_id": "CHUNK001",
        },
    ])
    results = _parse_questions(raw, "CHUNK001")
    assert len(results) == 2
    assert results[0].question == "What is X?"
    assert results[1].question == "What is Y?"


def test_parse_empty_array_returns_empty():
    results = _parse_questions("[]", "CHUNK001")
    assert results == []


def test_parse_validates_pydantic():
    # Missing required field (explanation)
    raw = json.dumps({
        "questions": [{
            "question": "What is Z?",
            "options": ["A", "B", "C"],  # only 3 options — invalid
            "correct_index": 0,
            "explanation": "A is correct.",
            "difficulty": "easy",
            "source_chunk_id": "CHUNK001",
        }]
    })
    results = _parse_questions(raw, "CHUNK001")
    assert results == []


# --- MCQGenerator ---

def test_generator_uses_client(mock_ollama_client):
    # Override chunk_id to match mock response
    chunk = _make_chunk(500)
    # The mock client returns a fixed chunk_id "CHUNK001"; patch chunk id
    chunk = Chunk(
        id="CHUNK001",
        document_id="DOC001",
        content=" ".join(["word"] * 500),
        word_count=500,
        chunk_index=0,
    )
    gen = MCQGenerator(mock_ollama_client)
    result = gen.generate_for_chunk(chunk, "DOC001")

    assert result.chunk_id == "CHUNK001"
    assert result.document_id == "DOC001"
    assert len(result.questions) == 1
    assert isinstance(result.questions[0], RawMCQ)
    mock_ollama_client.generate.assert_called_once()
