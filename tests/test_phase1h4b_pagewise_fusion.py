import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from backend.ai.pagewise import fuse_page_results
from backend.ai.models import PageDialogue
from backend.ai.service import ComicAiError, ComicAiService


class PagewiseFake:
    name = 'fake'
    enabled = True

    def __init__(self, fail_visual_page=None):
        self.dialogue_calls = 0
        self.visual_calls = 0
        self.fail_visual_page = fail_visual_page

    def get_status(self):
        return {'provider': 'fake', 'enabled': True, 'configured': True, 'model': 'local-7b',
                'baseUrlSafe': 'local', 'supportsVision': True, 'isLocalEndpoint': True, 'reason': None}

    def analyze_page_dialogue(self, page):
        self.dialogue_calls += 1
        return {'page': page['page'], 'dialogues': [{'text': f'Hello from {page["page"]}',
                'speakerTemporaryId': 'hero', 'speakerDescription': 'girl blue coat',
                'bubblePosition': 'top-left', 'confidence': .9}], 'warnings': []}

    def analyze_page_visual(self, page):
        self.visual_calls += 1
        if page['page'] == self.fail_visual_page:
            raise TimeoutError()
        return {'page': page['page'], 'characters': [{'temporaryId': 'hero', 'name': None,
                'appearance': 'young girl round face', 'clothing': 'blue coat', 'bodyType': 'small',
                'hairOrFur': 'black hair', 'accessories': ['glasses'], 'position': 'left',
                'roleHint': 'hero', 'confidence': .8}],
                'scene': {'location': 'living room', 'description': 'A girl stands by a fireplace.', 'confidence': .8},
                'plotEvents': [{'action': 'The girl points at a picture.', 'characterTemporaryIds': ['hero'], 'confidence': .8}],
                'props': [{'name': 'picture', 'confidence': .7}], 'visualNotes': '', 'warnings': []}

    def adapt_story(self, *_):
        raise AssertionError('not used')

    def generate_episode(self, *_):
        raise AssertionError('not used')


class Phase1H4BTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.pdf = self.root / 'comic.pdf'; document = fitz.open()
        for page in range(3):
            value = document.new_page(width=300, height=450); value.insert_text((20, 30), f'PAGE {page + 1}')
        document.save(self.pdf); document.close()
        self.pages = [{'page': 1, 'text': ''}, {'page': 2, 'text': ''}]

    def tearDown(self):
        self.tmp.cleanup()

    def test_pagewise_schema_evidence_character_and_speaker_resolution(self):
        provider = PagewiseFake(); service = ComicAiService(provider, self.root / 'cache')
        with patch.dict(os.environ, {'COMIC_AI_ANALYSIS_STRATEGY': 'pagewise-fusion'}, clear=False):
            value = service.analyze(self.pdf, 'token', self.pages)
        self.assertEqual(value['analysisStrategy'], 'pagewise-fusion')
        self.assertEqual(value['totalRequests'], 4); self.assertEqual(len(value['characters']), 1)
        self.assertEqual(value['characters'][0]['id'], 'character_01')
        self.assertTrue(value['characters'][0]['evidence'][0]['systemGrounded'])
        self.assertEqual(value['dialogues'][0]['speakerResolution'], 'resolved')
        self.assertTrue(value['dialogues'][0]['systemGrounded'])
        self.assertTrue(value['qualitySummary']['qualityGatePassed'])
        self.assertTrue(value['storySummary']['premise'])

    def test_page_dialogue_normalizes_percentage_confidence(self):
        self.assertEqual(PageDialogue.model_validate({'text': 'Hi', 'confidence': 95}).confidence, .95)

    def test_page_and_fusion_cache_prevent_repeat_requests(self):
        provider = PagewiseFake(); service = ComicAiService(provider, self.root / 'cache')
        with patch.dict(os.environ, {'COMIC_AI_ANALYSIS_STRATEGY': 'pagewise-fusion'}, clear=False):
            first = service.analyze(self.pdf, 'token', self.pages)
            second = service.analyze(self.pdf, 'token', self.pages)
        self.assertFalse(first['cacheHit']); self.assertTrue(second['cacheHit'])
        self.assertEqual(provider.dialogue_calls, 2); self.assertEqual(provider.visual_calls, 2)
        self.assertEqual(len(list((self.root / 'cache' / 'pages').glob('*.json'))), 4)

    def test_partial_visual_failure_keeps_dialogue_and_blocks_quality_gate(self):
        provider = PagewiseFake(fail_visual_page=2); service = ComicAiService(provider, self.root / 'cache')
        with patch.dict(os.environ, {'COMIC_AI_ANALYSIS_STRATEGY': 'pagewise-fusion'}, clear=False):
            value = service.analyze(self.pdf, 'token', self.pages)
        self.assertEqual(len(value['dialogues']), 2)
        self.assertIn('PAGE_2_VISUAL_ANALYSIS_FAILED', value['warnings'])
        self.assertTrue(value['needsReview'])

    def test_dialogue_only_and_visual_only_fusion(self):
        dialogue = fuse_page_results([{'page': 1, 'dialogue': {'page': 1, 'dialogues': [{'text': 'Hi'}]}}])
        self.assertEqual(dialogue['dialogues'][0]['text'], 'Hi')
        visual = fuse_page_results([{'page': 1, 'visual': PagewiseFake().analyze_page_visual({'page': 1})}])
        self.assertEqual(len(visual['characters']), 1); self.assertEqual(len(visual['plotEvents']), 1)

    def test_visible_scene_supplies_reviewable_event_when_model_omits_events(self):
        source = PagewiseFake().analyze_page_visual({'page': 1}); source['plotEvents'] = []
        value = fuse_page_results([{'page': 1, 'visual': source}])
        self.assertEqual(value['plotEvents'][0]['action'], source['scene']['description'])
        self.assertIn('PAGE_1_EVENT_DERIVED_FROM_SCENE', value['warnings'])
        self.assertTrue(value['plotEvents'][0]['evidence'][0]['systemGrounded'])

    def test_pagewise_quality_gate_blocks_adaptation(self):
        provider = PagewiseFake(); service = ComicAiService(provider, self.root / 'cache')
        with self.assertRaises(ComicAiError) as caught:
            service.adapt({'analysisStrategy': 'pagewise-fusion', 'characters': [], 'dialogues': [],
                           'scenes': [], 'plotEvents': [], 'storySummary': {}, 'source': {'pages': [1]}}, {})
        self.assertEqual(caught.exception.code, 'AI_SEMANTIC_QUALITY_GATE_FAILED')


if __name__ == '__main__':
    unittest.main()
