import os

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.models import Session
from django.http.cookie import parse_cookie
from rest_framework import serializers

from .models import Dialog, Room
from .realtime import (
    PRESENCE_GROUP,
    dialog_group,
    publish_dialog_summary_updated,
    room_group,
    user_group,
)
from .serializers import serialize_dialog_message, serialize_room_message
from .services import (
    DomainForbiddenError,
    DomainValidationError,
    create_dialog_message,
    create_room_message,
    delete_dialog_message,
    delete_room_message,
    get_dialog_for_user,
    is_room_banned,
    is_room_member,
    mark_dialog_read,
    mark_room_read,
    update_dialog_message,
    update_room_message,
)
from .ws_serializers import (
    DialogMessageDeleteSerializer,
    DialogMessageEditSerializer,
    DialogMessageSendSerializer,
    DialogReadSerializer,
    DialogSubscriptionSerializer,
    PresenceHeartbeatSerializer,
    RoomMessageDeleteSerializer,
    RoomMessageEditSerializer,
    RoomMessageSendSerializer,
    RoomReadSerializer,
    RoomSubscriptionSerializer,
)
from ..presence.services import close_presence_connection, upsert_presence_connection

User = get_user_model()
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self._authenticate_user_from_cookie()
        if user is None or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.user = user
        self.room_subscriptions: set[str] = set()
        self.dialog_subscriptions: set[str] = set()
        await self.accept()

        await self.channel_layer.group_add(user_group(self.user.id), self.channel_name)
        await self.channel_layer.group_add(PRESENCE_GROUP, self.channel_name)

        presence_payload = upsert_presence_connection(
            user=self.user,
            session_key=getattr(self, "session_key", None),
            connection_key=self.channel_name,
        )
        if presence_payload is not None:
            await self._publish_presence_payload(presence_payload)

    async def disconnect(self, close_code):
        if not hasattr(self, "user"):
            return

        for room_id in tuple(self.room_subscriptions):
            await self.channel_layer.group_discard(room_group(room_id), self.channel_name)
        for dialog_id in tuple(self.dialog_subscriptions):
            await self.channel_layer.group_discard(dialog_group(dialog_id), self.channel_name)

        await self.channel_layer.group_discard(user_group(self.user.id), self.channel_name)
        await self.channel_layer.group_discard(PRESENCE_GROUP, self.channel_name)

        presence_payload = close_presence_connection(
            user=self.user,
            connection_key=self.channel_name,
        )
        if presence_payload is not None:
            await self._publish_presence_payload(presence_payload)

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            await self._send_error(code="validation_error", message="Validation failed.")
            return

        event_type = content.get("type")
        payload = content.get("payload")
        request_id = content.get("request_id")

        if not isinstance(event_type, str):
            await self._send_error(
                code="validation_error",
                message="Validation failed.",
                details={"field": "type"},
                request_id=request_id,
            )
            return
        if not isinstance(payload, dict):
            await self._send_error(
                code="validation_error",
                message="Validation failed.",
                details={"field": "payload"},
                request_id=request_id,
            )
            return
        if request_id is not None and not isinstance(request_id, str):
            await self._send_error(
                code="validation_error",
                message="Validation failed.",
                details={"field": "request_id"},
            )
            return

        handler = getattr(self, f"_handle_{event_type.replace('.', '_')}", None)
        if handler is None:
            await self._send_error(
                code="validation_error",
                message="Unsupported event type.",
                details={"field": "type"},
                request_id=request_id,
            )
            return

        try:
            await handler(payload, request_id)
        except serializers.ValidationError as exc:
            await self._send_serializer_error(exc, request_id=request_id)
        except DomainValidationError as exc:
            await self._send_error(
                code="validation_error",
                message=str(exc),
                details=self._validation_details_from_message(str(exc)),
                request_id=request_id,
            )
        except DomainForbiddenError as exc:
            await self._send_error(code="forbidden", message=str(exc), request_id=request_id)
        except (Room.DoesNotExist, Dialog.DoesNotExist):
            await self._send_error(
                code="not_found",
                message="The requested resource was not found.",
                request_id=request_id,
            )
        except Exception as exc:
            if getattr(exc.__class__, "__name__", "") == "DoesNotExist":
                await self._send_error(
                    code="not_found",
                    message="The requested resource was not found.",
                    request_id=request_id,
                )
                return
            raise

    async def broadcast_event(self, event):
        event_type = event["event_type"]
        if event_type.startswith("room."):
            room_id = self._room_id_from_event(event["payload"])
            if room_id is not None and not self._can_receive_room_event(room_id=room_id):
                if room_id in self.room_subscriptions:
                    await self.channel_layer.group_discard(room_group(room_id), self.channel_name)
                    self.room_subscriptions.discard(room_id)
                return
        await self.send_json({"type": event["event_type"], "payload": event["payload"]})

    async def membership_force_room_unsubscribe(self, event):
        room_id = event["payload"]["room_id"]
        if room_id not in self.room_subscriptions:
            return
        await self.channel_layer.group_discard(room_group(room_id), self.channel_name)
        self.room_subscriptions.discard(room_id)

    async def _handle_ping(self, payload, request_id):
        await self.send_json({"type": "pong", "payload": {}})

    async def _handle_presence_heartbeat(self, payload, request_id):
        serializer = PresenceHeartbeatSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        presence_payload = upsert_presence_connection(
            user=self.user,
            session_key=getattr(self, "session_key", None),
            connection_key=self.channel_name,
            tab_id=serializer.validated_data["tab_id"],
            is_active=serializer.validated_data["is_active"],
            last_interaction_at=serializer.validated_data["last_interaction_at"],
        )
        await self._send_ack(request_id)
        if presence_payload is not None:
            await self._publish_presence_payload(presence_payload)

    async def _handle_room_subscribe(self, payload, request_id):
        serializer = RoomSubscriptionSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        room = self._get_room_for_live_access(room_id=serializer.validated_data["room_id"])
        room_id = str(room.id)
        await self.channel_layer.group_add(room_group(room_id), self.channel_name)
        self.room_subscriptions.add(room_id)
        await self._send_ack(request_id)

    async def _handle_room_unsubscribe(self, payload, request_id):
        serializer = RoomSubscriptionSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        room_id = str(serializer.validated_data["room_id"])
        await self.channel_layer.group_discard(room_group(room_id), self.channel_name)
        self.room_subscriptions.discard(room_id)
        await self._send_ack(request_id)

    async def _handle_dialog_subscribe(self, payload, request_id):
        serializer = DialogSubscriptionSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        dialog = get_dialog_for_user(
            dialog_id=serializer.validated_data["dialog_id"],
            user=self.user,
        )
        dialog_id = str(dialog.id)
        await self.channel_layer.group_add(dialog_group(dialog_id), self.channel_name)
        self.dialog_subscriptions.add(dialog_id)
        await self._send_ack(request_id)

    async def _handle_dialog_unsubscribe(self, payload, request_id):
        serializer = DialogSubscriptionSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        dialog_id = str(serializer.validated_data["dialog_id"])
        await self.channel_layer.group_discard(dialog_group(dialog_id), self.channel_name)
        self.dialog_subscriptions.discard(dialog_id)
        await self._send_ack(request_id)

    async def _handle_room_message_send(self, payload, request_id):
        serializer = RoomMessageSendSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        room = self._get_room_for_live_access(room_id=serializer.validated_data["room_id"])
        message = create_room_message(
            room=room,
            sender=self.user,
            text=serializer.validated_data.get("text"),
            reply_to_message_id=serializer.validated_data.get("reply_to_message_id"),
            attachment_ids=[
                str(attachment_id)
                for attachment_id in serializer.validated_data.get("attachment_ids", [])
            ],
        )
        await self._send_ack(request_id)
        payload = {"message": serialize_room_message(message)}
        await self._publish_group_event(
            room_group(message.room_id),
            event_type="room.message.created",
            payload=payload,
        )

    async def _handle_dialog_message_send(self, payload, request_id):
        serializer = DialogMessageSendSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        dialog = get_dialog_for_user(
            dialog_id=serializer.validated_data["dialog_id"],
            user=self.user,
        )
        message = create_dialog_message(
            dialog=dialog,
            sender=self.user,
            text=serializer.validated_data.get("text"),
            reply_to_message_id=serializer.validated_data.get("reply_to_message_id"),
            attachment_ids=[
                str(attachment_id)
                for attachment_id in serializer.validated_data.get("attachment_ids", [])
            ],
        )
        await self._send_ack(request_id)
        payload = {"message": serialize_dialog_message(message)}
        await self._publish_group_event(
            dialog_group(message.dialog_id),
            event_type="dialog.message.created",
            payload=payload,
        )
        publish_dialog_summary_updated(message.dialog, last_message=message)

    async def _handle_room_message_edit(self, payload, request_id):
        serializer = RoomMessageEditSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        room = self._get_room_for_live_access(room_id=serializer.validated_data["room_id"])
        message = update_room_message(
            room=room,
            message_id=serializer.validated_data["message_id"],
            actor=self.user,
            text=serializer.validated_data.get("text"),
        )
        await self._send_ack(request_id)
        payload = {"message": serialize_room_message(message)}
        await self._publish_group_event(
            room_group(message.room_id),
            event_type="room.message.updated",
            payload=payload,
        )

    async def _handle_room_message_delete(self, payload, request_id):
        serializer = RoomMessageDeleteSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        room = self._get_room_for_live_access(room_id=serializer.validated_data["room_id"])
        message_id = serializer.validated_data["message_id"]
        delete_room_message(room=room, message_id=message_id, actor=self.user)
        await self._send_ack(request_id)
        await self._publish_group_event(
            room_group(room.id),
            event_type="room.message.deleted",
            payload={"room_id": str(room.id), "message_id": str(message_id)},
        )

    async def _handle_dialog_message_edit(self, payload, request_id):
        serializer = DialogMessageEditSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        dialog = get_dialog_for_user(
            dialog_id=serializer.validated_data["dialog_id"],
            user=self.user,
        )
        message = update_dialog_message(
            dialog=dialog,
            message_id=serializer.validated_data["message_id"],
            actor=self.user,
            text=serializer.validated_data.get("text"),
        )
        await self._send_ack(request_id)
        payload = {"message": serialize_dialog_message(message)}
        await self._publish_group_event(
            dialog_group(message.dialog_id),
            event_type="dialog.message.updated",
            payload=payload,
        )

    async def _handle_dialog_message_delete(self, payload, request_id):
        serializer = DialogMessageDeleteSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        dialog = get_dialog_for_user(
            dialog_id=serializer.validated_data["dialog_id"],
            user=self.user,
        )
        message_id = serializer.validated_data["message_id"]
        delete_dialog_message(dialog=dialog, message_id=message_id, actor=self.user)
        await self._send_ack(request_id)
        await self._publish_group_event(
            dialog_group(dialog.id),
            event_type="dialog.message.deleted",
            payload={"dialog_id": str(dialog.id), "message_id": str(message_id)},
        )

    async def _handle_room_read(self, payload, request_id):
        serializer = RoomReadSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        room = self._get_room_for_live_access(room_id=serializer.validated_data["room_id"])
        mark_room_read(room=room, user=self.user)
        await self._send_ack(request_id)
        await self._publish_group_event(
            room_group(room.id),
            event_type="room.read.updated",
            payload={"room_id": str(room.id), "user_id": str(self.user.id), "unread_count": 0},
        )

    async def _handle_dialog_read(self, payload, request_id):
        serializer = DialogReadSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        dialog = get_dialog_for_user(
            dialog_id=serializer.validated_data["dialog_id"],
            user=self.user,
        )
        mark_dialog_read(dialog=dialog, user=self.user)
        await self._send_ack(request_id)
        await self._publish_group_event(
            dialog_group(dialog.id),
            event_type="dialog.read.updated",
            payload={"dialog_id": str(dialog.id), "user_id": str(self.user.id), "unread_count": 0},
        )

    def _get_room_for_live_access(self, *, room_id):
        room = Room.objects.filter(id=room_id).select_related("owner_user").first()
        if room is None:
            raise Room.DoesNotExist
        if room.visibility == "private" and not is_room_member(room=room, user=self.user):
            raise Room.DoesNotExist
        if not is_room_member(room=room, user=self.user) or is_room_banned(room=room, user=self.user):
            raise DomainForbiddenError("Not allowed")
        return room

    def _authenticate_user_from_cookie(self):
        headers = dict(self.scope.get("headers", []))
        cookie_header = headers.get(b"cookie", b"").decode("latin1")
        cookies = parse_cookie(cookie_header)
        session_key = cookies.get(settings.SESSION_COOKIE_NAME)
        self.session_key = session_key
        if not session_key:
            self.scope["user"] = AnonymousUser()
            return self.scope["user"]

        session = Session.objects.filter(session_key=session_key).first()
        session_data = session.get_decoded() if session is not None else {}
        user_id = session_data.get(SESSION_KEY)
        backend_path = session_data.get(BACKEND_SESSION_KEY)
        session_hash = session_data.get(HASH_SESSION_KEY)
        if not user_id or not backend_path:
            self.scope["user"] = AnonymousUser()
            return self.scope["user"]

        user = User.objects.filter(pk=user_id).first() or AnonymousUser()
        if not isinstance(user, AnonymousUser) and session_hash != user.get_session_auth_hash():
            user = AnonymousUser()
        self.scope["user"] = user
        return user

    def _room_id_from_event(self, payload: dict) -> str | None:
        if "room_id" in payload:
            return str(payload["room_id"])
        message = payload.get("message")
        if isinstance(message, dict) and message.get("chat_type") == "room":
            return str(message["chat_id"])
        return None

    def _can_receive_room_event(self, *, room_id: str) -> bool:
        try:
            self._get_room_for_live_access(room_id=room_id)
        except (DomainForbiddenError, Room.DoesNotExist):
            return False
        return True

    async def _publish_group_event(self, group_name: str, *, event_type: str, payload: dict):
        await self.channel_layer.group_send(
            group_name,
            {
                "type": "broadcast.event",
                "event_type": event_type,
                "payload": payload,
            },
        )

    async def _publish_presence_payload(self, payload: dict):
        await self._publish_group_event(
            PRESENCE_GROUP,
            event_type="presence.updated",
            payload=payload,
        )

    async def _send_ack(self, request_id):
        await self.send_json(
            {
                "type": "ack",
                "payload": {"accepted": True},
                "request_id": request_id,
            }
        )

    async def _send_error(self, *, code: str, message: str, request_id=None, details=None):
        payload = {
            "type": "error",
            "payload": {
                "code": code,
                "message": message,
                "details": details or {},
            },
        }
        if request_id is not None:
            payload["request_id"] = request_id
        await self.send_json(payload)

    async def _send_serializer_error(self, exc: serializers.ValidationError, *, request_id):
        details = {}
        if isinstance(exc.detail, dict) and exc.detail:
            details["field"] = next(iter(exc.detail.keys()))
        await self._send_error(
            code="validation_error",
            message="Validation failed.",
            details=details,
            request_id=request_id,
        )

    def _validation_details_from_message(self, message: str) -> dict:
        lowered = message.lower()
        if "text" in lowered:
            return {"field": "text"}
        if "attachment" in lowered:
            return {"field": "attachment_ids"}
        if "reply" in lowered:
            return {"field": "reply_to_message_id"}
        return {}
