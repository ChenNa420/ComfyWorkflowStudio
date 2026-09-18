from __future__ import annotations

import unittest

from backend.comfy.converter import WorkflowConversionError, ui_workflow_to_prompt
from backend.workflow.analyzer import analyze_workflow, detect_workflow_format


class WorkflowAnalyzerTests(unittest.TestCase):
    def test_detects_ui_workflow_and_first_frame(self):
        workflow = {
            'nodes': [
                {
                    'id': 1,
                    'type': 'PixaromaLoadImageMini',
                    'title': '1. Load Image - First Frame',
                    'inputs': [],
                    'outputs': [{'name': 'image', 'type': 'IMAGE', 'links': [1]}],
                    'properties': {'cnr_id': 'ComfyUI-Pixaroma'},
                    'widgets_values': ['first.png', 'image', ''],
                },
                {
                    'id': 2,
                    'type': 'PixaromaPrompt',
                    'title': 'Add a prompt',
                    'inputs': [],
                    'outputs': [{'name': 'text', 'type': 'STRING', 'links': []}],
                    'properties': {'cnr_id': 'ComfyUI-Pixaroma', 'promptState': {'text': 'hello'}},
                    'widgets_values': [''],
                },
                {
                    'id': 3,
                    'type': 'PixaromaSaveMp4',
                    'inputs': [],
                    'outputs': [],
                    'properties': {'cnr_id': 'ComfyUI-Pixaroma'},
                    'widgets_values': [24, 'Video', 'save', False, ''],
                },
                {
                    'id': 4,
                    'type': 'KSampler',
                    'inputs': [],
                    'outputs': [{'name': 'LATENT', 'links': []}],
                    'properties': {'cnr_id': 'comfy-core'},
                    'widgets_values': [1234, 'randomize', 20, 1.0, 'euler'],
                },
            ],
            'links': [],
        }
        self.assertEqual(detect_workflow_format(workflow), 'ui-workflow')
        result = analyze_workflow(workflow, 'MiniMax H3 - Image to video FF.json')
        self.assertEqual(result['category'], 'image-to-video')
        first_frame = next(item for item in result['inputs'] if item['type'] == 'image')
        self.assertEqual(first_frame['purpose'], 'video-start-frame')
        self.assertTrue(any(item['type'] == 'video' for item in result['outputs']))
        self.assertIn('ComfyUI-Pixaroma', [item['name'] for item in result['dependencies']['customNodes']])
        seed = next(item for item in result['parameters'] if item['key'] == 'seed')
        self.assertEqual(seed['default'], 1234)
        self.assertEqual(seed['mapping'], {'nodeId': '4', 'field': 'seed'})

    def test_detects_api_workflow(self):
        workflow = {
            '1': {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'model.safetensors'}},
            '2': {'class_type': 'SaveImage', 'inputs': {'images': ['1', 0]}},
            '3': {'class_type': 'KSampler', 'inputs': {'seed': 4321}},
        }
        self.assertEqual(detect_workflow_format(workflow), 'api-workflow')
        result = analyze_workflow(workflow, 'Example.json')
        self.assertIn('model.safetensors', [item['name'] for item in result['dependencies']['models']])
        self.assertEqual(result['parameters'][0]['mapping'], {'nodeId': '3', 'field': 'seed'})


class WorkflowConverterTests(unittest.TestCase):
    def test_maps_links_and_skips_seed_control_widget(self):
        workflow = {
            'nodes': [
                {'id': 1, 'type': 'ModelLoader', 'mode': 0, 'inputs': [], 'outputs': [{'name': 'MODEL', 'links': [10]}], 'widgets_values': ['model.safetensors'], 'properties': {}},
                {
                    'id': 2,
                    'type': 'Sampler',
                    'mode': 0,
                    'inputs': [{'name': 'model', 'link': 10}],
                    'outputs': [{'name': 'LATENT', 'links': []}],
                    'widgets_values': [1234, 'randomize', 20, 1.0, 'euler'],
                    'properties': {},
                },
            ],
            'links': [[10, 1, 0, 2, 0, 'MODEL']],
        }
        object_info = {
            'ModelLoader': {'input': {'required': {'model_name': [['model.safetensors'], {}]}}},
            'Sampler': {'input': {'required': {
                'model': ['MODEL', {}],
                'seed': ['INT', {'default': 0}],
                'steps': ['INT', {'default': 20}],
                'cfg': ['FLOAT', {'default': 1.0}],
                'sampler_name': [['euler', 'dpmpp'], {}],
            }}},
        }
        prompt = ui_workflow_to_prompt(workflow, object_info)
        self.assertEqual(prompt['2']['inputs']['model'], ['1', 0])
        self.assertEqual(prompt['2']['inputs']['seed'], 1234)
        self.assertEqual(prompt['2']['inputs']['steps'], 20)
        self.assertEqual(prompt['2']['inputs']['sampler_name'], 'euler')

    def test_optional_connection_does_not_consume_width_height_widgets(self):
        workflow = {
            'nodes': [
                {
                    'id': 222,
                    'type': 'MiniMaxH3ImageToVideo',
                    'mode': 0,
                    'inputs': [
                        {'name': 'first_frame', 'link': 11},
                        {'name': 'last_frame', 'link': None},
                    ],
                    'outputs': [{'name': 'video', 'links': []}],
                    'widgets_values': ['', 1344, 768, 73],
                    'properties': {},
                }
            ],
            'links': [[11, 236, 0, 222, 0, 'IMAGE']],
        }
        object_info = {
            'MiniMaxH3ImageToVideo': {
                'input': {
                    'required': {
                        'first_frame': ['IMAGE', {}],
                        'width': ['INT', {'default': 1344}],
                        'height': ['INT', {'default': 768}],
                        'length': ['INT', {'default': 73}],
                    },
                    'optional': {'last_frame': ['IMAGE', {}]},
                }
            }
        }
        prompt = ui_workflow_to_prompt(workflow, object_info)
        inputs = prompt['222']['inputs']
        self.assertEqual(inputs['first_frame'], ['236', 0])
        self.assertNotIn('last_frame', inputs)
        self.assertEqual(inputs['width'], 1344)
        self.assertEqual(inputs['height'], 768)
        self.assertEqual(inputs['length'], 73)

    def test_rejects_missing_required_node_type(self):
        workflow = {
            'nodes': [{'id': 1, 'type': 'MissingCustomNode', 'mode': 0, 'inputs': [], 'outputs': [{'name': 'x', 'links': [1]}], 'widgets_values': [], 'properties': {}}],
            'links': [],
        }
        with self.assertRaises(WorkflowConversionError):
            ui_workflow_to_prompt(workflow, {})


if __name__ == '__main__':
    unittest.main()
