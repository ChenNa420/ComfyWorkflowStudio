import unittest

from backend.gpt_keyframe_probe import classify_probe, sanitize_probe_metadata


class GPTKeyframeProbeTests(unittest.TestCase):
    def test_plain_string_is_not_assumed_to_be_image(self):
        self.assertEqual(classify_probe(sanitize_probe_metadata('hello')), 'IMAGE_NOT_TRANSFERABLE')

    def test_safe_url_scheme_without_full_url(self):
        value = sanitize_probe_metadata('https://example.test/private/image.png?token=secret')
        self.assertEqual(value['urlScheme'], 'https'); self.assertNotIn('secret', str(value))
        self.assertEqual(classify_probe(value), 'RESOURCE_URL_SUPPORTED')

    def test_direct_file_requires_readable_binary(self):
        value = {'constructor': 'File', 'referenceType': 'file', 'urlScheme': None}
        self.assertEqual(classify_probe(value), 'IMAGE_NOT_TRANSFERABLE')
        self.assertEqual(classify_probe(value, binary_accessible=True), 'DIRECT_FILE_SUPPORTED')

    def test_attachment_reference_classification(self):
        value = sanitize_probe_metadata({'attachmentId': 'opaque', 'mimeType': 'image/png', 'size': 12})
        self.assertEqual(classify_probe(value), 'ATTACHMENT_REFERENCE_SUPPORTED')

    def test_resource_reference_classification(self):
        self.assertEqual(classify_probe(sanitize_probe_metadata({'resourceRef': 'opaque'})), 'RESOURCE_REFERENCE_SUPPORTED')

    def test_sensitive_keys_are_removed(self):
        value = sanitize_probe_metadata({'url': 'https://example.test/x', 'accessToken': 'secret', 'authorization': 'secret'})
        self.assertNotIn('accessToken', value['objectKeys']); self.assertNotIn('authorization', value['objectKeys'])
        self.assertNotIn('secret', str(value))

    def test_base64_content_is_never_copied(self):
        value = sanitize_probe_metadata({'data': 'A' * 100000, 'type': 'image/png'})
        self.assertNotIn('A' * 10, str(value)); self.assertIn('data', value['objectKeys'])


if __name__ == '__main__': unittest.main()
