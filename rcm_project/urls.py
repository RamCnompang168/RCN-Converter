from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from converter import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/convert/", views.convert_media, name="convert_media"),
    path("api/playlist/info/", views.playlist_info, name="playlist_info"),
    path("api/playlist/download-zip/", views.playlist_download_zip, name="playlist_download_zip"),
    path("api/playlist/status/<str:job_id>/", views.playlist_status, name="playlist_status"),
    path("api/playlist/file/<str:job_id>/", views.playlist_file, name="playlist_file"),
    path("api/playlist/cancel/<str:job_id>/", views.playlist_cancel_job, name="playlist_cancel_job"),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR)
