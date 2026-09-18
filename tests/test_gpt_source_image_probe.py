import json
import tempfile
import unittest
from pathlib import Path

from backend.gpt_director import GPTDirectorPage, GPTDirectorSettings, GPTDirectorSource, GPTDirectorStore, GPTDirectorTask
from backend.gpt_source_image_probe import (
    authorize_source_page,
    neutral_image_name,
    safe_image_mime,
    safe_probe_metadata,
)


class GPTSourceImageProbeTests(unittest.TestCase):
    def task(self, pages=(4, 6, 9)):
        return GPTDirectorTask(
            id='gdt-' + 'a' * 32,
            status='WAITING_GPT',
            source=GPTDirectorSource(
                token='opaque-token', name='Issue', filename='issue.pdf', pageCount=12,
                selectedPages=list(pages),
                pages=[GPTDirectorPage(ref=f'P{page:03d}', page=page,
                                       imageUrl=f'http://127.0.0.1/page/{page}',
                                       thumbnailUrl=f'http://127.0.0.1/thumb/{page}') for page in pages],
            ),
            settings=GPTDirectorSettings(), createdAt='2026-01-01T00:00:00Z', updatedAt='2026-01-01T00:00:00Z',
        )

    def test_valid_selected_page(self):
        page = authorize_source_page(self.task(), 6)
        self.assertEqual((page.page, page.token, page.resource_name), (6, 'opaque-token', 'page-006'))

    def test_unselected_page_rejected(self):
        with self.assertRaises(PermissionError): authorize_source_page(self.task(), 5)

    def test_invalid_page(self):
        for value in (0, -1, True, '4'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                authorize_source_page(self.task(), value)  # type: ignore[arg-type]

    def test_invalid_task_is_rejected_by_store(self):
        with tempfile.TemporaryDirectory() as root:
            store = GPTDirectorStore(Path(root))
            with self.assertRaises(ValueError): store.load_task('../task')

    def test_safe_mime_png_jpeg_webp(self):
        for mime in ('image/png', 'image/jpeg', 'image/webp'):
            self.assertEqual(safe_image_mime(mime), mime)
        with self.assertRaises(ValueError): safe_image_mime('image/svg+xml')

    def test_neutral_metadata_and_no_path_exposure(self):
        metadata = safe_probe_metadata(4, 'image/png', 123, 164)
        encoded = json.dumps(metadata)
        self.assertEqual(metadata['resourceName'], 'page-004.png')
        self.assertNotIn('D:', encoded); self.assertNotIn('F:', encoded)
        self.assertNotIn('issue', encoded.lower())

    def test_no_base64_persistence(self):
        metadata = safe_probe_metadata(4, 'image/jpeg', 300, 400)
        self.assertNotIn('data', metadata); self.assertNotIn('base64', ''.join(metadata).lower().replace('base64encodedsize', ''))

    def test_resource_authorization_uses_page_records(self):
        task = self.task(); task.source.pages = [task.source.pages[0]]
        with self.assertRaises(PermissionError): authorize_source_page(task, 6)

    def test_non_contiguous_page_validation(self):
        task = self.task((4, 6, 9))
        self.assertEqual([authorize_source_page(task, page).page for page in (4, 6, 9)], [4, 6, 9])
        with self.assertRaises(PermissionError): authorize_source_page(task, 5)

    def test_neutral_names_follow_mime(self):
        self.assertEqual(neutral_image_name(9, 'image/webp'), 'page-009.webp')


if __name__ == '__main__':
    unittest.main()
