from __future__ import annotations

import os
from typing import Any, Protocol


class ComicAiProvider(Protocol):
    name: str
    enabled: bool

    def analyze_comic_pages(self, pages: list[dict[str, Any]]) -> dict[str, Any]: ...
    def rewrite_story(self, analysis: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]: ...
    def generate_episode(self, story: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]: ...


def get_comic_ai_provider() -> ComicAiProvider:
    provider = os.getenv('COMIC_AI_PROVIDER', 'disabled').strip().lower()
    if provider in {'', 'disabled', 'none', 'off'}:
        from .disabled import DisabledComicAiProvider
        return DisabledComicAiProvider()
    raise RuntimeError(f'comic_ai_provider_not_configured: {provider}')
