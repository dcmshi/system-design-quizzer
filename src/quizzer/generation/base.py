from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    model: str

    def generate(self, prompt: str) -> str: ...
    def health_check(self) -> bool: ...
    def close(self) -> None: ...
