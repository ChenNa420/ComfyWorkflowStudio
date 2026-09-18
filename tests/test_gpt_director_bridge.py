import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi import FastAPI
from pydantic import ValidationError

from backend import comic_story_api as comic
from backend.gpt_director import (
    GPTDirectorConflict, GPTDirectorPage, GPTDirectorResult, GPTDirectorSettings,
    GPTDirectorSource, GPTDirectorStore, GPTDirectorTaskCreate, build_episode_candidate,
)


def result(pages=(1,), count=2, title='A New Story'):
    return {
        'creativeStory': {'title': title, 'summary': 'A safe new adventure.', 'story': 'The friends solve a problem.'},
        'characterDefinitions': [{'id': 'C1', 'name': 'Mia'}],
        'sceneDefinitions': [{'id': 'S1', 'description': 'park'}],
        'shots': [
            {'shotId': f'S{index + 1}', 'title': f'Shot {index + 1}', 'duration': 5,
             'storyPurpose': 'advance story', 'speaker': 'Mia', 'english': 'Let us go!', 'chinese': '我们走吧！',
             'keyframeDescription': 'Mia in a bright park', 'imagePrompt': 'Mia in a bright park',
             'videoPrompt': 'Mia walks through the park', 'negativePrompt': 'text',
             'sourcePages': [pages[index % len(pages)]]}
            for index in range(count)
        ],
    }


class GPTDirectorBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = GPTDirectorStore(self.root / 'storage')
        self.source = GPTDirectorSource(
            token='abc', name='Comic', filename='comic.pdf', pageCount=12,
            selectedPages=[1, 2, 3],
            pages=[GPTDirectorPage(ref=f'P{p:03d}', page=p, imageUrl=f'http://test/page/{p}',
                                   thumbnailUrl=f'http://test/page/{p}?thumbnail=true') for p in [1, 2, 3]],
        )

    def tearDown(self): self.tmp.cleanup()
    def task(self, pages=None):
        source = self.source if pages is None else self.source.model_copy(update={
            'selectedPages': pages,
            'pages': [GPTDirectorPage(ref=f'P{p:03d}', page=p, imageUrl=f'/page/{p}', thumbnailUrl=f'/thumb/{p}') for p in pages],
        })
        return self.store.create(source, GPTDirectorSettings())

    def test_01_one_page_task(self): self.assertEqual(self.task([1]).source.selectedPages, [1])
    def test_02_three_page_task(self): self.assertEqual(len(self.task().source.pages), 3)
    def test_03_non_contiguous_pages(self): self.assertEqual(self.task([4, 6, 9]).source.selectedPages, [4, 6, 9])
    def test_04_duplicate_page_validation(self):
        with self.assertRaises(ValidationError): GPTDirectorTaskCreate(token='x', selectedPages=[1, 1])
    def test_05_page_out_of_range(self):
        pdf, token = self.pdf_with_pages(3)
        with self.assertRaisesRegex(ValueError, 'selected_page_out_of_range'):
            comic._gpt_director_source(pdf, token, [4], 'http://test')
    def test_06_more_than_twelve_pages(self):
        with self.assertRaises(ValidationError): GPTDirectorTaskCreate(token='x', selectedPages=list(range(1, 14)))
    def test_07_task_persisted(self):
        task = self.task(); self.assertTrue((self.root / 'storage' / task.id / 'task.json').is_file())
    def test_08_task_reload(self):
        task = self.task(); self.assertEqual(self.store.load_task(task.id).source.filename, 'comic.pdf')
    def test_09_safe_task_id(self): self.assertRegex(self.task().id, r'^gdt-[a-f0-9]{32}$')
    def test_10_invalid_task_id(self):
        with self.assertRaises(ValueError): self.store.load_task('../outside')
    def test_11_valid_gpt_result(self): GPTDirectorResult.model_validate(result())
    def test_12_invalid_result(self):
        with self.assertRaises(ValidationError): GPTDirectorResult.model_validate({'creativeStory': {'title': ''}, 'shots': []})
    def test_13_invalid_source_page(self):
        task = self.task()
        with self.assertRaises(ValueError): self.store.import_result(task.id, GPTDirectorResult.model_validate(result((9,))))
    def test_14_duplicate_shot_id(self):
        value = result(); value['shots'][1]['shotId'] = 'S1'
        with self.assertRaises(ValidationError): GPTDirectorResult.model_validate(value)
    def test_15_duration_over_ten(self):
        value = result(); value['shots'][0]['duration'] = 11
        with self.assertRaises(ValidationError): GPTDirectorResult.model_validate(value)
    def test_16_dynamic_shot_count(self): self.assertEqual(len(GPTDirectorResult.model_validate(result(count=7)).shots), 7)
    def test_17_result_persistence(self):
        task = self.task(); self.store.import_result(task.id, GPTDirectorResult.model_validate(result()))
        self.assertTrue((self.root / 'storage' / task.id / 'result.json').is_file())
    def test_18_result_reload(self):
        task = self.task(); self.store.import_result(task.id, GPTDirectorResult.model_validate(result()))
        self.assertEqual(self.store.load_result(task.id).creativeStory.title, 'A New Story')
    def test_19_identical_result_idempotency(self):
        task = self.task(); value = GPTDirectorResult.model_validate(result())
        self.assertFalse(self.store.import_result(task.id, value)[1]); self.assertTrue(self.store.import_result(task.id, value)[1])
    def test_20_conflicting_result(self):
        task = self.task(); self.store.import_result(task.id, GPTDirectorResult.model_validate(result()))
        with self.assertRaises(GPTDirectorConflict): self.store.import_result(task.id, GPTDirectorResult.model_validate(result(title='Different')))
    def test_21_complete_without_result(self):
        with self.assertRaises(ValueError): self.store.complete(self.task().id)
    def test_22_valid_complete(self):
        task = self.task(); self.store.import_result(task.id, GPTDirectorResult.model_validate(result()))
        self.assertEqual(self.store.complete(task.id).status, 'COMPLETED')
    def test_23_completed_protection(self):
        task = self.task(); first = GPTDirectorResult.model_validate(result()); self.store.import_result(task.id, first); self.store.complete(task.id)
        with self.assertRaises(GPTDirectorConflict): self.store.import_result(task.id, GPTDirectorResult.model_validate(result(title='Different')))
        self.assertTrue(self.store.import_result(task.id, first)[1])
    def test_24_no_filesystem_path_exposure(self):
        task = self.task(); dumped = json.dumps(task.model_dump(mode='json'))
        self.assertNotIn(str(self.root), dumped); self.assertNotIn('D:\\', dumped)
    def test_25_episode_candidate_and_existing_router(self):
        task = self.task(); value = GPTDirectorResult.model_validate(result(count=5))
        candidate = build_episode_candidate(task, value)
        self.assertEqual(len(candidate['shots']), 5); self.assertEqual(candidate['shots'][0]['imagePrompt'], 'Mia in a bright park')
        app = FastAPI(); app.include_router(comic.comic_story_router()); paths = {route.path for route in app.routes}
        self.assertIn('/api/comic-story/analyze', paths); self.assertIn('/api/comic-story/gpt-director/tasks', paths)

    def test_26_local_source_binding_survives_store_recreation(self):
        pdf, token = self.pdf_with_pages(2)
        source = GPTDirectorSource(
            token=token, name='Comic', filename='comic.pdf', pageCount=2,
            selectedPages=[1],
            pages=[GPTDirectorPage(ref='P001', page=1, imageUrl='/page/1', thumbnailUrl='/thumb/1')],
        )
        task = self.store.create(source, GPTDirectorSettings())
        self.store.bind_local_source(task.id, token, pdf)
        restarted = GPTDirectorStore(self.root / 'storage')
        self.assertEqual(restarted.resolve_local_source(task.id, token), pdf.resolve())

    def test_27_local_source_path_is_private(self):
        pdf, token = self.pdf_with_pages(1)
        source = GPTDirectorSource(
            token=token, name='Comic', filename='comic.pdf', pageCount=1,
            selectedPages=[1],
            pages=[GPTDirectorPage(ref='P001', page=1, imageUrl='/page/1', thumbnailUrl='/thumb/1')],
        )
        task = self.store.create(source, GPTDirectorSettings())
        self.store.bind_local_source(task.id, token, pdf)
        public_task = (self.root / 'storage' / task.id / 'task.json').read_text(encoding='utf-8')
        self.assertNotIn(str(pdf.resolve()), public_task)
        self.assertTrue((self.root / 'storage' / task.id / 'source.local.json').is_file())

    def test_28_local_source_binding_rejects_token_mismatch(self):
        pdf, _ = self.pdf_with_pages(1)
        task = self.task([1])
        with self.assertRaisesRegex(ValueError, 'token'):
            self.store.bind_local_source(task.id, 'wrong-token', pdf)
    def pdf_with_pages(self, pages):
        pdf = self.root / 'comic.pdf'
        with fitz.open() as doc:
            for _ in range(pages): doc.new_page()
            doc.save(pdf)
        token = comic._register_file(pdf)
        return pdf, token


if __name__ == '__main__': unittest.main()
