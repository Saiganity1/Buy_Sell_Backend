from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

urlpatterns = [
    # Minimal health endpoint at root to satisfy PaaS probes and avoid 404 noise
    path('', lambda request: HttpResponse('ok')),
    path('admin/', admin.site.urls),
    path('api/', include('market.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
