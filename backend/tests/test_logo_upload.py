import unittest

from app.services.logo_upload import detectar_content_type


class DetectarContentTypeTest(unittest.TestCase):
    def test_detecta_png_sin_extension_en_url(self):
        self.assertEqual(detectar_content_type(b"\x89PNG\r\n\x1a\nresto"), "image/png")

    def test_detecta_jpeg(self):
        self.assertEqual(detectar_content_type(b"\xff\xd8\xff\xe0resto"), "image/jpeg")

    def test_detecta_svg(self):
        self.assertEqual(detectar_content_type(b"  <svg xmlns='http://www.w3.org/2000/svg'></svg>"), "image/svg+xml")


if __name__ == "__main__":
    unittest.main()
