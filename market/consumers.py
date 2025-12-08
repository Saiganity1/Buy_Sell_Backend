import json
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework_simplejwt.backends import TokenBackend
from django.conf import settings
from .models import Message, Product
from typing import Optional
from channels.db import database_sync_to_async

User = get_user_model()


def room_name_for(user_id: int, partner_id: int, product_id: Optional[int]):
    a, b = sorted([user_id, partner_id])
    if product_id:
        return f"chat_{a}_{b}_{product_id}"
    return f"chat_{a}_{b}"


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Authenticate via JWT token in query string (?token=...)
        qs = parse_qs(self.scope['query_string'].decode())
        token = (qs.get('token') or [None])[0]
        if not token:
            await self.close()
            return
        try:
            backend = TokenBackend(algorithm='HS256', signing_key=settings.SECRET_KEY)
            payload = backend.decode(token, verify=True)
            self.user = await User.objects.aget(id=payload.get('user_id'))
        except Exception:
            await self.close()
            return
        self.partner_id = int(self.scope['url_route']['kwargs']['partner_id'])
        product_id = self.scope['url_route']['kwargs'].get('product_id')
        self.product_id = int(product_id) if product_id is not None else None
        self.room_group_name = room_name_for(self.user.id, self.partner_id, self.product_id)
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        # Broadcast presence online to the room
        await self.channel_layer.group_send(
            self.room_group_name,
            { 'type': 'chat.presence', 'user_id': self.user.id, 'online': True }
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
            # Broadcast presence offline to the room
            await self.channel_layer.group_send(
                self.room_group_name,
                { 'type': 'chat.presence', 'user_id': getattr(self, 'user', None) and self.user.id or None, 'online': False }
            )

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except Exception:
            return
        # Typing indicator (no message persistence)
        if 'typing' in data:
            try:
                is_typing = bool(data.get('typing'))
            except Exception:
                is_typing = False
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'chat.typing',
                'user_id': self.user.id,
                'typing': is_typing,
            })
            return

        content = (data.get('content') or '').strip()
        if not content:
            return
        product = None
        if self.product_id:
            try:
                product = await Product.objects.aget(id=self.product_id)
            except Product.DoesNotExist:
                product = None
        # Persist message
        partner = await User.objects.aget(id=self.partner_id)
        msg = await database_sync_to_async(Message.objects.create)(
            sender=self.user,
            recipient=partner,
            product=product,
            content=content,
            created_at=timezone.now()
        )
        # Debug log: message persisted
        try:
            print(f"[ChatConsumer] persisted msg id={msg.id} sender={self.user.id} recipient={partner.id} room={self.room_group_name}")
        except Exception:
            pass
        payload = {
            'id': msg.id,
            'content': msg.content,
            'sender': {'id': self.user.id, 'username': self.user.username},
            'recipient': {'id': partner.id, 'username': partner.username},
            'product': self.product_id,
            'created_at': msg.created_at.isoformat()
        }
        # Include origin_channel so consumers can avoid echoing back to the sender
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'chat.message',
            'message': payload,
            'origin_channel': self.channel_name,
        })
        # Also notify the recipient's personal notification group so their Messages list can update in realtime
        try:
            await self.channel_layer.group_send(f'user_{partner.id}', {
                'type': 'notify.message',
                'message': {
                    'id': msg.id,
                    'snippet': (msg.content[:140] + '...') if len(msg.content or '') > 140 else msg.content,
                    'sender': {'id': self.user.id, 'username': self.user.username},
                    'product': self.product_id,
                    'created_at': msg.created_at.isoformat(),
                }
            })
        except Exception:
            pass

    async def chat_message(self, event):
        # Avoid echoing messages back to the sender's own websocket connection
        try:
            origin = event.get('origin_channel')
            if origin and origin == self.channel_name:
                # Debug: skip echo
                print(f"[ChatConsumer] skipping echo to origin channel {origin}")
                return
        except Exception:
            pass
        # Debug: forwarding chat message
        try:
            print(f"[ChatConsumer] sending message to {self.channel_name} in room {self.room_group_name}")
        except Exception:
            pass
        await self.send(text_data=json.dumps(event['message']))

    async def chat_typing(self, event):
        await self.send(text_data=json.dumps({
            'event': 'typing',
            'user_id': event.get('user_id'),
            'typing': event.get('typing', False),
        }))

    async def chat_presence(self, event):
        await self.send(text_data=json.dumps({
            'event': 'presence',
            'user_id': event.get('user_id'),
            'online': event.get('online', False),
        }))


class NotificationsConsumer(AsyncWebsocketConsumer):
    """Simple per-user notifications websocket. Clients subscribe to 'user_<id>' group and
    receive lightweight events like new-message notifications.
    """
    async def connect(self):
        qs = parse_qs(self.scope['query_string'].decode())
        token = (qs.get('token') or [None])[0]
        if not token:
            await self.close()
            return
        try:
            backend = TokenBackend(algorithm='HS256', signing_key=settings.SECRET_KEY)
            payload = backend.decode(token, verify=True)
            self.user = await User.objects.aget(id=payload.get('user_id'))
        except Exception:
            await self.close()
            return
        self.group_name = f'user_{self.user.id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        # Send initial unread count (total messages addressed to this user).
        try:
            count = await database_sync_to_async(lambda: Message.objects.filter(recipient=self.user).count())()
            await self.send(text_data=json.dumps({'event': 'unread_count', 'count': count}))
        except Exception:
            pass

    async def receive(self, text_data=None, bytes_data=None):
        # Support simple client messages (ping/pong) and lightweight commands
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except Exception:
            return
        # ping -> pong
        if data.get('type') == 'ping':
            try:
                await self.send(text_data=json.dumps({'event': 'pong'}))
            except Exception:
                pass
            return
        # clients may request a refresh of unread count
        if data.get('type') == 'get_unread_count':
            try:
                count = await database_sync_to_async(lambda: Message.objects.filter(recipient=self.user).count())()
                await self.send(text_data=json.dumps({'event': 'unread_count', 'count': count}))
            except Exception:
                pass
            return

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notify_message(self, event):
        # Forward the notification payload to the connected client
        await self.send(text_data=json.dumps({ 'event': 'new_message', 'message': event.get('message') }))
