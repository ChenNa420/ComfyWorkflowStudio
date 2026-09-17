import tempfile
import unittest
from pathlib import Path

from backend.ai.episode_planning import build_episode_shot_plan, resolve_shot_count
from backend.ai.models import Episode, EpisodeShotPlan
from backend.ai.service import ComicAiError, ComicAiService


def story(beat_count=4, recommended=5):
    beats = []
    for index in range(beat_count):
        page = 1 + min(index, 2)
        beats.append({'id': f'B{index + 1}', 'summary': f'Beat {index + 1} action',
                      'sourcePages': [page], 'sourceEvidenceIds': [f'E{index + 1}']})
    return {'title': 'Test Story', 'logline': 'Friends solve a mystery.', 'summary': 'A grounded story.',
            'characters': [{'id': 'character_01', 'name': 'Hero', 'role': 'child', 'pages': [1, 2, 3]},
                           {'id': 'character_02', 'name': 'Friend', 'role': 'child', 'pages': [1, 2, 3]}],
            'scenes': [{'id': 'S1', 'summary': 'Room', 'sourcePages': [1]}],
            'storyBeats': beats, 'ending': 'Safe ending.', 'learningGoals': [],
            'sourceEvidence': [{'sourcePage': page, 'evidence': f'fact page {page}'} for page in (1, 2, 3)],
            'adaptationNotes': [], 'recommendedShotCount': recommended}


def settings(count=6, auto=True, duration=30):
    return {'shotCount': count, 'autoShotCount': auto, 'duration': duration, 'level': 'Pre-A1',
            'age': '3-6', 'aspectRatio': '9:16',
            'source': {'type': 'comic', 'name': 'comic.pdf', 'fileToken': 'token', 'pages': [1, 2, 3]}}


class ShotProvider:
    enabled = True
    def __init__(self, fail_shot=None, speaker='character_01', override=False):
        self.calls = []
        self.fail_shot = fail_shot
        self.speaker = speaker
        self.override = override

    def get_status(self):
        return {'provider': 'fake', 'enabled': True, 'configured': True, 'model': 'fake-shot',
                'baseUrlSafe': 'local', 'supportsVision': True, 'isLocalEndpoint': True, 'reason': None}

    def generate_episode_shot(self, slot, context, request_settings):
        self.calls.append(slot['id'])
        if self.fail_shot == slot['id']:
            self.fail_shot = None
            raise TimeoutError('one shot timed out')
        value = {'title': f"Shot {slot['id']}", 'speaker': self.speaker,
                 'english': 'We can help.', 'chinese': '我们能帮忙。',
                 'imagePrompt': f"Image for {slot['purpose']}",
                 'videoPrompt': f"Video for {slot['purpose']}", 'negativePrompt': 'identity drift'}
        if self.override:
            value.update({'id': 999, 'sourcePages': [999],
                          'sourceEvidence': [{'sourcePage': 999, 'evidence': 'invented'}]})
        return value


class EpisodeShotPlanningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_auto_shot_count_five(self):
        self.assertEqual(resolve_shot_count(story(recommended=5), settings()), 5)

    def test_auto_shot_count_seven(self):
        self.assertEqual(resolve_shot_count(story(recommended=7), settings()), 7)

    def test_fixed_shot_counts(self):
        for count in (6, 10, 12):
            self.assertEqual(resolve_shot_count(story(), settings(count, False)), count)

    def test_beat_equals_shot(self):
        plan = build_episode_shot_plan(story(4, 4), settings(auto=True))
        self.assertEqual([item['beatIds'] for item in plan['shots']], [['B1'], ['B2'], ['B3'], ['B4']])

    def test_beat_split_preserves_order(self):
        plan = build_episode_shot_plan(story(4, 7), settings(auto=True))
        flattened = [item['beatIds'][0] for item in plan['shots']]
        self.assertEqual(flattened, sorted(flattened, key=lambda value: int(value[1:])))
        self.assertEqual(len(flattened), 7)

    def test_adjacent_beats_merge_without_loss(self):
        plan = build_episode_shot_plan(story(8, 5), settings(auto=True))
        self.assertEqual([beat for shot in plan['shots'] for beat in shot['beatIds']], [f'B{x}' for x in range(1, 9)])
        self.assertTrue(any(len(item['beatIds']) > 1 for item in plan['shots']))

    def test_ids_are_continuous_and_exact_n(self):
        plan = build_episode_shot_plan(story(4, 9), settings(auto=True))
        EpisodeShotPlan.model_validate(plan)
        self.assertEqual([item['id'] for item in plan['shots']], list(range(1, 10)))

    def test_duration_is_bounded_and_totals_target(self):
        plan = build_episode_shot_plan(story(4, 5), settings(duration=37))
        durations = [item['targetDuration'] for item in plan['shots']]
        self.assertTrue(all(0 < value <= 10 for value in durations))
        self.assertAlmostEqual(sum(durations), 37)

    def test_duration_caps_impossible_total(self):
        plan = build_episode_shot_plan(story(4, 5), settings(duration=90))
        self.assertEqual(sum(item['targetDuration'] for item in plan['shots']), 50)

    def test_invalid_speaker_becomes_null(self):
        provider = ShotProvider(speaker='not-a-character')
        value = ComicAiService(provider, self.root).episode(story(), settings())
        self.assertTrue(all(item['speaker'] is None for item in value['shots']))
        self.assertEqual(value['qualitySummary']['invalidSpeakersNormalized'], 5)

    def test_group_speaker_becomes_null(self):
        value = ComicAiService(ShotProvider(speaker='Hero, Friend'), self.root).episode(story(), settings())
        self.assertTrue(all(item['speaker'] is None for item in value['shots']))

    def test_single_character_name_maps_to_id(self):
        value = ComicAiService(ShotProvider(speaker='Hero'), self.root).episode(story(), settings())
        self.assertTrue(all(item['speaker'] == 'character_01' for item in value['shots']))

    def test_ai_cannot_override_ids_pages_or_evidence(self):
        value = ComicAiService(ShotProvider(override=True), self.root).episode(story(), settings())
        self.assertEqual([item['id'] for item in value['shots']], [1, 2, 3, 4, 5])
        self.assertTrue(all(999 not in item['sourcePages'] for item in value['shots']))
        self.assertTrue(all(e['sourcePage'] != 999 for item in value['shots'] for e in item['sourceEvidence']))

    def test_no_source_mapping_outside_episode_pages(self):
        value = ComicAiService(ShotProvider(), self.root).episode(story(), settings())
        Episode.model_validate(value)
        self.assertTrue(all(page in {1, 2, 3} for shot in value['shots'] for page in shot['sourcePages']))

    def test_exact_dynamic_counts_four_through_twelve(self):
        for count in range(4, 13):
            root = self.root / str(count)
            value = ComicAiService(ShotProvider(), root).episode(story(recommended=count), settings())
            self.assertEqual(len(value['shots']), count)

    def test_fixed_mode_uses_same_planner(self):
        for count in (6, 10, 12):
            value = ComicAiService(ShotProvider(), self.root / f'fixed-{count}').episode(story(), settings(count, False))
            self.assertEqual(value['qualitySummary']['resolvedShotCount'], count)
            self.assertTrue(value['qualitySummary']['deterministicShotPlan'])

    def test_second_run_uses_all_shot_caches(self):
        provider = ShotProvider(); service = ComicAiService(provider, self.root)
        first = service.episode(story(), settings())
        second = service.episode(story(), settings())
        self.assertEqual(provider.calls, [1, 2, 3, 4, 5])
        self.assertEqual(first['qualitySummary']['cache']['shotMisses'], 5)
        self.assertEqual(second['qualitySummary']['cache']['shotHits'], 5)

    def test_only_failed_shot_retries(self):
        provider = ShotProvider(fail_shot=3); service = ComicAiService(provider, self.root)
        with self.assertRaises(ComicAiError) as caught:
            service.episode(story(), settings())
        self.assertEqual(caught.exception.code, 'AI_REQUEST_TIMEOUT')
        value = service.episode(story(), settings())
        self.assertEqual(provider.calls, [1, 2, 3, 3, 4, 5])
        self.assertEqual(value['qualitySummary']['cache']['shotHits'], 2)

    def test_episode_schema_validation_and_dialogue_source(self):
        value = ComicAiService(ShotProvider(), self.root).episode(story(), settings())
        Episode.model_validate(value)
        self.assertTrue(all(item['dialogueSource'] == 'adapted' for item in value['shots']))


if __name__ == '__main__':
    unittest.main()
