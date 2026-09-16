from __future__ import annotations

from typing import Any


class DisabledComicAiProvider:
    name = 'disabled'
    enabled = False

    @staticmethod
    def _pending() -> dict[str, Any]:
        return {
            'characters': [], 'scenes': [], 'dialogues': [], 'plotEvents': [],
            'visualStyle': None, 'props': [], 'locations': [], 'storySummary': None,
            'status': 'pending',
        }

    def analyze_comic_pages(self, pages: list[dict[str, Any]]) -> dict[str, Any]:
        del pages
        return self._pending()

    def rewrite_story(self, analysis: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        del analysis, settings
        return {'status': 'pending'}

    def generate_episode(self, story: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        del story, settings
        return {'status': 'pending'}
