import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.staticfiles import finders
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
        if self.options.get("extract_flat"):
            return {
                "id": "PL123",
                "title": "Test Playlist",
                "playlist_count": 2,
                "entries": [
                    {"id": "vid1", "title": "Track 1", "duration": 180, "uploader": "Artist A"},
                    {"id": "vid2", "title": "Track 2", "duration": 240, "uploader": "Artist B"},
                ],
            }
        output_format = "mp3" if "postprocessors" in self.options else "mp4"
        outtmpl = self.options["outtmpl"]
        job_dir = Path(outtmpl).parent
        suffix = url.split("=")[-1] if "=" in url else "sample"
        output_path = job_dir / f"track_{suffix}.{output_format}"
        output_path.write_bytes(b"converted-media")
        return {"id": suffix, "title": f"Title {suffix}"}


class ConverterRouteTests(SimpleTestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.get("/")
        self.csrf_token = self.client.cookies["csrftoken"].value

    def post_conversion(self, **data):
        return self.client.post("/api/convert/", data, HTTP_X_CSRFTOKEN=self.csrf_token)

    def test_home_and_static_assets_load(self):
        home_response = self.client.get("/")
        self.assertEqual(home_response.status_code, 200)
        self.assertContains(home_response, "RCN Converter")
        for asset in ("style/styles.css", "script/script.js", "img/image_dark.png", "img/image_white.png"):
            self.assertIsNotNone(finders.find(asset), msg=f"Missing static asset: {asset}")

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

    def test_playlist_info_rejects_invalid_url(self):
        response = self.client.post("/api/playlist/info/", {"url": "https://example.com/not-a-playlist"}, HTTP_X_CSRFTOKEN=self.csrf_token)
        self.assertEqual(response.status_code, 400)

    def test_playlist_info_fetches_entries(self):
        with patch("converter.views.yt_dlp.YoutubeDL", FakeDownloader):
            response = self.client.post("/api/playlist/info/", {"url": "https://www.youtube.com/playlist?list=PL123"}, HTTP_X_CSRFTOKEN=self.csrf_token)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["title"], "Test Playlist")
            self.assertEqual(len(data["entries"]), 2)
            self.assertEqual(data["entries"][0]["id"], "vid1")
            self.assertEqual(data["entries"][0]["duration_formatted"], "3:00")

    def test_playlist_download_zip_flow(self):
        import time
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(views, "WORK_DIR", Path(temp_dir)), patch("converter.views.yt_dlp.YoutubeDL", FakeDownloader):
            start_response = self.client.post(
                "/api/playlist/download-zip/",
                {
                    "url": "https://www.youtube.com/playlist?list=PL123",
                    "output_format": "mp3",
                    "quality": "128 kbps",
                    "video_ids": '["vid1", "vid2"]',
                    "playlist_title": "Test Playlist",
                },
                HTTP_X_CSRFTOKEN=self.csrf_token,
            )
            self.assertEqual(start_response.status_code, 200)
            job_id = start_response.json()["job_id"]

            # Wait briefly for the worker thread to finish
            for _ in range(50):
                status_res = self.client.get(f"/api/playlist/status/{job_id}/")
                self.assertEqual(status_res.status_code, 200)
                data = status_res.json()
                if data["status"] in ("completed", "failed"):
                    break
                time.sleep(0.05)

            self.assertEqual(data["status"], "completed")
            self.assertEqual(data["percent"], 100)
            self.assertIsNotNone(data["download_url"])

            # Download the zip file
            file_response = self.client.get(data["download_url"])
            self.assertEqual(file_response.status_code, 200)
            self.assertEqual(file_response["Content-Type"], "application/zip")
            self.assertIn("Test Playlist.zip", file_response["Content-Disposition"])
            file_response.close()

    def test_playlist_cancel_job(self):
        cancel_res = self.client.post("/api/playlist/cancel/nonexistent-id/", HTTP_X_CSRFTOKEN=self.csrf_token)
        self.assertEqual(cancel_res.status_code, 200)
        self.assertTrue(cancel_res.json()["ok"])

