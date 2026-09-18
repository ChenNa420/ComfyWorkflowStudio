from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.comfy.runtime import _apply_dynamic_duration, _collect_outputs, _run_task_guarded
from backend.db import Database
from backend.models import GenerationTaskCreate
from backend.workflow.pilot import PilotRejected, create_pilot, validate_pilot


class Phase1G4RuntimePilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / 'pilot.sqlite3')
        self.db.initialize()
        self.manifest = {
            'workflowId': 'pilot-wf', 'name': 'Pilot', 'category': 'image-to-video',
            'capabilities': ['image-to-video'],
            'inputs': [{'key': 'image', 'label': 'Image', 'type': 'image', 'required': True, 'mapping': {'nodeId': '1', 'field': 'image'}}],
            'outputs': [{'key': 'video', 'type': 'video', 'mapping': {'nodeId': '2'}}],
            'runtime': {'executionMode': 'serial', 'retryUnknown': False, 'preserveOriginalWorkflow': True},
        }
        with self.db.connect() as conn:
            conn.execute("INSERT INTO workflows(id,name,category,original_path,manifest_json,created_at,updated_at) VALUES(?,?,?,?,?,datetime('now'),datetime('now'))", ('pilot-wf','Pilot','image-to-video','missing.json',json.dumps(self.manifest)))

    def tearDown(self): self.tmp.cleanup()

    def certified(self, source='api-workflow'):
        return {'workflowId':'pilot-wf','status':'CERTIFIED','dependencyStatus':'READY','sourceFormat':source}

    @patch('backend.workflow.pilot.preflight_detail')
    def test_certified_allowed_and_backend_forces_preflight(self, preflight):
        preflight.return_value = self.certified()
        result = validate_pilot(self.db, 'pilot-wf', {'image':'real.png'})
        self.assertEqual(result['preflight']['status'], 'CERTIFIED')
        preflight.assert_called_once_with(self.db, 'pilot-wf', force_refresh=True)

    @patch('backend.workflow.pilot.preflight_detail')
    def test_needs_review_blocked_offline_are_refused(self, preflight):
        for state in ('NEEDS_REVIEW','BLOCKED_DEPENDENCIES','COMFY_OFFLINE'):
            preflight.return_value = {**self.certified(), 'status':state}
            with self.assertRaises(PilotRejected) as caught: validate_pilot(self.db, 'pilot-wf', {'image':'x'})
            self.assertEqual(caught.exception.code, state)

    @patch('backend.workflow.pilot.preflight_detail')
    def test_missing_input_fails_safely_before_task(self, preflight):
        preflight.return_value = self.certified()
        with self.assertRaises(PilotRejected) as caught: validate_pilot(self.db, 'pilot-wf', {})
        self.assertEqual(caught.exception.code, 'REQUIRED_INPUT_MISSING')
        with self.db.connect() as conn: self.assertEqual(conn.execute('SELECT COUNT(*) c FROM generation_tasks').fetchone()['c'], 0)

    @patch('backend.workflow.pilot.create_task', return_value='task-new')
    @patch('backend.workflow.pilot.start_task')
    @patch('backend.comfy.runtime._event')
    @patch('backend.workflow.pilot.preflight_detail')
    def test_submit_creates_one_authorized_runtime_task(self, preflight, event, start, create):
        preflight.return_value = self.certified('ui-workflow')
        payload = GenerationTaskCreate(workflowId='pilot-wf', inputs={'image':'x'})
        self.assertEqual(create_pilot(self.db, 'pilot-wf', payload), 'task-new')
        create.assert_called_once_with(self.db, payload, start=False); event.assert_called_once(); start.assert_called_once_with(self.db, 'task-new')
        self.assertTrue(event.call_args.args[4]['runtimeClone'])

    @patch('backend.workflow.pilot.preflight_detail')
    def test_strict_serial_and_double_submit_protection(self, preflight):
        preflight.return_value = self.certified()
        with self.db.connect() as conn:
            conn.execute("INSERT INTO generation_tasks(id,workflow_id,status,inputs_json,parameters_json,created_at) VALUES('active','pilot-wf','RUNNING','{}','{}',datetime('now'))")
        with self.assertRaises(PilotRejected) as caught:
            create_pilot(self.db, 'pilot-wf', GenerationTaskCreate(workflowId='pilot-wf', inputs={'image':'x'}))
        self.assertEqual(caught.exception.code, 'PILOT_ACTIVE')

    def test_dynamic_duration_updates_all_runtime_frame_fields(self):
        prompt={'1':{'inputs':{'frames':1}},'2':{'inputs':{'total_frames':1}}}
        plan=_apply_dynamic_duration(prompt, {'nodes':[{'properties':{'durationState':{'step':24,'plus':4}}}]}, 5)
        self.assertEqual(plan['frames'],124); self.assertEqual(prompt['1']['inputs']['frames'],124); self.assertEqual(prompt['2']['inputs']['total_frames'],124)

    def test_multiple_outputs_are_persisted_with_node_metadata(self):
        client=Mock(); client.download_view.side_effect=[b'a',b'b']
        with self.db.connect() as conn:
            conn.execute("INSERT INTO generation_tasks(id,workflow_id,status,inputs_json,parameters_json,created_at) VALUES('task-output','pilot-wf','RUNNING','{}','{}',datetime('now'))")
        with patch('backend.comfy.runtime.OUTPUT_ROOT', Path(self.tmp.name)/'outputs'):
            saved=_collect_outputs(self.db,'task-output','pilot-wf',{'outputs':{'2':{'images':[{'filename':'a.png'}]},'3':{'videos':[{'filename':'b.mp4'}]}}},client)
        self.assertEqual(len(saved),2)
        with self.db.connect() as conn:
            rows=conn.execute('SELECT type,metadata_json FROM outputs ORDER BY type').fetchall()
        self.assertEqual({row['type'] for row in rows},{'image','video'})
        self.assertEqual({json.loads(row['metadata_json'])['nodeId'] for row in rows},{'2','3'})

    def test_failure_converges_and_unknown_is_not_retried(self):
        with self.db.connect() as conn:
            conn.execute("INSERT INTO generation_tasks(id,workflow_id,status,prompt_id,inputs_json,parameters_json,created_at) VALUES('fail','pilot-wf','RUNNING',NULL,'{}','{}',datetime('now'))")
        with patch('backend.comfy.runtime.run_task', side_effect=RuntimeError('safe failure')) as run:
            _run_task_guarded(self.db,'fail')
        with self.db.connect() as conn: row=conn.execute("SELECT status,error FROM generation_tasks WHERE id='fail'").fetchone()
        self.assertEqual(row['status'],'FAILED'); self.assertIn('safe failure',row['error']); self.assertEqual(run.call_count,1)

    def test_failure_does_not_block_next_task(self):
        with self.db.connect() as conn:
            for ident in ('first','next'): conn.execute("INSERT INTO generation_tasks(id,workflow_id,status,inputs_json,parameters_json,created_at) VALUES(?,'pilot-wf','WAITING','{}','{}',datetime('now'))",(ident,))
        calls=[]
        def runner(_db, task):
            calls.append(task)
            if task=='first': raise RuntimeError('expected')
        with patch('backend.comfy.runtime.run_task', side_effect=runner):
            _run_task_guarded(self.db,'first'); _run_task_guarded(self.db,'next')
        self.assertEqual(calls,['first','next'])


if __name__ == '__main__': unittest.main()
