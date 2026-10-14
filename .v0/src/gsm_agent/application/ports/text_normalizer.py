from typing import Protocol


class TextNormalizer(Protocol):
    def normalize(self, text: str) -> str:
        """Return SMS plain text, preserving prose/links and removing styling."""
        ...
