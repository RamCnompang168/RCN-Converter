from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from converter import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/convert/", views.convert_media, name="convert_media"),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR)
