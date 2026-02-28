import logging
import re
import time

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]:\s*['\"](\d+(?:\.\d+)?)s")


def _parse_retry_delay(error_str: str) -> float | None:
    """Extract the suggested retryDelay (seconds) from a 429 error string."""
    m = _RETRY_DELAY_RE.search(error_str)
    return float(m.group(1)) + 1.0 if m else None  # +1s safety buffer


def _is_rate_limit(exc: Exception) -> bool:
    return "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        request_delay: float = 7.0,
        max_retries: int = 3,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self._request_delay = request_delay
        self._max_retries = max_retries
        self._last_call_at: float = 0.0

    def _throttle(self) -> None:
        """Sleep if needed to honour the inter-request delay."""
        if self._request_delay <= 0:
            return
        elapsed = time.monotonic() - self._last_call_at
        wait = self._request_delay - elapsed
        if wait > 0:
            logger.debug("Throttling: sleeping %.1fs before Gemini call", wait)
            time.sleep(wait)

    def generate(self, prompt: str) -> str:
        for attempt in range(self._max_retries + 1):
            self._throttle()
            try:
                self._last_call_at = time.monotonic()
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                return response.text
            except Exception as exc:
                if not _is_rate_limit(exc) or attempt >= self._max_retries:
                    raise
                delay = _parse_retry_delay(str(exc)) or (2 ** attempt * 10)
                logger.warning(
                    "Rate limited (attempt %d/%d) — waiting %.0fs …",
                    attempt + 1,
                    self._max_retries + 1,
                    delay,
                )
                time.sleep(delay)
                self._last_call_at = 0.0  # force full throttle delay after sleep

        raise RuntimeError("generate() exited retry loop unexpectedly")

    def health_check(self) -> bool:
        try:
            # Lightweight metadata call — no generation quota cost
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
