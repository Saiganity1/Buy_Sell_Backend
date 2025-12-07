import os
from django.core.asgi import get_asgi_application

# 1) Configure settings BEFORE importing any Django/DRF/Channels code
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# 2) Initialize Django
django_asgi_app = get_asgi_application()

# 3) Now import channels pieces and your app routing (safe after initialization)
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from market.routing import websocket_urlpatterns  # depends on Django settings

# 4) Compose the ASGI application for Daphne
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})