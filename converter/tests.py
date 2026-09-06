import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import Client, SimpleTestCase

from converter import views


class FakeDownloader:
    """Creates a small result file without calling an external platform."""

    last_options = None

    def __init__(self, options):
        self.options = options
        type(self).last_options = options

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=True):
        output_format = "mp3" if "postprocessors" in self.options else "mp4"
        output_path = Path(self.options["outtmpl"].replace("%(title).80s-%(id)s.%(ext)s", f"sample.{output_format}"))
        output_path.write_bytes(b"converted-media")
        return {"id": "sample"}


class ConverterRouteTests(SimpleTestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.get("/")
        self.csrf_token = self.client.cookies["csrftoken"].value

    def post_conversion(self, **data):
        return self.client.post("/api/convert/", data, HTTP_X_CSRFTOKEN=self.csrf_token)

    def test_home_and_static_assets_load(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertTrue((settings.BASE_DIR / "styles.css").is_file())
        self.assertTrue((settings.BASE_DIR / "script.js").is_file())
        self.assertTrue((settings.BASE_DIR / "img" / "image_dark.png").is_file())
        self.assertTrue((settings.BASE_DIR / "img" / "image_white.png").is_file())

    def test_rejects_unsupported_link(self):
        response = self.post_conversion(url="https://example.com/media", output_format="mp3", quality="128 kbps")
        self.assertEqual(response.status_code, 400)

    def test_rejects_invalid_quality(self):
        response = self.post_conversion(url="https://youtu.be/example", output_format="mp4", quality="ultra")
        self.assertEqual(response.status_code, 400)

    def test_creates_mp3_download_response(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(views, "WORK_DIR", Path(temp_dir)), patch("converter.views.yt_dlp.YoutubeDL", FakeDownloader):
            response = self.post_conversion(url="https://youtu.be/example", output_format="mp3", quality="128 kbps")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "audio/mpeg")
            self.assertIn(".mp3", response["Content-Disposition"])
            self.assertEqual(b"".join(response.streaming_content), b"converted-media")
            self.assertTrue(FakeDownloader.last_options["ffmpeg_location"].lower().endswith(".exe"))
            response.close()

    def test_creates_mp4_download_response(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(views, "WORK_DIR", Path(temp_dir)), patch("converter.views.yt_dlp.YoutubeDL", FakeDownloader):
            response = self.post_conversion(url="https://www.tiktok.com/@creator/video/123", output_format="mp4", quality="720p")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "video/mp4")
            self.assertIn(".mp4", response["Content-Disposition"])
            self.assertEqual(b"".join(response.streaming_content), b"converted-media")
            response.close()
