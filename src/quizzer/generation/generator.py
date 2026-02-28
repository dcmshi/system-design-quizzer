import json
import logging

from pydantic import ValidationError

from quizzer.generation.base import LLMClient
from quizzer.generation.models import GenerationResult, RawMCQ
from quizzer.generation.prompt_builder import PROMPT_VERSION, build_prompt
from quizzer.ingestion.models import Chunk

logger = logging.getLogger(__name__)


def _question_count(word_count: int) -> int:
    if word_count <= 400:
        return 1
    if word_count <= 600:
        return 2
    return 3


def _parse_questions(raw: str, chunk_id: str) -> list[RawMCQ]:
    """Attempt 3-layer parse: direct → regex extract → give up."""

    def _from_data(data: dict) -> list[RawMCQ]:
        items = data.get("questions", [data])  # fallback: treat root as single question
        if isinstance(items, dict):
            items = [items]
        results: list[RawMCQ] = []
        for item in items:
            # Ensure chunk id is set
            if not item.get("source_chunk_id"):
                item["source_chunk_id"] = chunk_id
            try:
                results.append(RawMCQ.model_validate(item))
            except ValidationError as exc:
                logger.warning("Skipping invalid MCQ object: %s", exc)
        return results

    # Layer 1: direct parse
    try:
        data = json.loads(raw)
        return _from_data(data)
    except json.JSONDecodeError:
        pass

    # Layer 2: find first syntactically valid JSON object using raw_decode
    decoder = json.JSONDecoder()
    for i, ch in enumerate(raw):
        if ch == '{':
            try:
                data, _ = decoder.raw_decode(raw, i)
                return _from_data(data)
            except json.JSONDecodeError:
                continue

    logger.warning("Could not parse LLM response as JSON for chunk %s", chunk_id)
    return []


class MCQGenerator:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def generate_for_chunk(self, chunk: Chunk, document_id: str) -> GenerationResult:
        n = _question_count(chunk.word_count)
        prompt = build_prompt(chunk, n)

        raw = self.client.generate(prompt)
        questions = _parse_questions(raw, chunk.id)

        return GenerationResult(
            chunk_id=chunk.id,
            document_id=document_id,
            questions=questions,
            raw_response=raw,
            model=self.client.model,
            prompt_version=PROMPT_VERSION,
        )
