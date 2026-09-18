import copy
import unittest

from backend.ai.production_handoff import ProductionPlan, build_production_plan


def episode():
    characters = [
        {'id': 'C1', 'name': 'Jem', 'description': 'child detective', 'appearance': 'short dark hair',
         'clothing': 'blue jacket', 'bodyType': 'child', 'hairOrFur': 'short dark hair',
         'accessories': ['notebook'], 'prompt': 'Jem, short dark hair, blue jacket', 'negativePrompt': 'identity drift'},
        {'id': 'C2', 'name': 'Mia', 'description': 'friend', 'appearance': 'curly hair',
         'clothing': 'red jumper', 'bodyType': 'child', 'hairOrFur': 'curly hair',
         'accessories': [], 'prompt': 'Mia, curly hair, red jumper', 'negativePrompt': 'identity drift'},
    ]
    shots = []
    values = [
        (1, 'Opening', ['B1'], 'Establish Jem and Mia in the moonlit garden', [4], 'E1', 'D1',
         'Jem and Mia in the moonlit garden, wide shot, comic style', 'Jem and Mia discuss the room while leaves move, fixed camera'),
        (2, 'Discussion', ['B1'], 'Focus on the next renovation detail', [4], 'E2', 'D2',
         'Jem and Mia examine the room plan, medium shot, comic style', 'Jem points to the plan while Mia looks, slow camera pan'),
        (3, 'Light', ['B2'], 'Shift attention to the unusual light in the house', [5], 'E3', 'D3',
         'Jem notices an unusual light by the house, close-up, comic style', 'Jem turns toward the light as curtains move, fixed camera'),
    ]
    for sid, title, beats, focus, pages, evidence, dialogue, image, video in values:
        shots.append({'id': sid, 'title': title, 'speaker': None, 'english': '', 'chinese': '', 'duration': 6,
                      'imagePrompt': image, 'videoPrompt': video, 'negativePrompt': 'text artifacts',
                      'sourcePages': pages, 'sourceEvidence': [{'id': evidence, 'sourcePage': pages[0], 'evidence': focus}],
                      'beatIds': beats, 'subFocus': focus, 'evidenceIds': [evidence], 'dialogueIds': [dialogue],
                      'evidenceMappingMode': 'exact_beat', 'sequenceIndex': sid if sid < 3 else 1,
                      'sequenceTotal': 2 if sid < 3 else 1, 'redundantShot': False, 'dialogueSource': 'none'})
    return {'title': 'Mystery', 'level': 'Pre-A1', 'age': '3-8', 'duration': 18, 'aspectRatio': '9:16',
            'characters': ['Jem', 'Mia'], 'characterDefinitions': characters,
            'scenes': [{'id': 'S1', 'description': 'moonlit garden', 'location': 'garden', 'sourcePages': [4]},
                       {'id': 'S2', 'description': 'house exterior', 'location': 'house', 'sourcePages': [5]}],
            'shots': shots, 'source': {'type': 'comic', 'name': 'beano.pdf', 'fileToken': 't', 'pages': [4, 5]}}


class GroundedProductionHandoffTests(unittest.TestCase):
    def plan(self, value=None): return build_production_plan(value or episode())

    def test_episode_to_production_plan(self): self.assertEqual(self.plan()['episodeTitle'], 'Mystery')
    def test_exact_shot_count_preserved(self): self.assertEqual(len(self.plan()['shots']), 3)
    def test_shot_ids_preserved(self): self.assertEqual([s['shotId'] for s in self.plan()['shots']], [1, 2, 3])
    def test_beat_refs_preserved(self): self.assertEqual(self.plan()['shots'][0]['storyContext']['beatIds'], ['B1'])
    def test_source_pages_preserved(self): self.assertEqual([s['storyContext']['sourcePages'] for s in self.plan()['shots']], [[4], [4], [5]])
    def test_evidence_preserved(self):
        before = episode()['shots'][0]['sourceEvidence']; after = self.plan()['shots'][0]['storyContext']['sourceEvidence']
        self.assertEqual(after, before)
    def test_character_ids_valid(self):
        valid = {p['id'] for p in self.plan()['characters']}
        self.assertTrue(all(set(s['characterRefs']) <= valid for s in self.plan()['shots']))
    def test_stable_character_profile_reuse(self):
        plan = self.plan(); self.assertEqual(len({p['id'] for p in plan['characters']}), len(plan['characters']))
        self.assertEqual(plan['characters'][0]['prompt'], 'Jem, short dark hair, blue jacket')
    def test_same_scene_continuity(self):
        continuity = self.plan()['shots'][1]['continuity']; self.assertEqual(continuity['strength'], 'strong')
        self.assertEqual(continuity['previousShotId'], 1)
    def test_scene_transition_continuity(self):
        continuity = self.plan()['shots'][2]['continuity']; self.assertEqual(continuity['strength'], 'transition')
        self.assertEqual(continuity['locationContinuity'], 'transition')
    def test_no_future_event_leakage(self):
        value = episode(); value['shots'][0]['videoPrompt'] += '. ' + value['shots'][2]['subFocus']
        plan = self.plan(value); self.assertEqual(plan['shots'][0]['status'], 'BLOCKED')
        self.assertIn('future-event leakage', plan['shots'][0]['warnings'])
    def test_no_invented_character(self):
        value = episode(); value['shots'][0]['imagePrompt'] += ' character_999 enters'
        shot = self.plan(value)['shots'][0]; self.assertEqual(shot['status'], 'BLOCKED')
        self.assertIn('invented character id', shot['warnings'])
    def test_dialogue_source_none_forbids_invented_dialogue(self):
        value = episode(); value['shots'][0]['videoPrompt'] = 'Jem says “We solved it!” The leaves move.'
        shot = self.plan(value)['shots'][0]
        self.assertNotIn('says', shot['production']['videoPrompt'].lower())
        self.assertIn('removed ungrounded spoken dialogue', shot['warnings'])
    def test_duration_at_most_ten(self): self.assertTrue(all(s['production']['duration'] <= 10 for s in self.plan()['shots']))
    def test_image_prompt_readiness(self):
        shot = self.plan()['shots'][0]; self.assertTrue(shot['imagePromptReadiness']['ready'])
        self.assertIn('9:16 framing', shot['production']['imagePrompt'])
    def test_video_prompt_readiness(self):
        shot = self.plan()['shots'][0]; self.assertTrue(shot['videoPromptReadiness']['ready'])
        self.assertIn('6-second duration', shot['production']['videoPrompt'])
    def test_ready_gate(self): self.assertTrue(all(s['status'] == 'READY' for s in self.plan()['shots']))
    def test_needs_review_gate(self):
        value = episode(); value['characterDefinitions'][0]['appearance'] = ''; value['characterDefinitions'][0]['prompt'] = ''
        shot = self.plan(value)['shots'][0]; self.assertEqual(shot['status'], 'NEEDS_REVIEW')
    def test_blocked_gate(self):
        value = episode(); value['shots'][0]['imagePrompt'] = ''
        self.assertEqual(self.plan(value)['shots'][0]['status'], 'BLOCKED')
    def test_episode_production_readiness(self):
        plan = self.plan(); ProductionPlan.model_validate(plan)
        self.assertEqual(plan['productionReadiness']['blockedShots'], 0)
        self.assertTrue(plan['productionReadiness']['readyForStoryboard'])


if __name__ == '__main__': unittest.main()
