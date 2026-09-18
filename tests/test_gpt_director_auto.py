import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI

from backend import gpt_director_auto_api
from backend.gpt_director import (
    GPTDirectorPage,
    GPTDirectorResult,
    GPTDirectorSettings,
    GPTDirectorSource,
)
from backend.gpt_director_auto import (
    GPTDirectorAutoError,
    GPTDirectorAutoService,
    ImmediateExecutor,
)


def sample_result(page=1):
    return GPTDirectorResult.model_validate({
        'sourceUnderstanding': {'summary': 'Observed source page.'},
        'creativeStory': {
            'title': 'A Brave Little Plan',
            'summary': 'Friends solve a small problem.',
            'story': 'They work together.',
            'adaptationNotes': ['New child-friendly story'],
        },
        'characterDefinitions': [{'id': 'C1', 'name': 'Mia'}],
        'sceneDefinitions': [{'id': 'SC1', 'description': 'A bright room'}],
        'shots': [{
            'shotId': 'S01',
            'title': 'A New Idea',
            'duration': 5,
            'storyPurpose': 'Introduce the problem',
            'speaker': 'Mia',
            'english': 'Let us try!',
            'chinese': '我们试试吧！',
            'keyframeDescription': 'Mia has an idea.',
            'imagePrompt': 'Mia in a bright room',
            'videoPrompt': 'Mia points to a colorful object',
            'negativePrompt': 'text, watermark',
            'sourcePages': [page],
        }],
    })


class FakeRunner:
    def __init__(self, root: Path, fail: bool = False):
        self.root = root
        self.fail = fail

    def status(self):
        return {'ready': True, 'relayReady': True, 'cdpReady': True}

    def run(self, task_id: str, timeout: int = 780):
        if self.fail:
            raise GPTDirectorAutoError('FAKE_FAILURE', 'runner failed')
        service_store = GPTDirectorAutoService(self.root, runner=self, executor=ImmediateExecutor()).director
        result = sample_result()
        service_store.import_result(task_id, result)
        service_store.complete(task_id)
        return {
            'result': {
                'ok': True,
                'taskId': task_id,
                'title': result.creativeStory.title,
                'shotCount': len(result.shots),
                'sourcePages': [1],
            },
            'stderrTail': 'fake runner completed',
        }


class GPTDirectorAutoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runner = FakeRunner(self.root)
        self.service = GPTDirectorAutoService(self.root, runner=self.runner, executor=ImmediateExecutor())
        source = GPTDirectorSource(
            token='opaque-token',
            name='Comic',
            filename='comic.pdf',
            pageCount=3,
            selectedPages=[1],
            pages=[GPTDirectorPage(ref='P001', page=1, imageUrl='/page/1', thumbnailUrl='/thumb/1')],
        )
        self.task = self.service.director.create(source, GPTDirectorSettings())

    def tearDown(self):
        self.tmp.cleanup()

    def test_status_passthrough(self):
        value = self.service.status()
        self.assertTrue(value['ready'])

    def test_successful_job_completes_and_persists_result(self):
        job = self.service.create_job(self.task.id)
        saved = self.service.get_job(job['jobId'])
        self.assertEqual(saved['status'], 'COMPLETED')
        self.assertEqual(saved['result']['title'], 'A Brave Little Plan')
        self.assertEqual(saved['result']['shotCount'], 1)
        self.assertEqual(self.service.director.load_task(self.task.id).status, 'COMPLETED')
        self.assertIsNotNone(self.service.director.load_result(self.task.id))

    def test_recover_interrupted_jobs_marks_stale_running_job_failed(self):
        stale = {
            'jobId': 'gda-' + 'a' * 32,
            'taskId': self.task.id,
            'status': 'RUNNING',
            'createdAt': '2026-09-18T00:00:00+00:00',
            'startedAt': '2026-09-18T00:00:01+00:00',
            'completedAt': None,
            'errorCode': None,
            'errorMessage': None,
            'result': None,
        }
        path = self.service._job_path(stale['jobId'])
        self.service._atomic_write(path, stale)

        recovered = self.service.recover_interrupted_jobs()
        saved = self.service.get_job(stale['jobId'])

        self.assertEqual(recovered, 1)
        self.assertEqual(saved['status'], 'FAILED')
        self.assertEqual(saved['errorCode'], 'DIRECTOR_AUTO_INTERRUPTED')
        self.assertIsNotNone(saved['completedAt'])

    def test_failed_runner_marks_job_failed(self):
        service = GPTDirectorAutoService(
            self.root,
            runner=FakeRunner(self.root, fail=True),
            executor=ImmediateExecutor(),
        )
        source = GPTDirectorSource(
            token='another-token',
            name='Comic2',
            filename='comic2.pdf',
            pageCount=1,
            selectedPages=[1],
            pages=[GPTDirectorPage(ref='P001', page=1, imageUrl='/page/1', thumbnailUrl='/thumb/1')],
        )
        task = service.director.create(source, GPTDirectorSettings())
        job = service.create_job(task.id)
        saved = service.get_job(job['jobId'])
        self.assertEqual(saved['status'], 'FAILED')
        self.assertEqual(saved['errorCode'], 'FAKE_FAILURE')

    def test_missing_task_rejected(self):
        with self.assertRaisesRegex(GPTDirectorAutoError, 'not found'):
            self.service.create_job('gdt-' + 'f' * 32)

    def test_completed_task_rejected(self):
        self.service.create_job(self.task.id)
        with self.assertRaises(GPTDirectorAutoError) as caught:
            self.service.create_job(self.task.id)
        self.assertEqual(caught.exception.code, 'TASK_ALREADY_COMPLETED')

    def test_invalid_job_id_rejected(self):
        with self.assertRaises(GPTDirectorAutoError) as caught:
            self.service.get_job('../bad')
        self.assertEqual(caught.exception.code, 'INVALID_JOB_ID')

    def test_router_exposes_status_run_and_job(self):
        app = FastAPI()
        app.include_router(gpt_director_auto_api.gpt_director_auto_router())
        paths = {route.path for route in app.routes}
        self.assertIn('/api/gpt-director-auto/status', paths)
        self.assertIn('/api/gpt-director-auto/tasks/{task_id}/run', paths)
        self.assertIn('/api/gpt-director-auto/jobs/{job_id}', paths)


if __name__ == '__main__':
    unittest.main()
