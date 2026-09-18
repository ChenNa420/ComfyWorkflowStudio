from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from backend.gpt_director import (
    GPTDirectorPage,
    GPTDirectorResult,
    GPTDirectorSettings,
    GPTDirectorSource,
    GPTDirectorStore,
)
from backend.gpt_image_service import (
    DEFAULT_CHATGPT_IMAGE_CDP_URL,
    DEFAULT_CHATGPT_IMAGE_GPT_URL,
    GPTImageError,
    GPTImageService,
    ImmediateExecutor,
    NodeImageWorker,
)


class FakeWorker:
    def __init__(self, image_path: Path):
        self.image_path = image_path
        self.calls = []
        self.story_calls = []
        self.login_calls = []

    def installation_status(self):
        return {'node': True, 'worker': True, 'dependencies': True, 'profileExists': True, 'readyForCheck': True}

    def check(self):
        return {'ok': True, 'ready': True}

    def cdp_ready(self):
        return True

    def start_login(self, gpt_url=None):
        self.login_calls.append(gpt_url)
        return {'started': True}

    def prepare_story(self, payload):
        self.story_calls.append(payload)
        return {
            'ok': True,
            'prepared': True,
            'sent': False,
            'attachmentCount': len(payload.get('sourcePages') or []),
            'promptLength': len(payload.get('prompt') or ''),
            'url': payload.get('gptUrl'),
            'browserMode': 'cdp',
        }

    def generate(self, payload):
        self.calls.append(payload)
        return {
            'ok': True,
            'image': {
                'filePath': str(self.image_path),
                'mimeType': 'image/png',
                'captureMethod': 'authenticated_image_fetch',
            },
        }


def make_result():
    return GPTDirectorResult.model_validate({
        'creativeStory': {'title': 'Demo'},
        'characterDefinitions': [{'key': 'puppy', 'description': 'golden puppy'}],
        'sceneDefinitions': [],
        'shots': [{
            'shotId': 'S01',
            'title': 'Kitchen',
            'duration': 5,
            'imagePrompt': 'A puppy in a warm kitchen',
            'videoPrompt': 'The puppy waves',
            'sourcePages': [1],
        }],
    })


class GPTImageServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        store = GPTDirectorStore(self.root / 'storage' / 'gpt-director')
        source = GPTDirectorSource(
            token='token',
            name='comic',
            filename='comic.pdf',
            pageCount=1,
            selectedPages=[1],
            pages=[GPTDirectorPage(ref='P001', page=1, imageUrl='/p1', thumbnailUrl='/p1?t=1')],
        )
        task = store.create(source, GPTDirectorSettings())
        store.import_result(task.id, make_result())
        store.complete(task.id)
        self.task_id = task.id

        worker_dir = self.root / 'storage' / 'chatgpt-image-worker' / 'fake'
        worker_dir.mkdir(parents=True)
        self.generated = worker_dir / 'frame.png'
        Image.new('RGB', (512, 512), 'white').save(self.generated)
        self.worker = FakeWorker(self.generated)
        self.service = GPTImageService(self.root, worker=self.worker, executor=ImmediateExecutor())

    def tearDown(self):
        self.temp.cleanup()

    def test_status_is_safe(self):
        self.assertTrue(self.service.status()['readyForCheck'])

    def test_node_worker_defaults_to_local_cdp_and_tongyu_gpt(self):
        worker = NodeImageWorker(self.root)
        env = worker._env()
        self.assertEqual(env['CWS_CHATGPT_IMAGE_CDP_URL'], DEFAULT_CHATGPT_IMAGE_CDP_URL)
        self.assertEqual(env['CWS_CHATGPT_IMAGE_URL'], DEFAULT_CHATGPT_IMAGE_GPT_URL)
        self.assertTrue(env['CWS_CHATGPT_IMAGE_URL'].startswith('https://chatgpt.com/g/'))

    def test_prepares_story_draft_with_selected_source_pages_without_sending(self):
        target = 'https://chatgpt.com/g/test-manual-director'
        result = self.service.prepare_story(self.task_id, 'manual story prompt', target)
        self.assertTrue(result['prepared'])
        self.assertFalse(result['sent'])
        self.assertEqual(result['attachmentCount'], 1)
        self.assertEqual(result['sourcePages'], [1])
        self.assertEqual(len(self.worker.story_calls), 1)
        payload = self.worker.story_calls[0]
        self.assertEqual(payload['prompt'], 'manual story prompt')
        self.assertEqual(payload['gptUrl'], target)
        self.assertEqual(payload['sourcePages'][0]['page'], 1)
        self.assertIn(f'/gpt-director/tasks/{self.task_id}/pages/1/image', payload['sourcePages'][0]['url'])
        self.assertEqual(self.worker.login_calls, [])

    def test_prepare_story_starts_browser_only_when_cdp_is_not_ready(self):
        target = 'https://chatgpt.com/g/test-manual-director'
        self.worker.cdp_ready = lambda: False
        self.service.prepare_story(self.task_id, 'manual story prompt', target)
        self.assertEqual(self.worker.login_calls, [target])

    def test_generates_and_binds_frame(self):
        job = self.service.create_job(self.task_id, 'S01')
        completed = self.service.get_job(job['jobId'])
        self.assertEqual(completed['status'], 'COMPLETED')
        self.assertEqual(completed['frame']['shotId'], 'S01')
        path, record = self.service.frame_file(self.task_id, 'S01')
        self.assertTrue(path.is_file())
        self.assertEqual(record['mime'], 'image/png')

    def test_existing_frame_requires_explicit_replace(self):
        self.service.create_job(self.task_id, 'S01')
        with self.assertRaises(GPTImageError) as context:
            self.service.create_job(self.task_id, 'S01')
        self.assertEqual(context.exception.code, 'FRAME_EXISTS')

    def test_explicit_replace_is_allowed(self):
        self.service.create_job(self.task_id, 'S01')
        second = self.service.create_job(self.task_id, 'S01', replace=True)
        self.assertEqual(self.service.get_job(second['jobId'])['status'], 'COMPLETED')

    def test_invalid_shot_rejected(self):
        with self.assertRaises(GPTImageError) as context:
            self.service.create_job(self.task_id, 'S99')
        self.assertEqual(context.exception.code, 'SHOT_NOT_FOUND')

    def test_frames_reports_missing_or_imported(self):
        self.assertEqual(self.service.frames(self.task_id)[0]['status'], 'MISSING')
        self.service.create_job(self.task_id, 'S01')
        self.assertEqual(self.service.frames(self.task_id)[0]['status'], 'IMPORTED')

    def test_rejects_corrupt_image(self):
        self.generated.write_bytes(b'not an image')
        job = self.service.create_job(self.task_id, 'S01')
        completed = self.service.get_job(job['jobId'])
        self.assertEqual(completed['status'], 'FAILED')
        self.assertEqual(completed['errorCode'], 'FRAME_DECODE_FAILED')


if __name__ == '__main__':
    unittest.main()
