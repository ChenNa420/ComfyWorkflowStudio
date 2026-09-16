from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.models import WorkflowManifest
from backend.workflow.preflight import (
    PREFLIGHT_BLOCKED,
    PREFLIGHT_CERTIFIED,
    PREFLIGHT_NEEDS_REVIEW,
    PREFLIGHT_OFFLINE,
    preflight_one,
)


class Phase1G3PreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.package = self.root / 'wf'
        self.package.mkdir()
        self.manifest_path = self.package / 'manifest.json'
        self.manifest_path.write_text('{}', encoding='utf-8')
        self.source_path = self.package / 'workflow-api.json'
        self.source_path.write_text(
            json.dumps(
                {
                    '10': {'class_type': 'LoadImage', 'inputs': {'image': 'placeholder.png'}},
                    '20': {'class_type': 'VideoSampler', 'inputs': {'prompt': 'move', 'seed': 1}},
                    '30': {'class_type': 'SaveVideo', 'inputs': {'video': ['20', 0]}},
                }
            ),
            encoding='utf-8',
        )
        self.object_info = {
            'LoadImage': {'input': {'required': {'image': [['placeholder.png'], {}]}}, 'output_node': False},
            'VideoSampler': {
                'input': {'required': {'prompt': ['STRING', {}], 'seed': ['INT', {'default': 1}]}},
                'output_node': False,
            },
            'SaveVideo': {'input': {'required': {'video': ['VIDEO', {}]}}, 'output_node': True},
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def manifest(self) -> WorkflowManifest:
        return WorkflowManifest.model_validate(
            {
                'schemaVersion': '1.0',
                'workflowId': 'wf',
                'name': 'Video Workflow',
                'category': 'image-to-video',
                'description': 'Preflight test workflow',
                'capabilities': ['image-to-video'],
                'inputs': [
                    {
                        'key': 'first-frame',
                        'label': '首帧',
                        'type': 'image',
                        'required': True,
                        'purpose': 'video-start-frame',
                        'mapping': {'nodeId': '10', 'field': 'image'},
                    }
                ],
                'parameters': [
                    {
                        'key': 'prompt',
                        'label': 'Prompt',
                        'type': 'textarea',
                        'default': 'move',
                        'mapping': {'nodeId': '20', 'field': 'prompt'},
                    },
                    {
                        'key': 'seed',
                        'label': 'Seed',
                        'type': 'seed',
                        'default': -1,
                        'mapping': {'nodeId': '20', 'field': 'seed'},
                    },
                ],
                'outputs': [
                    {'key': 'video', 'type': 'video', 'format': 'mp4', 'mapping': {'nodeId': '30'}}
                ],
                'dependencies': {'models': [], 'customNodes': []},
                'runtime': {
                    'executionMode': 'serial',
                    'durationPolicy': 'none',
                    'retryUnknown': False,
                    'preserveOriginalWorkflow': True,
                },
            }
        )

    def row(self):
        return {'api_workflow_path': str(self.source_path), 'original_path': str(self.source_path), 'enabled': 1}

    def test_certifies_dependency_ready_prompt_without_submitting(self):
        result = preflight_one(
            self.manifest(),
            self.manifest_path,
            db_row=self.row(),
            dependency={'status': 'READY'},
            object_info=self.object_info,
        )
        self.assertEqual(result['status'], PREFLIGHT_CERTIFIED)
        self.assertEqual(result['sourceFormat'], 'api-workflow')
        self.assertEqual(result['promptNodes'], 3)
        self.assertEqual(result['detectedOutputNodes'], ['30'])
        self.assertEqual(result['errors'], [])
        self.assertFalse(result['writeMode'])
        self.assertFalse(result['submitsPrompt'])

    def test_missing_required_input_mapping_needs_review(self):
        payload = self.manifest().model_dump(mode='json')
        payload['inputs'][0]['mapping'] = {}
        result = preflight_one(
            WorkflowManifest.model_validate(payload),
            self.manifest_path,
            db_row=self.row(),
            dependency={'status': 'READY'},
            object_info=self.object_info,
        )
        self.assertEqual(result['status'], PREFLIGHT_NEEDS_REVIEW)
        self.assertIn('REQUIRED_INPUT_MAPPING_MISSING', {item['code'] for item in result['errors']})

    def test_missing_dependency_blocks_before_runtime_certification(self):
        result = preflight_one(
            self.manifest(),
            self.manifest_path,
            db_row=self.row(),
            dependency={'status': 'MISSING_DEPENDENCIES'},
            object_info=self.object_info,
        )
        self.assertEqual(result['status'], PREFLIGHT_BLOCKED)
        self.assertEqual(result['sourcePath'], None)
        self.assertIn('MISSING_DEPENDENCIES', {item['code'] for item in result['errors']})

    def test_offline_never_creates_fake_certification(self):
        result = preflight_one(
            self.manifest(),
            self.manifest_path,
            db_row=self.row(),
            dependency={'status': 'COMFY_OFFLINE'},
            object_info=None,
        )
        self.assertEqual(result['status'], PREFLIGHT_OFFLINE)
        self.assertEqual(result['errors'], [])
        self.assertIn('COMFY_OFFLINE', {item['code'] for item in result['warnings']})

    def test_ui_conversion_failure_requires_review(self):
        ui_path = self.package / 'original.json'
        ui_path.write_text(
            json.dumps(
                {
                    'nodes': [
                        {
                            'id': 1,
                            'type': 'MissingExecutionNode',
                            'mode': 0,
                            'inputs': [],
                            'outputs': [{'name': 'out', 'links': [1]}],
                            'widgets_values': [],
                        }
                    ],
                    'links': [],
                }
            ),
            encoding='utf-8',
        )
        result = preflight_one(
            self.manifest(),
            self.manifest_path,
            db_row={'original_path': str(ui_path), 'api_workflow_path': None},
            dependency={'status': 'READY'},
            object_info=self.object_info,
        )
        self.assertEqual(result['status'], PREFLIGHT_NEEDS_REVIEW)
        self.assertIn('CONVERSION_FAILED', {item['code'] for item in result['errors']})


if __name__ == '__main__':
    unittest.main()
