from __future__ import annotations

from typing import Any


class DisabledComicAiProvider:
    name = 'disabled'
    enabled = False

    def get_status(self) -> dict[str, Any]:
        return {'provider': self.name, 'enabled': False, 'configured': True, 'model': None,
                'baseUrlSafe': '', 'supportsVision': False, 'reachable': False,
                'visionVerified': False, 'structuredOutputVerified': False, 'lastProbeAt': None,
                'reason': 'AI Provider is disabled by default'}

    def probe(self):
        raise RuntimeError('AI_PROVIDER_DISABLED')

    @staticmethod
    def _pending() -> dict[str, Any]:
        return {
            'characters': [], 'scenes': [], 'dialogues': [], 'plotEvents': [],
            'visualStyle': None, 'props': [], 'locations': [], 'storySummary': None,
            'status': 'pending',
        }

    def analyze_comic_pages(self, pages: list[dict[str, Any]], context: dict[str, Any] | None = None) -> dict[str, Any]:
        del pages, context
        return self._pending()

    def rewrite_story(self, analysis: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        del analysis, settings
        return {'status': 'pending'}

    adapt_story = rewrite_story

    def generate_episode(self, story: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        del story, settings
        return {'status': 'pending'}
