from __future__ import annotations

import os
from typing import Any, Protocol


class ComicAiProvider(Protocol):
    name: str
    enabled: bool

    def get_status(self) -> dict[str, Any]: ...
    def analyze_comic_pages(self, pages: list[dict[str, Any]], context: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def adapt_story(self, analysis: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]: ...
    def generate_episode(self, story: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]: ...


def get_comic_ai_provider() -> ComicAiProvider:
    provider = os.getenv('COMIC_AI_PROVIDER', 'disabled').strip().lower()
    if provider in {'', 'disabled', 'none', 'off'}:
        from .disabled import DisabledComicAiProvider
        return DisabledComicAiProvider()
    if provider in {'openai_compatible', 'openai-compatible'}:
        from .openai_compatible import OpenAICompatibleComicProvider
        return OpenAICompatibleComicProvider()
    raise RuntimeError('AI_PROVIDER_UNAVAILABLE')
