from quizzer.config import settings
from quizzer.generation.models import RawMCQ


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

    return errors
