from __future__ import annotations

import unittest

from backend.comfy.runtime import _apply_dynamic_duration, _duration_plan


class RuntimeDurationTests(unittest.TestCase):
    def test_uses_workflow_duration_state_for_minimax_style_timing(self):
        source = {
            'nodes': [
                {
                    'id': 10,
                    'type': 'PixaromaDuration',
                    'properties': {
                        'durationState': {
                            'step': 24,
                            'plus': 4,
                        }
                    },
                }
            ]
        }

        self.assertEqual(_duration_plan(5, source)['frames'], 124)
        self.assertEqual(_duration_plan(7, source)['frames'], 172)
        self.assertEqual(_duration_plan(7.5, source)['frames'], 184)
        self.assertEqual(_duration_plan(8, source)['frames'], 196)

    def test_updates_seconds_and_all_video_frame_fields(self):
        source = {
            'nodes': [
                {
                    'id': 10,
                    'type': 'PixaromaDuration',
                    'properties': {'durationState': {'step': 24, 'plus': 4}},
                }
            ]
        }
        prompt = {
            '10': {'class_type': 'DurationNode', 'inputs': {'duration': 5.0}},
            '20': {'class_type': 'Generator', 'inputs': {'length': 124, 'frames': 124}},
            '30': {'class_type': 'Timeline', 'inputs': {'total_frames': 124, 'frame_count': 124}},
            '40': {'class_type': 'Other', 'inputs': {'width': 1536, 'height': 864, 'model': ['1', 0]}},
        }

        plan = _apply_dynamic_duration(prompt, source, 8)

        self.assertEqual(plan['frames'], 196)
        self.assertEqual(prompt['10']['inputs']['duration'], 8.0)
        self.assertEqual(prompt['20']['inputs']['length'], 196)
        self.assertEqual(prompt['20']['inputs']['frames'], 196)
        self.assertEqual(prompt['30']['inputs']['total_frames'], 196)
        self.assertEqual(prompt['30']['inputs']['frame_count'], 196)
        self.assertEqual(prompt['40']['inputs']['width'], 1536)
        self.assertEqual(prompt['40']['inputs']['height'], 864)
        self.assertEqual(prompt['40']['inputs']['model'], ['1', 0])

    def test_minimax_recipe_uses_phase1d_padding_and_replaces_linked_length(self):
        source = {
            'nodes': [{
                'properties': {
                    'durationState': {
                        'fps': 24,
                        'plus': 5,
                        'recipeName': 'MiniMax H3',
                    },
                },
            }],
        }
        prompt = {
            '222': {'class_type': 'MiniMaxH3ImageToVideo', 'inputs': {'length': ['238', 0]}},
            '228': {'class_type': 'PixaromaSaveMp4', 'inputs': {'video_frames': ['226', 0]}},
        }

        plan = _apply_dynamic_duration(prompt, source, 8)

        self.assertEqual(plan['frames'], 196)
        self.assertEqual(prompt['222']['inputs']['length'], 196)
        self.assertEqual(prompt['228']['inputs']['video_frames'], ['226', 0])

    def test_fps_override_controls_frame_count(self):
        source = {
            'nodes': [
                {
                    'id': 10,
                    'properties': {'durationState': {'step': 24, 'plus': 4}},
                }
            ]
        }

        plan = _duration_plan(6, source, fps_override=30)
        self.assertEqual(plan['fps'], 30)
        self.assertEqual(plan['frames'], 184)

    def test_rejects_zero_or_negative_duration(self):
        with self.assertRaises(Exception):
            _duration_plan(0, {})
        with self.assertRaises(Exception):
            _duration_plan(-1, {})


if __name__ == '__main__':
    unittest.main()
