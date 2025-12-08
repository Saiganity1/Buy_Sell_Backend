from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/chat/<int:partner_id>/', consumers.ChatConsumer.as_asgi()),
    path('ws/chat/<int:partner_id>/<int:product_id>/', consumers.ChatConsumer.as_asgi()),
    path('ws/notifications/', consumers.NotificationsConsumer.as_asgi()),
]
