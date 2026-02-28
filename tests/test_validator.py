import pytest

from quizzer.generation.models import RawMCQ
from quizzer.validation.duplicate_detector import fingerprint, is_duplicate
from quizzer.validation.normalizer import normalize_mcq
from quizzer.validation.schema_validator import validate_mcq


def _make_mcq(**overrides) -> RawMCQ:
    base = dict(
        question="What is the main advantage of consistent hashing?",
        options=[
            "Minimizes data replication",
            "Distributes load while minimizing remapping",
            "Encrypts data at rest",
            "Ensures sequential reads",
        ],
        correct_index=1,
        explanation="Consistent hashing places nodes on a ring so that only neighboring nodes are affected when a node is added or removed, minimizing data movement.",
        difficulty="medium",
        source_chunk_id="CHUNK001",
    )
    base.update(overrides)
    return RawMCQ(**base)


# --- Normalizer ---

def test_normalize_adds_question_mark():
    mcq = _make_mcq(question="What is hashing")
    result = normalize_mcq(mcq)
    assert result.question.endswith("?")


def test_normalize_keeps_existing_question_mark():
    mcq = _make_mcq(question="What is hashing?")
    result = normalize_mcq(mcq)
    assert result.question == "What is hashing?"


def test_normalize_capitalizes_options():
    mcq = _make_mcq(options=["option a", "option b", "option c", "option d"])
    result = normalize_mcq(mcq)
    assert all(opt[0].isupper() for opt in result.options)


def test_normalize_strips_whitespace():
    mcq = _make_mcq(question="  What is it?  ", explanation="  It is because of X.  ")
    result = normalize_mcq(mcq)
    assert result.question == "What is it?"
    assert result.explanation == "It is because of X."


# --- Schema Validator ---

def test_validate_valid_mcq_returns_no_errors():
    mcq = _make_mcq()
    errors = validate_mcq(mcq)
    assert errors == []


def test_validate_duplicate_options():
    mcq = _make_mcq(options=["Same", "Same", "Option C", "Option D"])
    errors = validate_mcq(mcq)
    assert any("distinct" in e for e in errors)


def test_validate_short_explanation():
    mcq = _make_mcq(explanation="Too short.")
    errors = validate_mcq(mcq)
    assert any("Explanation" in e for e in errors)


def test_validate_option_duplicates_question():
    q = "What is the main advantage of consistent hashing"
    mcq = _make_mcq(
        question=q + "?",
        options=[q, "Option B", "Option C", "Option D"],
    )
    errors = validate_mcq(mcq)
    assert any("duplicates question" in e for e in errors)


def test_validate_explanation_letter_mismatch():
    # correct_index=1 (B) but explanation says "Option C is correct"
    mcq = _make_mcq(
        correct_index=1,
        explanation="Option C is correct because it distributes load while minimizing remapping.",
    )
    errors = validate_mcq(mcq)
    assert any("Option C" in e and "correct_index is 1" in e for e in errors)


def test_validate_explanation_letter_match_no_error():
    # correct_index=1 (B) and explanation says "Option B is correct"
    mcq = _make_mcq(
        correct_index=1,
        explanation="Option B is correct because it distributes load while minimizing remapping.",
    )
    errors = validate_mcq(mcq)
    assert errors == []


def test_validate_explanation_no_letter_reference_no_error():
    # Explanation doesn't mention any option letter — no error
    mcq = _make_mcq(
        correct_index=1,
        explanation="Consistent hashing minimizes data movement when nodes are added or removed.",
    )
    errors = validate_mcq(mcq)
    assert errors == []


def test_validate_explanation_numeric_index_mismatch():
    # LLM wrote "Option 2" (0-indexed C) but correct_index=1 (B)
    mcq = _make_mcq(
        correct_index=1,
        explanation="Option 2 is correct because it distributes load while minimizing remapping.",
    )
    errors = validate_mcq(mcq)
    assert any("Option 2" in e and "correct_index is 1" in e for e in errors)


def test_validate_explanation_numeric_index_match():
    # "Option 1" (0-indexed B) matches correct_index=1 — no error
    mcq = _make_mcq(
        correct_index=1,
        explanation="Option 1 is correct because it distributes load while minimizing remapping.",
    )
    errors = validate_mcq(mcq)
    assert errors == []


def test_normalize_strips_letter_paren_prefix():
    # "A) text", "B) text" etc. should have the prefix stripped
    mcq = _make_mcq(options=["A) first", "B) second", "C) third", "D) fourth"])
    result = normalize_mcq(mcq)
    assert result.options == ["First", "Second", "Third", "Fourth"]


def test_normalize_strips_letter_dot_prefix():
    mcq = _make_mcq(options=["A. first", "B. second", "C. third", "D. fourth"])
    result = normalize_mcq(mcq)
    assert result.options == ["First", "Second", "Third", "Fourth"]


def test_normalize_strips_parenthetical_prefix():
    mcq = _make_mcq(options=["(A) first", "(B) second", "(C) third", "(D) fourth"])
    result = normalize_mcq(mcq)
    assert result.options == ["First", "Second", "Third", "Fourth"]


def test_normalize_leaves_plain_options_unchanged():
    mcq = _make_mcq(options=["first", "second", "third", "fourth"])
    result = normalize_mcq(mcq)
    assert result.options == ["First", "Second", "Third", "Fourth"]


# --- Duplicate Detector ---

def test_fingerprint_is_deterministic():
    text = "What is consistent hashing?"
    assert fingerprint(text) == fingerprint(text)


def test_fingerprint_normalizes_case_and_punctuation():
    fp1 = fingerprint("What is consistent hashing?")
    fp2 = fingerprint("what is consistent hashing")
    assert fp1 == fp2


def test_is_duplicate_detects_existing():
    text = "What is consistent hashing?"
    fp = fingerprint(text)
    assert is_duplicate(text, {fp})


def test_is_duplicate_returns_false_for_new():
    text = "What is sharding?"
    assert not is_duplicate(text, {fingerprint("What is consistent hashing?")})
