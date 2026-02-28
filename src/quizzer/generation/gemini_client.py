from google import genai
from google.genai import types


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self._client = genai.Client(api_key=api_key)
        self.model = model

    def generate(self, prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        return response.text

    def health_check(self) -> bool:
        try:
            # Lightweight metadata call — no quota cost
            next(self._client.models.list())
            return True
        except Exception:
            return False

    def close(self) -> None:
        pass

    def __enter__(self) -> "GeminiClient":
        return self

    def __exit__(self, *args: object) -> None:
        pass
