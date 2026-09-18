from __future__ import annotations

import unittest

from backend.workflow.readiness import build_readiness_plan


class Phase1GReadinessTests(unittest.TestCase):
    def inventory(self):
        return {
            'connected': True,
            'comfyUiUrl': 'http://127.0.0.1:8188',
            'error': None,
            'workflows': [
                {
                    'workflowId': 'wf-ready',
                    'name': 'Ready Workflow',
                    'category': 'image-to-video',
                    'capabilities': ['image-to-video'],
                    'status': 'READY',
                    'models': [],
                    'nodeTypes': [],
                },
                {
                    'workflowId': 'wf-model-only',
                    'name': 'Needs Model',
                    'category': 'image-to-video',
                    'capabilities': ['image-to-video'],
                    'status': 'MISSING_DEPENDENCIES',
                    'models': [
                        {
                            'name': 'wan_model.safetensors',
                            'required': True,
                            'status': 'MISSING',
                            'modelType': 'diffusion-model',
                            'modelTypes': ['diffusion-model'],
                        }
                    ],
                    'nodeTypes': [{'nodeType': 'WanVideoSampler', 'status': 'PRESENT'}],
                },
                {
                    'workflowId': 'wf-node-only',
                    'name': 'Needs Node',
                    'category': 'controlnet',
                    'capabilities': ['image-control'],
                    'status': 'MISSING_DEPENDENCIES',
                    'models': [],
                    'nodeTypes': [{'nodeType': 'MissingPoseNode', 'status': 'MISSING'}],
                },
                {
                    'workflowId': 'wf-two',
                    'name': 'Needs Two',
                    'category': 'image-to-video',
                    'capabilities': ['image-to-video'],
                    'status': 'MISSING_DEPENDENCIES',
                    'models': [
                        {
                            'name': 'wan_model.safetensors',
                            'required': True,
                            'status': 'MISSING',
                            'modelType': 'diffusion-model',
                            'modelTypes': ['diffusion-model'],
                        }
                    ],
                    'nodeTypes': [{'nodeType': 'MissingPoseNode', 'status': 'MISSING'}],
                },
            ],
        }

    def test_plan_separates_affected_from_conservative_unlocks(self):
        plan = build_readiness_plan(self.inventory())
        self.assertEqual(plan['summary']['ready'], 1)
        self.assertEqual(plan['summary']['blocked'], 3)
        self.assertEqual(plan['summary']['nearReady'], 2)
        model = next(item for item in plan['topBlockers'] if item['kind'] == 'MODEL')
        node = next(item for item in plan['topBlockers'] if item['kind'] == 'NODE')
        self.assertEqual(model['affectedCount'], 2)
        self.assertEqual(model['unlockCount'], 1)
        self.assertEqual(node['affectedCount'], 2)
        self.assertEqual(node['unlockCount'], 1)

    def test_capability_filter_changes_unlock_plan(self):
        plan = build_readiness_plan(self.inventory(), capability='image-to-video')
        self.assertEqual(plan['summary']['workflows'], 3)
        self.assertEqual(plan['summary']['blocked'], 2)
        self.assertTrue(all('image-to-video' in item['capabilities'] for item in plan['blockedWorkflows']))

    def test_offline_inventory_never_reports_fake_missing_blockers(self):
        inventory = self.inventory()
        inventory['connected'] = False
        inventory['workflows'] = [
            {
                **item,
                'status': 'COMFY_OFFLINE',
                'models': [{**model, 'status': 'UNKNOWN'} for model in item.get('models') or []],
                'nodeTypes': [{**node, 'status': 'UNKNOWN'} for node in item.get('nodeTypes') or []],
            }
            for item in inventory['workflows']
        ]
        plan = build_readiness_plan(inventory)
        self.assertFalse(plan['connected'])
        self.assertEqual(plan['summary']['blocked'], 0)
        self.assertEqual(plan['summary']['modelBlockers'], 0)
        self.assertEqual(plan['summary']['nodeBlockers'], 0)
        self.assertEqual(plan['topBlockers'], [])


if __name__ == '__main__':
    unittest.main()
