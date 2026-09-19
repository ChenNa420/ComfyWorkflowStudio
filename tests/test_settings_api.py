from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from backend.db import Database
from backend.comfy.client import ComfyClientError
from backend.settings import SettingsUpdate, effective_comfy_url, read_overrides
from backend.settings_api import settings_router


CANDIDATES = [
    {'id': 'image-ready', 'name': 'Image Ready', 'category': 'image', 'capabilities': ['image-generation'], 'health': 'READY', 'dependencyStatus': 'READY', 'manifest': {'outputs': [{'type': 'image'}]}},
    {'id': 'video-ready', 'name': 'Video Ready', 'category': 'video', 'capabilities': ['image-to-video'], 'health': 'READY', 'dependencyStatus': 'READY', 'manifest': {'outputs': [{'type': 'video'}]}},
]


class SettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / 'settings.sqlite3')
        conn = sqlite3.connect(self.db.path)
        try:
            conn.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL)')
            conn.commit()
        finally:
            conn.close()
        router = settings_router(self.db)
        self.patches = [
            patch('backend.settings_api.search_workflow_knowledge', return_value=CANDIDATES),
            patch('backend.settings_api.ComfyClient.system_stats', side_effect=ComfyClientError('offline')),
        ]
        for item in self.patches:
            item.start()
        self.get_settings = next(route.endpoint for route in router.routes if route.path == '/api/settings' and 'GET' in route.methods)
        self.update_settings = next(route.endpoint for route in router.routes if route.path == '/api/settings' and 'PUT' in route.methods)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_get_returns_real_readonly_safety_policy(self):
        payload = self.get_settings()
        self.assertEqual(payload['taskPolicy']['maxConcurrency'], {'value': 1, 'editable': False})
        self.assertFalse(payload['taskPolicy']['retryUnknown']['value'])
        self.assertTrue(payload['workflow']['requireCertified']['value'])
        self.assertTrue(payload['storage'][0]['path'])

    def test_writable_fields_are_saved(self):
        with patch('backend.settings_api.ComfyClient.system_stats', return_value={}):
            response = self.update_settings(SettingsUpdate.model_validate({
                'comfyUiUrl': 'http://127.0.0.1:8288/',
                'defaultImageWorkflowId': 'image-ready',
                'defaultVideoWorkflowId': 'video-ready',
                'productionVideoWorkflowId': 'video-ready',
                'showReadyOnly': False,
            }))
        self.assertIn('comfyUiUrl', response['saved'])
        values = read_overrides(self.db)
        self.assertEqual(values['comfyUiUrl'], 'http://127.0.0.1:8288')
        self.assertFalse(values['showReadyOnly'])

    def test_readonly_security_field_is_rejected(self):
        with self.assertRaises(ValidationError):
            SettingsUpdate.model_validate({'retryUnknown': True})
        with self.assertRaises(ValidationError):
            SettingsUpdate.model_validate({'storage': {'outputs': '..\\outside'}})

    def test_invalid_url_and_workflow_type_are_rejected(self):
        with self.assertRaises(ValidationError):
            SettingsUpdate.model_validate({'comfyUiUrl': '../8188'})
        with self.assertRaises(HTTPException) as caught:
            self.update_settings(SettingsUpdate(defaultVideoWorkflowId='image-ready'))
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(caught.exception.detail['code'], 'WORKFLOW_TYPE_MISMATCH')

    def test_override_precedes_environment_and_default(self):
        with patch.dict(os.environ, {'COMFYUI_URL': 'http://127.0.0.1:8388'}):
            self.assertEqual(effective_comfy_url(self.db), ('http://127.0.0.1:8388', 'environment'))
            with self.db.connect() as conn:
                conn.execute("INSERT INTO settings VALUES('comfyUiUrl','\"http://127.0.0.1:8488\"',datetime('now'))")
            self.assertEqual(effective_comfy_url(self.db), ('http://127.0.0.1:8488', 'local_override'))


if __name__ == '__main__':
    unittest.main()
