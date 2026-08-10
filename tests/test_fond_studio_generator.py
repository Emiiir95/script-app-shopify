"""
Tests unitaires — features/fond_studio/generator.py

Couvre : download_image, _guess_name, regenerate_on_background
"""
import base64
import io
import unittest
from unittest.mock import patch, MagicMock

from features.fond_studio.generator import (
    download_image, _guess_name, make_image_buffer, regenerate_on_background,
)


class TestDownloadImage(unittest.TestCase):
    @patch("features.fond_studio.generator.requests.get")
    def test_returns_content(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = b"IMGBYTES"
        mock_get.return_value = mock_resp

        out = download_image("https://cdn/x.jpg")
        self.assertEqual(out, b"IMGBYTES")
        mock_resp.raise_for_status.assert_called_once()


class TestGuessName(unittest.TestCase):
    def test_keeps_known_extension(self):
        self.assertTrue(_guess_name("https://cdn/photo.png?v=1").endswith(".png"))
        self.assertTrue(_guess_name("https://cdn/photo.webp").endswith(".webp"))

    def test_unknown_extension_becomes_png(self):
        self.assertTrue(_guess_name("https://cdn/photo.tiff").endswith(".png"))
        self.assertTrue(_guess_name("https://cdn/noext").endswith(".png"))


class TestMakeImageBuffer(unittest.TestCase):
    def test_returns_named_buffer(self):
        buf = make_image_buffer(b"data", "https://cdn/p.webp")
        self.assertEqual(buf.read(), b"data")
        self.assertTrue(buf.name.endswith(".webp"))


class TestRegenerateOnBackground(unittest.TestCase):
    def _client_returning(self, raw_bytes):
        b64 = base64.b64encode(raw_bytes).decode("ascii")
        client = MagicMock()
        client.images.edit.return_value = MagicMock(data=[MagicMock(b64_json=b64)])
        return client

    def _buf(self, name="produit.png"):
        b = io.BytesIO(b"img"); b.name = name; return b

    def test_returns_decoded_bytes(self):
        client = self._client_returning(b"NEWPNG")
        out = regenerate_on_background([self._buf()], "mon prompt", client)
        self.assertEqual(out, b"NEWPNG")

    def test_single_image_sent_as_buffer_not_list(self):
        client = self._client_returning(b"x")
        regenerate_on_background([self._buf()], "p", client)
        _, kwargs = client.images.edit.call_args
        self.assertFalse(isinstance(kwargs["image"], list))   # 1 image → buffer direct

    def test_multiple_images_sent_as_list(self):
        client = self._client_returning(b"x")
        regenerate_on_background([self._buf(), self._buf(), self._buf()], "p", client)
        _, kwargs = client.images.edit.call_args
        self.assertIsInstance(kwargs["image"], list)          # plusieurs → liste
        self.assertEqual(len(kwargs["image"]), 3)

    def test_forwards_prompt_size_format(self):
        client = self._client_returning(b"x")
        regenerate_on_background([self._buf()], "PROMPT TEST", client, size="1024x1536", output_format="webp")

        _, kwargs = client.images.edit.call_args
        self.assertEqual(kwargs["model"], "gpt-image-1")
        self.assertEqual(kwargs["size"], "1024x1536")
        self.assertEqual(kwargs["output_format"], "webp")
        self.assertEqual(kwargs["quality"], "medium")   # qualité normale, fixe
        self.assertEqual(kwargs["prompt"], "PROMPT TEST")

    def test_default_output_format_is_png(self):
        client = self._client_returning(b"x")
        regenerate_on_background([self._buf()], "p", client)
        _, kwargs = client.images.edit.call_args
        self.assertEqual(kwargs["output_format"], "png")


if __name__ == "__main__":
    unittest.main()
