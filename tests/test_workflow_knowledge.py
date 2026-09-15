from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.db import Database
from backend.models import WorkflowManifest
from backend.workflow.knowledge import (
    build_workflow_card,
    manifest_completeness,
    search_workflow_knowledge,
    workflow_knowledge_stats,
)


class WorkflowKnowledgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root / 'studio.sqlite3')
        self.db.initialize()
        self.package = self.root / 'workflow-packages' / 'wf-minimax'
        self.package.mkdir(parents=True)
        self.manifest_path = self.package / 'manifest.json'
        self.manifest_path.write_text('{}', encoding='utf-8')
        (self.package / 'analysis.json').write_text(
            json.dumps(
                {
                    'format': 'ui-workflow',
                    'nodeCount': 24,
                    'nodeTypes': ['MiniMaxH3ImageToVideo', 'KSampler', 'SaveVideo'],
                    'inputs': [
                        {'analysisConfidence': 0.98},
                        {'analysisConfidence': 0.82},
                    ],
                }
            ),
            encoding='utf-8',
        )
        self.manifest = WorkflowManifest.model_validate(
            {
                'schemaVersion': '1.0',
                'workflowId': 'wf-minimax',
                'name': 'MiniMax H3 First Frame Animation',
                'category': 'image-to-video',
                'description': '使用首帧图片和英文动作提示词生成连续的短动画视频。',
                'difficulty': 'medium',
                'source': {'name': 'Test', 'url': ''},
                'capabilities': ['image-to-video'],
                'recommendedFor': ['动画镜头', '角色动作'],
                'notRecommendedFor': ['精确口型同步'],
                'inputs': [
                    {
                        'key': 'first-frame',
                        'label': '首帧',
                        'type': 'image',
                        'required': True,
                        'purpose': 'video-start-frame',
                        'description': '镜头起始画面',
                        'help': '保持角色与目标镜头一致。',
                        'mapping': {'nodeId': '10', 'field': 'image'},
                    },
                    {
                        'key': 'prompt',
                        'label': '动作提示词',
                        'type': 'textarea',
                        'required': True,
                        'purpose': 'prompt',
                        'description': '描述动作、环境和镜头运动',
                        'mapping': {'nodeId': '20', 'field': 'text'},
                    },
                ],
                'parameters': [
                    {
                        'key': 'seed',
                        'label': 'Seed',
                        'type': 'seed',
                        'default': -1,
                        'description': '随机种子',
                        'mapping': {'nodeId': '30', 'field': 'seed'},
                    }
                ],
                'outputs': [
                    {'key': 'video', 'type': 'video', 'format': 'mp4', 'mapping': {'nodeId': '40'}}
                ],
                'dependencies': {
                    'models': [{'name': 'minimax-model.safetensors', 'required': True}],
                    'customNodes': [{'name': 'ComfyUI-Pixaroma', 'required': True}],
                },
                'runtime': {
                    'executionMode': 'serial',
                    'durationPolicy': 'dynamic',
                    'allowRetry': True,
                    'retryUnknown': False,
                    'preserveOriginalWorkflow': True,
                    'outputTimeout': 900,
                },
                'guide': {
                    'summary': '首帧驱动的短视频生成工作流。',
                    'steps': ['准备首帧', '填写动作提示词', '提交任务'],
                    'promptTips': ['动作要具体', '说明镜头运动'],
                    'warnings': ['角色细节可能随长时长漂移'],
                },
            }
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_complete_manifest_scores_ready_and_extracts_taxonomy(self):
        analysis = json.loads((self.package / 'analysis.json').read_text(encoding='utf-8'))
        completeness = manifest_completeness(self.manifest, analysis)
        self.assertGreaterEqual(completeness['score'], 85)
        self.assertEqual(completeness['grade'], 'A')

        card = build_workflow_card(self.manifest_path, self.manifest)
        self.assertEqual(card['health'], 'READY')
        self.assertIn('MiniMax H3', card['families'])
        self.assertIn('首帧控制', card['traits'])
        self.assertIn('动态时长', card['traits'])
        self.assertEqual(card['categoryLabel'], '首帧 / 图片生视频')

    def test_missing_mapping_requires_adaptation(self):
        payload = self.manifest.model_dump(mode='json')
        payload['inputs'][0]['mapping'] = {}
        incomplete = WorkflowManifest.model_validate(payload)
        card = build_workflow_card(self.manifest_path, incomplete)
        self.assertEqual(card['health'], 'NEEDS_ADAPTATION')
        self.assertIn('input-mappings', card['completeness']['missing'])

    def test_search_stats_and_recommendation_order_use_real_manifest_fields(self):
        second_payload = self.manifest.model_dump(mode='json')
        second_payload['workflowId'] = 'wf-control'
        second_payload['name'] = 'ControlNet Pose Image'
        second_payload['category'] = 'controlnet'
        second_payload['capabilities'] = ['image-control']
        second_payload['inputs'][0]['purpose'] = 'pose'
        second_manifest = WorkflowManifest.model_validate(second_payload)
        second_package = self.root / 'workflow-packages' / 'wf-control'
        second_package.mkdir(parents=True)
        second_path = second_package / 'manifest.json'
        second_path.write_text('{}', encoding='utf-8')
        (second_package / 'analysis.json').write_text(
            json.dumps({'format': 'ui-workflow', 'nodeCount': 10, 'nodeTypes': ['ControlNetApply']}),
            encoding='utf-8',
        )

        manifests = [(self.manifest_path, self.manifest), (second_path, second_manifest)]
        with patch('backend.workflow.knowledge.discover_manifests', return_value=manifests):
            found = search_workflow_knowledge(self.db, q='首帧', capability='image-to-video')
            stats = workflow_knowledge_stats(self.db)

        self.assertEqual([item['id'] for item in found], ['wf-minimax'])
        self.assertEqual(stats['total'], 2)
        self.assertEqual(sum(item['count'] for item in stats['categories']), 2)
        self.assertTrue(any(item['key'] == 'image-to-video' for item in stats['capabilities']))


if __name__ == '__main__':
    unittest.main()
