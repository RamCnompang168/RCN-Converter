import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client, SimpleTestCase
from yt_dlp.utils import DownloadError

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
        favicon_response = self.client.get("/favicon.ico")
        self.assertEqual(favicon_response.status_code, 301)

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
            self.assertTrue("ffmpeg" in FakeDownloader.last_options["ffmpeg_location"].lower())
            response.close()

    def test_creates_mp4_download_response(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(views, "WORK_DIR", Path(temp_dir)), patch("converter.views.yt_dlp.YoutubeDL", FakeDownloader):
            response = self.post_conversion(url="https://www.tiktok.com/@creator/video/123", output_format="mp4", quality="720p")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "video/mp4")
            self.assertIn(".mp4", response["Content-Disposition"])
            self.assertEqual(b"".join(response.streaming_content), b"converted-media")
            response.close()

    def test_youtube_bot_detection_returns_friendly_error(self):
        class BotErrorDownloader:
            def __init__(self, options):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def extract_info(self, url, download=True):
                raise DownloadError("ERROR: [youtube] rVlsyfq7Vlc: Sign in to confirm you’re not a bot. Use --cookies for authentication.")

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(views, "WORK_DIR", Path(temp_dir)), patch("converter.views.yt_dlp.YoutubeDL", BotErrorDownloader):
            response = self.post_conversion(url="https://youtu.be/rVlsyfq7Vlc", output_format="mp3", quality="128 kbps")
            self.assertEqual(response.status_code, 422)
            data = response.json()
            self.assertEqual(data["detail"], "YouTube temporarily rejected this request. Please try another video or try again later.")

    def test_unavailable_video_returns_friendly_error(self):
        class UnavailableDownloader:
            def __init__(self, options):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def extract_info(self, url, download=True):
                raise DownloadError("ERROR: Video unavailable. This video has been removed by the uploader.")

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(views, "WORK_DIR", Path(temp_dir)), patch("converter.views.yt_dlp.YoutubeDL", UnavailableDownloader):
            response = self.post_conversion(url="https://youtu.be/unavailable", output_format="mp4", quality="720p")
            self.assertEqual(response.status_code, 422)
            data = response.json()
            self.assertEqual(data["detail"], "This video is unavailable or has been removed.")

    def test_options_inject_pot_provider(self):
        with patch.dict(os.environ, {"YOUTUBE_POT_PROVIDER_URL": "http://bgutil-provider:4416"}):
            opts = views.get_base_ytdl_options()
            self.assertIn("extractor_args", opts)
            self.assertEqual(opts["extractor_args"]["youtubepot-bgutilhttp"]["base_url"], ["http://bgutil-provider:4416"])

    def test_cookies_content_staging(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(views, "WORK_DIR", Path(temp_dir)), patch.dict(os.environ, {"YOUTUBE_COOKIES_CONTENT": "# Netscape HTTP Cookie File\n.youtube.com TRUE / FALSE 1800000000 SID sample"}):
            cookie_path = views.get_youtube_cookies_path()
            self.assertIsNotNone(cookie_path)
            self.assertTrue(cookie_path.is_file())
            self.assertIn(".youtube.com", cookie_path.read_text(encoding="utf-8"))

    def test_cleanup_response_deletes_directory_on_close(self):
        temp_parent = tempfile.mkdtemp()
        job_dir = Path(temp_parent) / "job123"
        job_dir.mkdir()
        test_file = job_dir / "sample.mp3"
        test_file.write_bytes(b"content")

        response = views.CleanupFileResponse(test_file.open("rb"), cleanup_dir=job_dir)
        self.assertTrue(job_dir.exists())
        response.close()
        self.assertFalse(job_dir.exists())
        shutil.rmtree(temp_parent, ignore_errors=True)

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

            file_response = self.client.get(data["download_url"])
            self.assertEqual(file_response.status_code, 200)
            self.assertEqual(file_response["Content-Type"], "application/zip")
            self.assertIn("Test Playlist.zip", file_response["Content-Disposition"])
            file_response.close()

    def test_playlist_cancel_job(self):
        cancel_res = self.client.post("/api/playlist/cancel/nonexistent-id/", HTTP_X_CSRFTOKEN=self.csrf_token)
        self.assertEqual(cancel_res.status_code, 200)
        self.assertTrue(cancel_res.json()["ok"])
