import tempfile
import unittest
from pathlib import Path

from backend.ai.episode_planning import (
    build_episode_shot_plan, compact_shot_context, duplicate_flags,
    plan_quality, validate_plan_quality,
)
from backend.ai.models import Episode
from backend.ai.service import ComicAiError, ComicAiService


def grounded_story(narrative_type='narrative_story', recommended=5):
    return {
        'title': 'Grounded Story', 'logline': 'Children notice a light.', 'summary': 'A source-grounded story.',
        'characters': [{'id': 'C1', 'name': 'Child', 'role': 'child'}],
        'scenes': [{'id': 'S1', 'description': 'Moonlit garden', 'sourcePages': [4]},
                   {'id': 'S2', 'description': 'House doorway', 'sourcePages': [5, 6]}],
        'storyBeats': [
            {'id': 'B1', 'summary': 'The children discuss the garden renovation.', 'sourcePages': [4], 'sourceEvidenceIds': ['E1', 'E2']},
            {'id': 'B2', 'summary': 'They notice an unusual light inside.', 'sourcePages': [5], 'sourceEvidenceIds': ['E3']},
            {'id': 'B3', 'summary': 'Mrs Creecher leaves while they remain.', 'sourcePages': [6], 'sourceEvidenceIds': ['E4']},
        ],
        'sourceEvidence': [
            {'id': 'E1', 'sourcePage': 4, 'evidence': 'The group stands in the moonlit garden.'},
            {'id': 'E2', 'sourcePage': 4, 'evidence': 'They discuss changing the room.'},
            {'id': 'E3', 'sourcePage': 5, 'evidence': 'A light appears inside the house.'},
            {'id': 'E4', 'sourcePage': 6, 'evidence': 'Mrs Creecher walks away.'},
            {'id': 'EX', 'sourcePage': 4, 'evidence': 'Unrelated page detail.'},
        ],
        'keyDialogues': [
            {'id': 'D1', 'sourcePage': 4, 'sceneId': 'S1', 'speaker': 'unknown', 'text': 'What shall we change?', 'dialogueSource': 'source', 'sourceEvidenceIds': ['E1']},
            {'id': 'D2', 'sourcePage': 4, 'sceneId': 'S1', 'speaker': 'C1', 'text': 'Look at the room.', 'dialogueSource': 'source', 'sourceEvidenceIds': ['E2']},
            {'id': 'D3', 'sourcePage': 5, 'sceneId': 'S2', 'speaker': 'C1', 'text': 'What is that light?', 'dialogueSource': 'source', 'sourceEvidenceIds': ['E3']},
        ],
        'ending': 'They keep watching.', 'learningGoals': [], 'adaptationNotes': [],
        'narrativeType': narrative_type, 'recommendedShotCount': recommended,
    }


def settings(count=5):
    return {'autoShotCount': True, 'shotCount': count, 'duration': 30, 'level': 'Pre-A1', 'age': '3-6',
            'aspectRatio': '9:16', 'source': {'type': 'comic', 'name': 'beano.pdf', 'fileToken': 't', 'pages': [4, 5, 6]}}


class Provider:
    enabled = True
    def __init__(self): self.calls = 0
    def get_status(self):
        return {'provider': 'fake', 'enabled': True, 'configured': True, 'model': 'grounded', 'isLocalEndpoint': True}
    def generate_episode_shot(self, slot, context, request_settings):
        self.calls += 1
        dialogue = slot.get('assignedDialogues', [])
        return {'title': f"Shot {slot['id']}", 'speaker': None, 'english': '', 'chinese': '',
                'imagePrompt': slot['subFocus'], 'videoPrompt': slot['purpose'], 'negativePrompt': 'drift'}


class GroundedShotQualityTests(unittest.TestCase):
    def plan(self, story=None): return build_episode_shot_plan(story or grounded_story(), settings())

    def test_exact_beat_evidence_mapping(self):
        plan = self.plan(); self.assertEqual(plan['shots'][0]['evidenceMappingMode'], 'exact_beat')
        self.assertEqual([x for s in plan['shots'][:2] for x in s['evidenceIds']], ['E1', 'E2'])

    def test_page_fallback_only_when_beat_evidence_missing(self):
        value = grounded_story(); value['storyBeats'][0]['sourceEvidenceIds'] = []
        plan = self.plan(value); self.assertEqual(plan['shots'][0]['evidenceMappingMode'], 'page_fallback')
        self.assertIn('EX', [x for s in plan['shots'][:2] for x in s['evidenceIds']])

    def test_no_invented_evidence(self):
        allowed = {x['id'] for x in grounded_story()['sourceEvidence']}
        self.assertTrue({x for s in self.plan()['shots'] for x in s['evidenceIds']} <= allowed)

    def test_split_beat_gets_distinct_subfocus(self):
        shots = self.plan()['shots'][:2]; self.assertNotEqual(shots[0]['subFocus'], shots[1]['subFocus'])
        self.assertEqual([(s['sequenceIndex'], s['sequenceTotal']) for s in shots], [(1, 2), (2, 2)])

    def test_dialogue_distribution_preserves_order(self):
        self.assertEqual([x for s in self.plan()['shots'] for x in s['dialogueIds']], ['D1', 'D2', 'D3'])

    def test_dialogue_is_not_duplicated_across_split_shots(self):
        ids = [x for s in self.plan()['shots'] for x in s['dialogueIds']]; self.assertEqual(len(ids), len(set(ids)))

    def test_future_beat_leakage_forbidden(self):
        plan = self.plan(); context = compact_shot_context(grounded_story(), plan['shots'][0])
        self.assertEqual([x['id'] for x in context['storyBeats']], ['B1'])
        self.assertNotIn('light inside', str(context).lower())

    def test_beat_coverage_complete(self):
        self.assertEqual(plan_quality(grounded_story(), self.plan())['beatCoverage'], {'covered': 3, 'total': 3, 'missingBeatIds': []})

    def test_missing_beat_rejected(self):
        plan = self.plan(); plan['shots'] = [s for s in plan['shots'] if 'B3' not in s['beatIds']]; plan['shotCount'] = len(plan['shots'])
        with self.assertRaisesRegex(ValueError, 'EPISODE_MISSING_STORY_BEAT'): validate_plan_quality(grounded_story(), plan)

    def test_source_page_order_preserved(self): self.assertTrue(plan_quality(grounded_story(), self.plan())['sourcePageOrderPreserved'])

    def test_narrative_story_ordering(self): self.assertTrue(plan_quality(grounded_story(), self.plan())['storyOrderPreserved'])

    def test_educational_process_ordering(self):
        value = grounded_story('educational_process', 5)
        value['storyBeats'] = [{'id': f'P{i}', 'summary': name, 'sourcePages': [4 + min(i // 3, 2)], 'sourceEvidenceIds': []}
                               for i, name in enumerate(('plough', 'harrow', 'roller', 'seed drill', 'mow', 'bale', 'harvest', 'transport'))]
        plan = build_episode_shot_plan(value, settings()); flattened = [b for s in plan['shots'] for b in s['beatIds']]
        self.assertEqual(flattened, [f'P{i}' for i in range(8)])
        self.assertTrue(all('conflict' not in s['purpose'].lower() for s in plan['shots']))

    def test_duplicate_detector_warning(self):
        plan = self.plan(); plan['shots'][1]['purpose'] = plan['shots'][0]['purpose']; plan['shots'][1]['evidenceIds'] = plan['shots'][0]['evidenceIds']; plan['shots'][1]['dialogueIds'] = plan['shots'][0]['dialogueIds']
        self.assertTrue(duplicate_flags(plan)[1])

    def test_distinct_purpose_generation(self):
        purposes = [s['purpose'] for s in self.plan()['shots']]; self.assertEqual(len(purposes), len(set(purposes)))

    def test_unknown_speaker_remains_unresolved(self):
        first = self.plan()['shots'][0]['assignedDialogues'][0]; self.assertEqual(first['speaker'], 'unknown')

    def test_cache_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = Provider(); service = ComicAiService(provider, Path(tmp))
            first = service.episode(grounded_story(), settings()); second = service.episode(grounded_story(), settings())
            self.assertEqual(provider.calls, 5); self.assertEqual(second['qualitySummary']['cache']['shotHits'], 5)
            self.assertFalse(first['qualitySummary']['cache']['planHit'])

    def test_existing_deterministic_shot_count_unchanged(self): self.assertEqual(len(self.plan()['shots']), 5)

    def test_episode_remains_schema_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            value = ComicAiService(Provider(), Path(tmp)).episode(grounded_story(), settings())
            Episode.model_validate(value); self.assertEqual(value['qualitySummary']['beatCoverage']['covered'], 3)


if __name__ == '__main__': unittest.main()
