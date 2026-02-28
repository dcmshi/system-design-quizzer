import re

from quizzer.config import settings
from quizzer.generation.models import RawMCQ

_OPTION_LETTER_RE = re.compile(r"\bOption\s+([A-D])\b", re.IGNORECASE)


def validate_mcq(mcq: RawMCQ, cfg=None) -> list[str]:
    cfg = cfg or settings
    errors: list[str] = []

    # 4 distinct options
    if len(mcq.options) != 4:
        errors.append(f"Expected 4 options, got {len(mcq.options)}")
    elif len(set(mcq.options)) != 4:
        errors.append("Options must all be distinct")

    # correct_index in range
    if mcq.correct_index not in (0, 1, 2, 3):
        errors.append(f"correct_index {mcq.correct_index} out of range 0-3")

    # Explanation length
    if len(mcq.explanation) < cfg.min_explanation_length:
        errors.append(
            f"Explanation too short: {len(mcq.explanation)} < {cfg.min_explanation_length}"
        )

    # No option duplicates question
    q_lower = mcq.question.lower().strip().rstrip("?")
    for opt in mcq.options:
        if opt.lower().strip() == q_lower:
            errors.append(f"Option duplicates question text: '{opt}'")

    # Explanation letter must match correct_index
    letter_match = _OPTION_LETTER_RE.search(mcq.explanation)
    if letter_match:
        stated_letter = letter_match.group(1).upper()
        stated_index = ord(stated_letter) - ord("A")
        if stated_index != mcq.correct_index:
            expected_letter = chr(ord("A") + mcq.correct_index)
            errors.append(
                f"Explanation mentions Option {stated_letter} but correct_index is "
                f"{mcq.correct_index} (Option {expected_letter})"
            )

    return errors
