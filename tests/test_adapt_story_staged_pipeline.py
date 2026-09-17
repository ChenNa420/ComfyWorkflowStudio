import json
import tempfile
import unittest
from pathlib import Path

from backend.ai.adaptation import build_adaptation_context
from backend.ai.models import AdaptationContext, AdaptationPlan
from backend.ai.service import ComicAiError, ComicAiService


def source_semantic():
    dialogues = []
    texts = ['Hello!', 'Look there!', 'What is that?', 'Run!', 'Hello!', 'We need a plan.', 'Plan B?', 'Yes!', 'Go now!', 'Safe at last.']
    for index, text in enumerate(texts):
        page = 1 if index < 5 else 2
        dialogues.append({'page': page, 'speakerId': None, 'text': text, 'confidence': .8,
                          'evidence': 'transcribed from visible speech bubble or caption', 'evidenceType': 'speech_bubble',
                          'systemGrounded': True, 'speakerResolution': 'unknown', 'needsReview': False})
    characters = [
        {'id': 'character_01', 'name': 'Hero', 'role': 'child', 'appearance': 'round face', 'clothing': 'blue coat',
         'firstSeenPage': 1, 'pages': [1, 2], 'confidence': .8, 'needsReview': False,
         'evidence': [{'sourcePage': 1, 'evidence': 'character visible on selected comic page'}]},
        {'id': 'character_02', 'name': 'unknown', 'role': 'friend', 'appearance': 'small child', 'clothing': 'red cap',
         'firstSeenPage': 1, 'pages': [1], 'confidence': .5, 'needsReview': True,
         'evidence': [{'sourcePage': 1, 'evidence': 'character visible on selected comic page'}]},
        {'id': 'character_03', 'name': 'unknown', 'role': 'unknown', 'appearance': 'tiny figure', 'clothing': '',
         'firstSeenPage': 2, 'pages': [2], 'confidence': .1, 'needsReview': True,
         'evidence': [{'sourcePage': 2, 'evidence': 'character visible on selected comic page'}]},
        {'id': 'character_04', 'name': 'Ghost', 'role': 'ghost', 'appearance': 'pale ghost', 'clothing': '',
         'firstSeenPage': 2, 'pages': [2], 'confidence': .7, 'needsReview': False,
         'evidence': [{'sourcePage': 2, 'evidence': 'character visible on selected comic page'}]},
    ]
    scenes = [
        {'id': 'scene_01', 'location': 'hall', 'timeOfDay': 'night', 'description': 'Children stand in a hall.',
         'pages': [1], 'characters': ['character_01', 'character_02'], 'mood': 'tense', 'confidence': .8,
         'evidence': [{'sourcePage': 1, 'evidence': 'scene visible on selected comic page'}]},
        {'id': 'scene_02', 'location': 'yard', 'timeOfDay': 'night', 'description': 'The group reaches the yard.',
         'pages': [2], 'characters': ['character_01', 'character_04'], 'mood': 'relieved', 'confidence': .8,
         'evidence': [{'sourcePage': 2, 'evidence': 'scene visible on selected comic page'}]},
    ]
    events = [{'id': 'event_01', 'pages': [2], 'characters': ['character_01'], 'action': 'The hero leads everyone outside.',
               'cause': 'They need safety.', 'result': 'They reach the yard.', 'importance': 'major', 'confidence': .9,
               'evidence': [{'sourcePage': 2, 'evidence': 'visible escape action'}]}]
    return {'id': 'semantic-test', 'characters': characters, 'scenes': scenes, 'dialogues': dialogues,
            'plotEvents': events, 'visualStyle': {'medium': 'comic'}, 'props': [], 'locations': [],
            'storySummary': {'titleGuess': 'Escape', 'premise': 'Children solve a scary problem.',
                             'beginning': 'They notice something strange.', 'middle': 'They make a plan.',
                             'ending': 'They reach safety.', 'conflict': 'A ghost scares them.',
                             'resolution': 'They work together.', 'themes': ['teamwork'], 'tone': 'light suspense'},
            'warnings': [], 'needsReview': True, 'analysisStrategy': 'pagewise-fusion',
            'source': {'type': 'comic', 'name': 'test.pdf', 'fileToken': 'token', 'pages': [1, 2]},
            'provider': 'fake', 'model': 'fake-vision', 'schemaVersion': '1h4b-v3', 'cacheHit': False,
            'batchCount': 1, 'imageProfile': 'standard', 'requestRetries': 0, 'totalRequests': 4,
            'renderMetrics': [{'page': 1, 'inputWidth': 900, 'inputHeight': 1280, 'jpegBytes': 123456},
                              {'page': 2, 'inputWidth': 900, 'inputHeight': 1280, 'jpegBytes': 123457}],
            'pageMetrics': [{'page': 1, 'dialogues': 5, 'characters': 2, 'scenes': 1},
                            {'page': 2, 'dialogues': 5, 'characters': 2, 'scenes': 1}],
            'qualitySummary': {'selectedPages': [1, 2], 'charactersDetected': 4, 'dialoguesDetected': 10,
                               'speakerUnknown': 10, 'scenesDetected': 2, 'plotEventsDetected': 1,
                               'evidenceCount': 17, 'qualityGatePassed': True},
            'fusionDuration': 0.04, 'totalDuration': 12.3}


class StagedFakeProvider:
    name = 'fake'
    enabled = True

    def __init__(self):
        self.plan_calls = 0
        self.adapt_calls = 0
        self.fail_plan = False
        self.fail_final = False
        self.invalid_evidence = False
        self.final_beat_count = None

    def get_status(self):
        return {'provider': 'fake', 'enabled': True, 'configured': True, 'model': 'fake-adapt',
                'baseUrlSafe': 'local', 'supportsVision': True, 'isLocalEndpoint': True, 'reason': None}

    def plan_adaptation(self, context, settings):
        self.plan_calls += 1
        if self.fail_plan:
            raise TimeoutError()
        evidence_ids = [item['id'] for item in context['sourceEvidence']]
        main = [item['id'] for item in context['characters'] if item['classification'] == 'main']
        beats = []
        for index in range(4):
            evidence_id = evidence_ids[min(index, len(evidence_ids) - 1)]
            beats.append({'id': f'P{index + 1}', 'summary': f'Plan beat {index + 1}',
                          'sourcePages': [1 if index < 2 else 2], 'sourceEvidenceIds': [evidence_id]})
        return {'title': 'Plan', 'premise': context['premise'], 'mainCharacters': main[:2],
                'beginning': 'Begin safely.', 'middle': 'Work together.', 'ending': 'Reach safety.',
                'conflict': 'A scary problem.', 'resolution': 'Teamwork solves it.', 'beats': beats,
                'sourceEvidenceIds': evidence_ids[:4], 'unassignedDialogue': [], 'warnings': []}

    def generate_adapted_story(self, plan, context, settings):
        self.adapt_calls += 1
        if self.fail_final:
            raise TimeoutError()
        evidence_ids = [item['id'] for item in context['sourceEvidence']]
        count = self.final_beat_count or int(settings.get('shotCount') or 6)
        chosen = 'EX999' if self.invalid_evidence else evidence_ids[0]
        beats = [{'id': f'B{index + 1}', 'summary': f'Adapted beat {index + 1}',
                  'sourcePages': [1 if index < count / 2 else 2], 'sourceEvidenceIds': [chosen]}
                 for index in range(count)]
        characters = [{'id': item['id'], 'name': item['name'], 'role': item['role']}
                      for item in context['characters'][:2]]
        return {'title': 'Adapted', 'logline': 'Children solve a problem together.',
                'summary': 'A short child-safe adaptation.', 'characters': characters,
                'scenes': [{'id': 'adapted-scene-1', 'description': 'A safe simplified scene.'}],
                'storyBeats': beats, 'ending': 'Everyone is safe.',
                'learningGoals': settings.get('educationGoals', []),
                'sourceEvidenceIds': [chosen], 'adaptationNotes': ['simplified source wording']}

    def adapt_story(self, *_):
        raise AssertionError('legacy adaptation should not run')


class StagedAdaptationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.semantic = source_semantic()
        self.settings = {'audience': '3-6', 'level': 'Pre-A1', 'fidelity': 'balanced', 'shotCount': 6,
                         'style': 'warm', 'language': 'English', 'educationGoals': ['teamwork'],
                         'preserveCharacterNames': True, 'preserveCorePlot': True, 'preserveDialogue': True,
                         'aspectRatio': '9:16'}

    def tearDown(self):
        self.tmp.cleanup()

    def test_adaptation_context_compression_and_evidence_refs(self):
        context, _, stats = build_adaptation_context(self.semantic)
        AdaptationContext.model_validate(context)
        original = len(json.dumps(self.semantic, ensure_ascii=False).encode())
        compressed = len(json.dumps(context, ensure_ascii=False).encode())
        self.assertLess(compressed, original)
        self.assertEqual(stats['dialogues'], 10)
        self.assertEqual(stats['evidence'], 17)
        self.assertNotIn('transcribed from visible speech bubble or caption', json.dumps(context, ensure_ascii=False))
        self.assertNotIn('qualitySummary', context)

    def test_dialogue_deduplication_and_ordering(self):
        context, _, _ = build_adaptation_context(self.semantic)
        texts = [item['text'] for item in context['keyDialogues']]
        self.assertEqual(texts.count('Hello!'), 1)
        source_ids = [int(item['id'][1:]) for item in context['keyDialogues']]
        self.assertEqual(source_ids, sorted(source_ids))
        by_page = {}
        for item in context['keyDialogues']:
            by_page[item['sourcePage']] = by_page.get(item['sourcePage'], 0) + 1
        self.assertTrue(all(count <= 4 for count in by_page.values()))
        self.assertTrue(context['dialogueSummary'])

    def test_character_classification(self):
        context, _, stats = build_adaptation_context(self.semantic)
        classifications = {item['id']: item['classification'] for item in context['characters'] + context['backgroundCharacters']}
        self.assertEqual(classifications['character_01'], 'main')
        self.assertEqual(classifications['character_03'], 'background')
        self.assertGreaterEqual(stats['mainCharacters'], 1)
        self.assertGreaterEqual(stats['backgroundCharacters'], 1)

    def test_unknown_speaker_preserved_in_plan(self):
        provider = StagedFakeProvider(); service = ComicAiService(provider, self.root / 'cache')
        value = service.adapt(self.semantic, self.settings)
        plan_file = next((self.root / 'cache' / 'adaptation' / 'plan').glob('*.json'))
        plan = AdaptationPlan.model_validate_json(plan_file.read_text(encoding='utf-8'))
        context, _, _ = build_adaptation_context(self.semantic)
        unknown_ids = [item['id'] for item in context['keyDialogues'] if item['speaker'] == 'unknown']
        self.assertTrue(set(unknown_ids).issubset(set(plan.unassignedDialogue)))
        self.assertTrue(value['qualitySummary']['stagedAdaptation'])

    def test_adaptation_plan_schema(self):
        provider = StagedFakeProvider()
        context, _, _ = build_adaptation_context(self.semantic)
        plan = AdaptationPlan.model_validate(provider.plan_adaptation(context, self.settings))
        self.assertGreaterEqual(len(plan.beats), 4)
        self.assertLessEqual(len(plan.beats), 8)

    def test_source_evidence_mapping_restores_original_text(self):
        provider = StagedFakeProvider(); service = ComicAiService(provider, self.root / 'cache')
        value = service.adapt(self.semantic, self.settings)
        restored = {item['evidence'] for item in value['sourceEvidence']}
        self.assertIn('transcribed from visible speech bubble or caption', restored)

    def test_plan_to_adapted_story_and_source_mapping(self):
        provider = StagedFakeProvider(); service = ComicAiService(provider, self.root / 'cache')
        value = service.adapt(self.semantic, self.settings)
        self.assertEqual(len(value['storyBeats']), 6)
        self.assertTrue(value['sourceEvidence'])
        self.assertTrue(all(item['sourcePage'] in {1, 2} for item in value['sourceEvidence']))
        self.assertEqual(value['learningGoals'], ['teamwork'])
        self.assertEqual(provider.plan_calls, 1); self.assertEqual(provider.adapt_calls, 1)

    def test_partial_cache_reuse_after_final_failure(self):
        provider = StagedFakeProvider(); provider.fail_final = True
        service = ComicAiService(provider, self.root / 'cache')
        with self.assertRaises(ComicAiError) as caught:
            service.adapt(self.semantic, self.settings)
        self.assertEqual(caught.exception.code, 'AI_REQUEST_TIMEOUT')
        self.assertEqual(provider.plan_calls, 1); self.assertEqual(provider.adapt_calls, 1)
        self.assertTrue(list((self.root / 'cache' / 'adaptation' / 'plan').glob('*.json')))
        self.assertFalse(list((self.root / 'cache' / 'adaptation' / 'story').glob('*.json')))
        provider.fail_final = False
        value = service.adapt(self.semantic, self.settings)
        self.assertEqual(provider.plan_calls, 1); self.assertEqual(provider.adapt_calls, 2)
        self.assertTrue(value['qualitySummary']['cache']['planHit'])

    def test_plan_failure_does_not_create_plan_or_story_cache(self):
        provider = StagedFakeProvider(); provider.fail_plan = True
        service = ComicAiService(provider, self.root / 'cache')
        with self.assertRaises(ComicAiError) as caught:
            service.adapt(self.semantic, self.settings)
        self.assertEqual(caught.exception.code, 'AI_REQUEST_TIMEOUT')
        self.assertFalse(list((self.root / 'cache' / 'adaptation' / 'plan').glob('*.json')))
        self.assertFalse((self.root / 'cache' / 'adaptation' / 'story').exists())

    def test_final_adapt_failure_keeps_plan_cache(self):
        provider = StagedFakeProvider(); provider.fail_final = True
        service = ComicAiService(provider, self.root / 'cache')
        with self.assertRaises(ComicAiError):
            service.adapt(self.semantic, self.settings)
        self.assertTrue(list((self.root / 'cache' / 'adaptation' / 'plan').glob('*.json')))
        self.assertFalse(list((self.root / 'cache' / 'adaptation' / 'story').glob('*.json')))

    def test_no_invented_source_ids(self):
        provider = StagedFakeProvider(); provider.invalid_evidence = True
        service = ComicAiService(provider, self.root / 'cache')
        with self.assertRaises(ComicAiError) as caught:
            service.adapt(self.semantic, self.settings)
        self.assertEqual(caught.exception.code, 'AI_RESPONSE_INVALID')

    def test_six_shot_validation(self):
        provider = StagedFakeProvider(); provider.final_beat_count = 5
        service = ComicAiService(provider, self.root / 'cache')
        with self.assertRaises(ComicAiError) as caught:
            service.adapt(self.semantic, self.settings)
        self.assertEqual(caught.exception.code, 'AI_RESPONSE_INVALID')

    def test_second_call_hits_all_three_caches(self):
        provider = StagedFakeProvider(); service = ComicAiService(provider, self.root / 'cache')
        service.adapt(self.semantic, self.settings)
        value = service.adapt(self.semantic, self.settings)
        self.assertEqual(provider.plan_calls, 1); self.assertEqual(provider.adapt_calls, 1)
        self.assertEqual(value['qualitySummary']['cache'], {'contextHit': True, 'planHit': True, 'storyHit': True})


if __name__ == '__main__':
    unittest.main()
