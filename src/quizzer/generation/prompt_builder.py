from quizzer.ingestion.models import Chunk

PROMPT_VERSION = "v3"

PROMPT_V3 = """\
You are an expert technical educator creating multiple-choice questions (MCQs) for a system design quiz.

Given the following content chunk, generate exactly {n_questions} high-quality MCQ(s).

CONTENT:
---
{content}
---

CHUNK ID: {chunk_id}

REQUIREMENTS:
- Each question must test understanding, not memorization
- Questions must be answerable from the provided content only
- Include exactly 4 answer options per question
- Exactly 1 option must be correct
- Distractors must be plausible but clearly wrong to someone who understood the content
- Explanation must justify why the correct answer is right (minimum 50 characters)
- difficulty must be one of: "easy", "medium", "hard"
- source_chunk_id must be exactly: {chunk_id}
- Write option text as plain prose — do NOT prefix options with labels like "A)", "B.", "(C)", "1.", etc.
- In the explanation, describe WHY the correct answer is right using its actual content — do NOT use letter labels ("Option A/B/C/D") or numeric labels ("Option 0/1/2/3")

OUTPUT FORMAT — return ONLY a valid JSON object with this exact structure:
{{
  "questions": [
    {{
      "question": "What is the primary advantage of X?",
      "options": ["First choice text", "Second choice text", "Third choice text", "Fourth choice text"],
      "correct_index": 0,
      "explanation": "First choice text is correct because it directly addresses ...",
      "difficulty": "medium",
      "source_chunk_id": "{chunk_id}"
    }}
  ]
}}

Return ONLY the JSON object. No markdown, no prose, no code fences.
"""


def build_prompt(chunk: Chunk, n_questions: int) -> str:
    return PROMPT_V3.format(
        content=chunk.content,
        chunk_id=chunk.id,
        n_questions=n_questions,
    )
