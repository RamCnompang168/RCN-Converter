from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import imageio_ffmpeg
import yt_dlp
from django.conf import settings
from django.http import FileResponse, HttpRequest, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from yt_dlp.utils import DownloadError, ExtractorError

logger = logging.getLogger(__name__)
WORK_DIR = settings.BASE_DIR / "runtime"
VIDEO_HEIGHTS = {"144p": 144, "360p": 360, "480p": 480, "720p": 720, "1080p": 1080}
AUDIO_QUALITIES = {"128 kbps": "128", "192 kbps": "192", "256 kbps": "256", "320 kbps": "320"}
SUPPORTED_DOMAINS = ("youtube.com", "youtu.be", "facebook.com", "fb.watch", "tiktok.com", "vm.tiktok.com", "vt.tiktok.com")
YOUTUBE_DOMAINS = ("youtube.com", "youtu.be", "music.youtube.com")
MAX_PLAYLIST_ITEMS = 30

playlist_jobs: dict[str, dict] = {}
playlist_jobs_lock = threading.Lock()


@ensure_csrf_cookie
def home(request: HttpRequest):
    return FileResponse((settings.BASE_DIR / "template" / "index.html").open("rb"), content_type="text/html")


def is_supported_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        host = parsed.hostname.lower() if parsed.hostname else ""
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and any(host == domain or host.endswith(f".{domain}") for domain in SUPPORTED_DOMAINS)


def is_youtube_playlist_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        host = parsed.hostname.lower() if parsed.hostname else ""
    except ValueError:
        return False
    if not (parsed.scheme in {"http", "https"} and any(host == domain or host.endswith(f".{domain}") for domain in YOUTUBE_DOMAINS)):
        return False
    query = parse_qs(parsed.query)
    return "list" in query and bool(query["list"][0].strip())


def format_duration(seconds: int | float | None) -> str:
    if not seconds or seconds < 0:
        return "--:--"
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def sanitize_filename(name: str) -> str:
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return clean[:80] if clean else "playlist"


def delete_job(job_dir: Path) -> None:
    shutil.rmtree(job_dir, ignore_errors=True)


def get_ytdl_options(job_dir: Path, output_format: str, quality: str, ffmpeg_executable: str) -> dict:
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
    return options


@require_POST
def convert_media(request: HttpRequest):
    url = request.POST.get("url", "").strip()
    output_format = request.POST.get("output_format", "")
    quality = request.POST.get("quality", "")

    if not is_supported_url(url):
        return JsonResponse({"detail": "Paste a supported YouTube, Facebook, or TikTok link."}, status=400)
    if is_youtube_playlist_url(url) and request.POST.get("single_video_only") != "1":
        return JsonResponse({
            "is_playlist": True,
            "detail": "This is a YouTube playlist. Use the playlist popup to select videos or download the whole playlist.",
        }, status=400)
    if output_format not in {"mp3", "mp4"}:
        return JsonResponse({"detail": "Choose MP3 or MP4."}, status=400)
    if output_format == "mp3" and quality not in AUDIO_QUALITIES:
        return JsonResponse({"detail": "Choose a valid audio quality."}, status=400)
    if output_format == "mp4" and quality not in VIDEO_HEIGHTS:
        return JsonResponse({"detail": "Choose a valid video quality."}, status=400)

    job_dir = WORK_DIR / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_executable = imageio_ffmpeg.get_ffmpeg_exe()
    options = get_ytdl_options(job_dir, output_format, quality, ffmpeg_executable)

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


@require_POST
def playlist_info(request: HttpRequest):
    url = request.POST.get("url", "").strip()
    if not is_youtube_playlist_url(url):
        return JsonResponse({"detail": "Paste a valid YouTube playlist link."}, status=400)

    options = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "playlistend": MAX_PLAYLIST_ITEMS,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except (DownloadError, ExtractorError) as error:
        logger.warning("Could not fetch playlist info for %s: %s", url, error)
        return JsonResponse({"detail": "Unable to load YouTube playlist. Make sure it is public or unlisted."}, status=422)
    except Exception:
        logger.exception("Unexpected failure fetching playlist info for %s", url)
        return JsonResponse({"detail": "An error occurred while loading the playlist."}, status=500)

    raw_entries = info.get("entries") or []
    entries = []
    for e in raw_entries:
        if not e or not isinstance(e, dict):
            continue
        vid = e.get("id")
        if not vid:
            continue
        title = e.get("title") or "Untitled Video"
        duration = e.get("duration")
        uploader = e.get("uploader") or e.get("channel") or ""
        entries.append({
            "id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "title": title,
            "duration": duration,
            "duration_formatted": format_duration(duration),
            "thumbnail": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            "channel": uploader,
        })

    return JsonResponse({
        "id": info.get("id", ""),
        "title": info.get("title") or "YouTube Playlist",
        "uploader": info.get("uploader") or info.get("channel") or "",
        "total_entries": info.get("playlist_count") or len(entries),
        "displayed_entries": len(entries),
        "max_limit": MAX_PLAYLIST_ITEMS,
        "entries": entries,
    })


def _run_playlist_zip_job(
    job_id: str,
    video_ids: list[str],
    output_format: str,
    quality: str,
    playlist_title: str,
    job_dir: Path,
):
    ffmpeg_executable = imageio_ffmpeg.get_ffmpeg_exe()
    options = get_ytdl_options(job_dir, output_format, quality, ffmpeg_executable)
    total = len(video_ids)

    for idx, vid in enumerate(video_ids):
        video_url = f"https://www.youtube.com/watch?v={vid}"
        with playlist_jobs_lock:
            if job_id not in playlist_jobs:
                delete_job(job_dir)
                return
            playlist_jobs[job_id]["current"] = idx + 1
            playlist_jobs[job_id]["current_title"] = f"Video {idx + 1} of {total}"
            playlist_jobs[job_id]["percent"] = int((idx / total) * 85)

        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(video_url, download=True)
                if info and info.get("title"):
                    with playlist_jobs_lock:
                        if job_id in playlist_jobs:
                            playlist_jobs[job_id]["current_title"] = info.get("title", "")[:60]
        except Exception as err:
            logger.warning("Failed to download video %s in playlist job %s: %s", vid, job_id, err)
            continue

    with playlist_jobs_lock:
        if job_id not in playlist_jobs:
            delete_job(job_dir)
            return
        playlist_jobs[job_id]["current_title"] = "Packaging files into ZIP archive..."
        playlist_jobs[job_id]["percent"] = 90

    target_files = [p for p in job_dir.iterdir() if p.suffix.lower() == f".{output_format}"]
    if not target_files:
        with playlist_jobs_lock:
            if job_id in playlist_jobs:
                playlist_jobs[job_id]["status"] = "failed"
                playlist_jobs[job_id]["error"] = "None of the selected videos could be downloaded."
        delete_job(job_dir)
        return

    safe_title = sanitize_filename(playlist_title)
    zip_filename = f"{safe_title}.zip"
    zip_path = job_dir / zip_filename

    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in target_files:
                zf.write(f, arcname=f.name)
    except Exception as err:
        logger.exception("Failed to create zip for job %s: %s", job_id, err)
        with playlist_jobs_lock:
            if job_id in playlist_jobs:
                playlist_jobs[job_id]["status"] = "failed"
                playlist_jobs[job_id]["error"] = "Failed to create ZIP archive."
        delete_job(job_dir)
        return

    with playlist_jobs_lock:
        if job_id in playlist_jobs:
            playlist_jobs[job_id]["status"] = "completed"
            playlist_jobs[job_id]["percent"] = 100
            playlist_jobs[job_id]["zip_path"] = str(zip_path)
            playlist_jobs[job_id]["filename"] = zip_filename
            playlist_jobs[job_id]["current_title"] = "Complete!"

    def cleanup():
        delete_job(job_dir)
        with playlist_jobs_lock:
            playlist_jobs.pop(job_id, None)

    cleanup_timer = threading.Timer(15 * 60, cleanup)
    cleanup_timer.daemon = True
    cleanup_timer.start()


@require_POST
def playlist_download_zip(request: HttpRequest):
    output_format = request.POST.get("output_format", "")
    quality = request.POST.get("quality", "")
    video_ids_raw = request.POST.get("video_ids", "")
    playlist_title = request.POST.get("playlist_title", "YouTube Playlist").strip()

    if output_format not in {"mp3", "mp4"}:
        return JsonResponse({"detail": "Choose MP3 or MP4."}, status=400)
    if output_format == "mp3" and quality not in AUDIO_QUALITIES:
        return JsonResponse({"detail": "Choose a valid audio quality."}, status=400)
    if output_format == "mp4" and quality not in VIDEO_HEIGHTS:
        return JsonResponse({"detail": "Choose a valid video quality."}, status=400)

    try:
        video_ids = json.loads(video_ids_raw) if video_ids_raw.startswith("[") else [v.strip() for v in video_ids_raw.split(",") if v.strip()]
    except Exception:
        video_ids = []

    if not video_ids:
        return JsonResponse({"detail": "No videos selected for download."}, status=400)

    if len(video_ids) > MAX_PLAYLIST_ITEMS:
        video_ids = video_ids[:MAX_PLAYLIST_ITEMS]

    job_id = uuid.uuid4().hex
    job_dir = WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    with playlist_jobs_lock:
        playlist_jobs[job_id] = {
            "id": job_id,
            "status": "processing",
            "current": 0,
            "total": len(video_ids),
            "current_title": "Starting download...",
            "percent": 0,
            "zip_path": None,
            "filename": "",
            "error": None,
            "created_at": time.time(),
            "job_dir": job_dir,
        }

    thread = threading.Thread(
        target=_run_playlist_zip_job,
        args=(job_id, video_ids, output_format, quality, playlist_title, job_dir),
        daemon=True,
    )
    thread.start()

    return JsonResponse({"job_id": job_id, "total": len(video_ids)})


def playlist_status(request: HttpRequest, job_id: str):
    with playlist_jobs_lock:
        job = playlist_jobs.get(job_id)
        if not job:
            return JsonResponse({"detail": "Job not found or expired."}, status=404)
        return JsonResponse({
            "status": job["status"],
            "current": job["current"],
            "total": job["total"],
            "current_title": job["current_title"],
            "percent": job["percent"],
            "filename": job["filename"],
            "error": job["error"],
            "download_url": f"/api/playlist/file/{job_id}/" if job["status"] == "completed" else None,
        })


def playlist_file(request: HttpRequest, job_id: str):
    with playlist_jobs_lock:
        job = playlist_jobs.get(job_id)
    if not job or job["status"] != "completed" or not job.get("zip_path"):
        return JsonResponse({"detail": "File not found or not ready."}, status=404)

    zip_path = Path(job["zip_path"])
    if not zip_path.is_file():
        return JsonResponse({"detail": "File no longer available."}, status=404)

    return FileResponse(
        zip_path.open("rb"),
        as_attachment=True,
        filename=job["filename"],
        content_type="application/zip",
    )


@require_POST
def playlist_cancel_job(request: HttpRequest, job_id: str):
    with playlist_jobs_lock:
        job = playlist_jobs.pop(job_id, None)
    if job and job.get("job_dir"):
        delete_job(job["job_dir"])
    return JsonResponse({"ok": True})

