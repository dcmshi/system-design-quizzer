import re

from quizzer.generation.models import RawMCQ

# Matches leading option labels: "A) ", "A. ", "(A) ", "a) ", etc.
_OPTION_PREFIX_RE = re.compile(r"^(?:[A-Da-d][.)]\s*|\([A-Da-d]\)\s*)")


def normalize_mcq(mcq: RawMCQ) -> RawMCQ:
    question = mcq.question.strip()
    if not question.endswith("?"):
        question = question + "?"

    options = [_OPTION_PREFIX_RE.sub("", opt).strip().capitalize() for opt in mcq.options]
    explanation = mcq.explanation.strip()
    difficulty = mcq.difficulty

    return RawMCQ(
        question=question,
        options=options,
        correct_index=mcq.correct_index,
        explanation=explanation,
        difficulty=difficulty,
        source_chunk_id=mcq.source_chunk_id,
    )
