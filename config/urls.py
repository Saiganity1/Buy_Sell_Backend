from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from django.views.static import serve
import os

urlpatterns = [
    # Minimal health endpoint at root to satisfy PaaS probes and avoid 404 noise
    path('', lambda request: HttpResponse('ok')),
    path('admin/', admin.site.urls),
    path('api/', include('market.urls')),
]

# Temporary: serve media files at /static/media/... directly from MEDIA_ROOT.
# This helps when running on platforms with ephemeral filesystems (like Render)
# and when uploaded media needs to be accessible immediately. For production
# use a proper object storage (S3) and remove this route.
urlpatterns += [
    re_path(r'^static/media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
