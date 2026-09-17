import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi import HTTPException

from backend import comic_story_api as comic
from backend.ai.providers.base import get_comic_ai_provider
from backend.ai.providers.openai_compatible import parse_json_response, safe_base_url
from backend.ai.service import ComicAiError, ComicAiService, merge_batches


def semantic(page=1, character='unknown'):
    return {
        'characters': [{'id': 'temp-1', 'name': character, 'appearance': 'round face', 'clothing': 'blue coat',
                        'firstSeenPage': page, 'pages': [page], 'confidence': .72,
                        'evidence': [{'sourcePage': page, 'evidence': 'visible character'}]}],
        'scenes': [{'id': f'scene-{page}', 'location': 'unknown', 'pages': [page], 'confidence': .5,
                    'evidence': [{'sourcePage': page, 'evidence': 'background unclear'}]}],
        'dialogues': [{'page': page, 'speakerId': None, 'text': 'Hello!', 'confidence': .6, 'evidence': 'speech bubble'}],
        'plotEvents': [{'id': f'event-{page}', 'pages': [page], 'action': 'The character waves.', 'confidence': .7,
                        'evidence': [{'sourcePage': page, 'evidence': 'raised hand'}]}],
        'visualStyle': {'medium': 'comic ink'}, 'props': [], 'locations': [],
        'storySummary': {'titleGuess': 'unknown', 'premise': 'A greeting.'}, 'warnings': [], 'needsReview': True,
    }


class FakeProvider:
    name = 'fake'
    enabled = True
    def __init__(self): self.calls = []
    def get_status(self):
        return {'provider': 'fake', 'enabled': True, 'configured': True, 'model': 'fake-vision', 'baseUrlSafe': 'local', 'supportsVision': True, 'reason': None}
    def analyze_comic_pages(self, pages, context=None):
        self.calls.append(([p['page'] for p in pages], context))
        return semantic(pages[0]['page'])
    def adapt_story(self, analysis, settings):
        return {'title': 'Adapted', 'logline': 'A safe greeting.', 'summary': 'A child learns hello.',
                'characters': analysis['characters'], 'scenes': analysis['scenes'], 'storyBeats': [],
                'ending': 'Friends smile.', 'learningGoals': settings.get('educationGoals', []),
                'sourceEvidence': [{'sourcePage': 1, 'evidence': 'Hello'}]}
    def generate_episode(self, story, settings):
        return {'title': story['title'], 'level': 'Pre-A1', 'age': '3-8', 'duration': 5, 'aspectRatio': '9:16',
                'characters': ['character-01'], 'characterDefinitions': story['characters'],
                'scenes': story['scenes'], 'source': settings.get('source', {}),
                'shots': [{'id': 1, 'title': 'Greeting', 'speaker': 'character-01', 'english': 'Hello!', 'chinese': '你好！', 'duration': 5,
                           'imagePrompt': 'Round-faced child in a blue coat waves in the evidenced room.',
                           'videoPrompt': 'Medium shot; child raises one hand; coat and room remain consistent.',
                           'negativePrompt': 'identity drift, text artifacts', 'sourcePages': [1],
                           'sourceEvidence': [{'sourcePage': 1, 'evidence': 'raised hand'}], 'dialogueSource': 'source'}]}


class Phase1H3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pdf = self.root / 'comic.pdf'
        doc = fitz.open()
        for i in range(9):
            page = doc.new_page(width=240, height=320); page.insert_text((20, 40), f'Page {i+1}: Hello')
        doc.save(self.pdf); doc.close()
        self.before = (self.pdf.stat().st_size, self.pdf.stat().st_mtime_ns, self.pdf.read_bytes())
        self.provider = FakeProvider(); self.service = ComicAiService(self.provider, self.root / 'cache')
        self.pages = [{'page': i, 'text': f'Page {i}'} for i in range(1, 10)]
    def tearDown(self): self.tmp.cleanup()

    def test_disabled_is_default_and_never_calls_network(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = get_comic_ai_provider()
            self.assertFalse(provider.get_status()['enabled'])
            with self.assertRaises(ComicAiError) as caught:
                ComicAiService(provider, self.root / 'cache').analyze(self.pdf, 'token', self.pages[:1])
            self.assertEqual(caught.exception.code, 'AI_PROVIDER_DISABLED')

    def test_openai_configuration_and_secret_safe_status(self):
        env = {'COMIC_AI_PROVIDER': 'openai_compatible', 'COMIC_AI_BASE_URL': 'http://user:secret@localhost:1234/v1', 'COMIC_AI_MODEL': 'vision', 'COMIC_AI_API_KEY': 'top-secret'}
        with patch.dict(os.environ, env, clear=True):
            status = get_comic_ai_provider().get_status()
        self.assertTrue(status['configured']); self.assertEqual(status['baseUrlSafe'], 'http://localhost:1234/v1')
        self.assertNotIn('secret', str(status)); self.assertNotIn('top-secret', str(status))

    def test_batch_schema_evidence_unknown_merge_and_cache(self):
        first = self.service.analyze(self.pdf, 'safe-token', self.pages)
        self.assertEqual(first['batchCount'], 3); self.assertEqual(len(self.provider.calls), 3)
        self.assertTrue(self.provider.calls[1][1]['knownCharacters'])
        self.assertEqual(len(first['characters']), 1)
        self.assertEqual(first['characters'][0]['name'], 'unknown')
        self.assertEqual(first['characters'][0]['pages'], [1, 5, 9])
        self.assertEqual(first['dialogues'][0]['speakerId'], None)
        self.assertEqual(first['source'], {'type': 'comic', 'name': 'comic.pdf', 'fileToken': 'safe-token', 'pages': list(range(1, 10))})
        second = self.service.analyze(self.pdf, 'safe-token', self.pages)
        self.assertTrue(second['cacheHit']); self.assertEqual(len(self.provider.calls), 3)

    def test_cache_invalidates_when_source_changes(self):
        a = self.service.analyze(self.pdf, 'token', self.pages[:1])
        with self.pdf.open('ab') as stream: stream.write(b'changed')
        b = self.service.analyze(self.pdf, 'token', self.pages[:1])
        self.assertNotEqual(a['id'], b['id']); self.assertFalse(b['cacheHit'])

    def test_page_limit_and_source_unchanged(self):
        with self.assertRaises(ComicAiError) as caught:
            self.service.analyze(self.pdf, 'token', self.pages + self.pages[:4])
        self.assertEqual(caught.exception.code, 'AI_CONTEXT_TOO_LARGE')
        self.service.analyze(self.pdf, 'token', self.pages[:2])
        after = (self.pdf.stat().st_size, self.pdf.stat().st_mtime_ns, self.pdf.read_bytes())
        self.assertEqual(self.before, after)

    def test_adaptation_episode_and_stable_speaker(self):
        analysis = self.service.analyze(self.pdf, 'token', self.pages[:1])
        story = self.service.adapt(analysis, {'educationGoals': ['greeting']})
        episode = self.service.episode(story, {'source': analysis['source']})
        self.assertEqual(story['learningGoals'], ['greeting'])
        self.assertEqual(episode['shots'][0]['speaker'], 'character-01')
        self.assertEqual(episode['shots'][0]['dialogueSource'], 'source')
        self.assertNotIn(str(self.root), str(episode))

    def test_invalid_response_timeout_and_json_repair(self):
        self.assertEqual(parse_json_response('```json\n{"ok": true}\n```'), {'ok': True})
        with self.assertRaises(Exception): parse_json_response('prefix {bad}')
        self.provider.analyze_comic_pages = lambda pages, context=None: {'characters': 'bad'}
        with self.assertRaises(ComicAiError) as caught:
            self.service.analyze(self.pdf, 'invalid', self.pages[:1], True)
        self.assertEqual(caught.exception.code, 'AI_RESPONSE_INVALID')
        self.provider.analyze_comic_pages = lambda pages, context=None: (_ for _ in ()).throw(TimeoutError())
        with self.assertRaises(ComicAiError) as caught:
            self.service.analyze(self.pdf, 'timeout', self.pages[:1], True)
        self.assertEqual(caught.exception.code, 'AI_REQUEST_TIMEOUT')


if __name__ == '__main__': unittest.main()
