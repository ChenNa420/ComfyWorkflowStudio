from __future__ import annotations

import unittest

from backend.comfy.runtime import _detect_output_type


class OutputRetrievalTests(unittest.TestCase):
    def test_mp4_returned_in_comfy_images_bucket_is_video(self):
        self.assertEqual(_detect_output_type('image', 'Video_00021.mp4', 'video/mp4'), 'video')

    def test_regular_image_remains_image(self):
        self.assertEqual(_detect_output_type('image', 'preview.png', 'image/png'), 'image')


if __name__ == '__main__':
    unittest.main()
