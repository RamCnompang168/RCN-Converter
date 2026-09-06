from __future__ import annotations

import shutil
import threading
import uuid
import logging
from pathlib import Path
from urllib.parse import urlparse

import imageio_ffmpeg
import yt_dlp
from django.conf import settings
from django.http import FileResponse, HttpRequest, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from yt_dlp.utils import DownloadError

logger = logging.getLogger(__name__)
WORK_DIR = settings.BASE_DIR / "runtime"
VIDEO_HEIGHTS = {"144p": 144, "360p": 360, "480p": 480, "720p": 720, "1080p": 1080}
AUDIO_QUALITIES = {"128 kbps": "128", "192 kbps": "192", "256 kbps": "256", "320 kbps": "320"}
SUPPORTED_DOMAINS = ("youtube.com", "youtu.be", "facebook.com", "fb.watch", "tiktok.com", "vm.tiktok.com", "vt.tiktok.com")


@ensure_csrf_cookie
def home(request: HttpRequest):
    return FileResponse((settings.BASE_DIR / "index.html").open("rb"), content_type="text/html")


def is_supported_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        host = parsed.hostname.lower() if parsed.hostname else ""
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and any(host == domain or host.endswith(f".{domain}") for domain in SUPPORTED_DOMAINS)


def delete_job(job_dir: Path) -> None:
    shutil.rmtree(job_dir, ignore_errors=True)


@require_POST
def convert_media(request: HttpRequest):
    url = request.POST.get("url", "").strip()
    output_format = request.POST.get("output_format", "")
    quality = request.POST.get("quality", "")

    if not is_supported_url(url):
        return JsonResponse({"detail": "Paste a supported YouTube, Facebook, or TikTok link."}, status=400)
    if output_format not in {"mp3", "mp4"}:
        return JsonResponse({"detail": "Choose MP3 or MP4."}, status=400)
    if output_format == "mp3" and quality not in AUDIO_QUALITIES:
        return JsonResponse({"detail": "Choose a valid audio quality."}, status=400)
    if output_format == "mp4" and quality not in VIDEO_HEIGHTS:
        return JsonResponse({"detail": "Choose a valid video quality."}, status=400)

    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_executable = imageio_ffmpeg.get_ffmpeg_exe()
    options = {
        "outtmpl": str(job_dir / "%(title).80s-%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 2,
        "socket_timeout": 30,
        "ffmpeg_location": ffmpeg_executable,
    }

    if output_format == "mp3":
        options.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": AUDIO_QUALITIES[quality],
            }],
        })
    else:
        height = VIDEO_HEIGHTS[quality]
        options.update({
            "format": f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]/best[height<={height}]",
            "merge_output_format": "mp4",
        })

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.extract_info(url, download=True)
    except DownloadError as error:
        logger.warning("yt-dlp could not download %s: %s", url, error)
        delete_job(job_dir)
        return JsonResponse({"detail": "The source could not be downloaded. Check the Django terminal for the platform's exact reason."}, status=422)
    except Exception:
        logger.exception("Unexpected conversion failure for %s", url)
        delete_job(job_dir)
        return JsonResponse({"detail": "The conversion could not be completed."}, status=500)

    files = [path for path in job_dir.iterdir() if path.suffix.lower() == f".{output_format}"]
    if not files:
        delete_job(job_dir)
        return JsonResponse({"detail": "No compatible output was produced for this link."}, status=422)

    converted_file = files[0]
    response = FileResponse(
        converted_file.open("rb"),
        as_attachment=True,
        filename=converted_file.name,
        content_type="audio/mpeg" if output_format == "mp3" else "video/mp4",
    )
    cleanup_timer = threading.Timer(15 * 60, delete_job, args=[job_dir])
    cleanup_timer.daemon = True
    cleanup_timer.start()
    return response
