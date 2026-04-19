import asyncio
import os
import json
from datetime import timedelta
from importlib import import_module

import pytest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from ..models import Dialog, Room, RoomMembership
from ...common.enums import RoomRole, RoomVisibility
from ...social.models import Friendship
from config.asgi import application

User = get_user_model()
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


def create_user(*, email: str, username: str) -> User:
    return User.objects.create_user(email=email, username=username, password="StrongPassword123!")


def create_room(*, owner: User, name: str, visibility: str, description: str = "desc") -> Room:
    room = Room.objects.create(
        name=name,
        visibility=visibility,
        description=description,
        owner_user=owner,
    )
    RoomMembership.objects.create(
        room=room,
        user=owner,
        role=RoomRole.OWNER,
        joined_at=timezone.now(),
    )
    return room


def make_friends(user_a: User, user_b: User) -> None:
    user_low, user_high = sorted([user_a, user_b], key=lambda user: str(user.id))
    Friendship.objects.create(user_low=user_low, user_high=user_high)


def websocket_headers_for_user(user: User) -> list[tuple[bytes, bytes]]:
    session_engine = import_module(settings.SESSION_ENGINE)
    session = session_engine.SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()
    return [(b"cookie", f"sessionid={session.session_key}".encode("ascii"))]


def post_json_as(*, user: User, url: str, payload: dict) -> object:
    client = Client()
    client.force_login(user)
    return client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
    )


async def connect_user(user: User) -> WebsocketCommunicator:
    headers = websocket_headers_for_user(user)
    communicator = WebsocketCommunicator(
        application,
        "ws/v1/chat",
        headers=headers,
    )
    connected, _subprotocol = await communicator.connect()
    assert connected is True
    await drain_events(communicator)
    return communicator


async def drain_events(communicator: WebsocketCommunicator) -> list[dict]:
    events: list[dict] = []
    while True:
        has_nothing = await communicator.receive_nothing(timeout=0.02)
        if has_nothing:
            return events
        events.append(await communicator.receive_json_from(timeout=0.2))


async def next_event(
    communicator: WebsocketCommunicator,
    *,
    skip_types: tuple[str, ...] = (),
) -> dict:
    while True:
        event = await communicator.receive_json_from(timeout=1)
        if event["type"] in skip_types:
            continue
        return event


@pytest.mark.django_db(transaction=True)
def test_websocket_requires_authenticated_session() -> None:
    async def scenario():
        anonymous = WebsocketCommunicator(application, "ws/v1/chat")
        connected, close_code = await anonymous.connect()
        assert connected is False
        assert close_code == 4401

        user = create_user(email="alice@example.com", username="alice")
        communicator = await connect_user(user)
        await communicator.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_remove_friend_pushes_frozen_dialog_summary_to_both_users() -> None:
    alice = create_user(email="alice-remove-ws@example.com", username="alice-remove-ws")
    bob = create_user(email="bob-remove-ws@example.com", username="bob-remove-ws")
    make_friends(alice, bob)
    user_low, user_high = sorted([alice, bob], key=lambda user: str(user.id))
    dialog = Dialog.objects.create(user_low=user_low, user_high=user_high)

    async def scenario():
        alice_ws = await connect_user(alice)
        bob_ws = await connect_user(bob)
        await drain_events(alice_ws)
        await drain_events(bob_ws)

        client = Client()
        client.force_login(alice)
        response = client.delete(reverse("friend-detail", kwargs={"user_id": bob.id}))
        assert response.status_code == 204

        alice_event = await next_event(alice_ws, skip_types=("presence.updated",))
        bob_event = await next_event(bob_ws, skip_types=("presence.updated",))

        assert alice_event == {
            "type": "dialog.summary.updated",
            "payload": {
                "dialog": {
                    "id": str(dialog.id),
                    "other_user": {
                        "id": str(bob.id),
                        "username": bob.username,
                        "presence": "online",
                    },
                    "unread_count": 0,
                    "is_frozen": True,
                    "last_message": None,
                }
            },
        }
        assert bob_event == {
            "type": "dialog.summary.updated",
            "payload": {
                "dialog": {
                    "id": str(dialog.id),
                    "other_user": {
                        "id": str(alice.id),
                        "username": alice.username,
                        "presence": "online",
                    },
                    "unread_count": 0,
                    "is_frozen": True,
                    "last_message": None,
                }
            },
        }

        await alice_ws.disconnect()
        await bob_ws.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_websocket_ping_and_validation_errors() -> None:
    user = create_user(email="alice@example.com", username="alice")

    async def scenario():
        communicator = await connect_user(user)

        await communicator.send_json_to({"type": "ping", "payload": {}})
        assert await next_event(communicator) == {"type": "pong", "payload": {}}

        await communicator.send_json_to(
            {
                "type": "nope",
                "payload": {},
                "request_id": "req-invalid",
            }
        )
        assert await next_event(communicator) == {
            "type": "error",
            "payload": {
                "code": "validation_error",
                "message": "Unsupported event type.",
                "details": {"field": "type"},
            },
            "request_id": "req-invalid",
        }

        await communicator.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_room_subscription_and_rest_message_broadcast() -> None:
    owner = create_user(email="owner@example.com", username="owner")
    member = create_user(email="member@example.com", username="member")
    outsider = create_user(email="outsider@example.com", username="outsider")
    room = create_room(owner=owner, name="general", visibility=RoomVisibility.PUBLIC)
    RoomMembership.objects.create(
        room=room,
        user=member,
        role=RoomRole.MEMBER,
        joined_at=timezone.now(),
    )
    message_url = reverse("room-message-list-create", kwargs={"room_id": room.id})

    async def scenario():
        member_ws = await connect_user(member)
        outsider_ws = await connect_user(outsider)
        await drain_events(member_ws)
        await drain_events(outsider_ws)

        await member_ws.send_json_to(
            {
                "type": "room.subscribe",
                "payload": {"room_id": str(room.id)},
                "request_id": "req-sub",
            }
        )
        assert await next_event(member_ws) == {
            "type": "ack",
            "payload": {"accepted": True},
            "request_id": "req-sub",
        }

        await outsider_ws.send_json_to(
            {
                "type": "room.subscribe",
                "payload": {"room_id": str(room.id)},
                "request_id": "req-denied",
            }
        )
        denied = await next_event(outsider_ws)
        assert denied["type"] == "error"
        assert denied["payload"]["code"] == "forbidden"
        assert denied["request_id"] == "req-denied"

        response = post_json_as(user=owner, url=message_url, payload={"text": "hello room"})
        assert response.status_code == 201

        created = await next_event(member_ws)
        assert created["type"] == "room.message.created"
        assert created["payload"]["message"]["chat_type"] == "room"
        assert created["payload"]["message"]["chat_id"] == str(room.id)
        assert created["payload"]["message"]["text"] == "hello room"

        await member_ws.disconnect()
        await outsider_ws.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_dialog_websocket_send_edit_delete_and_read_flows() -> None:
    alice = create_user(email="alice@example.com", username="alice")
    bob = create_user(email="bob@example.com", username="bob")
    make_friends(alice, bob)
    user_low, user_high = sorted([alice, bob], key=lambda user: str(user.id))
    dialog = Dialog.objects.create(user_low=user_low, user_high=user_high)

    async def scenario():
        alice_ws = await connect_user(alice)
        bob_ws = await connect_user(bob)
        await drain_events(alice_ws)
        await drain_events(bob_ws)

        for communicator, request_id in ((alice_ws, "req-sub-a"), (bob_ws, "req-sub-b")):
            await communicator.send_json_to(
                {
                    "type": "dialog.subscribe",
                    "payload": {"dialog_id": str(dialog.id)},
                    "request_id": request_id,
                }
            )
            assert await next_event(communicator) == {
                "type": "ack",
                "payload": {"accepted": True},
                "request_id": request_id,
            }

        await alice_ws.send_json_to(
            {
                "type": "dialog.message.send",
                "payload": {
                    "dialog_id": str(dialog.id),
                    "text": "hi bob",
                    "reply_to_message_id": None,
                    "attachment_ids": [],
                },
                "request_id": "req-send",
            }
        )
        assert await next_event(alice_ws) == {
            "type": "ack",
            "payload": {"accepted": True},
            "request_id": "req-send",
        }
        alice_created = await next_event(alice_ws)
        bob_created = await next_event(bob_ws)
        assert alice_created["type"] == "dialog.message.created"
        assert bob_created["type"] == "dialog.message.created"
        message_id = alice_created["payload"]["message"]["id"]

        await alice_ws.send_json_to(
            {
                "type": "dialog.message.edit",
                "payload": {
                    "dialog_id": str(dialog.id),
                    "message_id": message_id,
                    "text": "updated dm",
                },
                "request_id": "req-edit",
            }
        )
        assert await next_event(alice_ws) == {
            "type": "ack",
            "payload": {"accepted": True},
            "request_id": "req-edit",
        }
        assert (await next_event(alice_ws, skip_types=("dialog.summary.updated",)))["type"] == "dialog.message.updated"
        updated_for_bob = await next_event(bob_ws, skip_types=("dialog.summary.updated",))
        assert updated_for_bob["type"] == "dialog.message.updated"
        assert updated_for_bob["payload"]["message"]["text"] == "updated dm"

        await bob_ws.send_json_to(
            {
                "type": "dialog.read",
                "payload": {"dialog_id": str(dialog.id)},
                "request_id": "req-read",
            }
        )
        assert await next_event(bob_ws) == {
            "type": "ack",
            "payload": {"accepted": True},
            "request_id": "req-read",
        }
        assert await next_event(bob_ws) == {
            "type": "dialog.read.updated",
            "payload": {
                "dialog_id": str(dialog.id),
                "user_id": str(bob.id),
                "unread_count": 0,
            },
        }
        read_updated = await next_event(alice_ws, skip_types=("dialog.summary.updated",))
        assert read_updated == {
            "type": "dialog.read.updated",
            "payload": {
                "dialog_id": str(dialog.id),
                "user_id": str(bob.id),
                "unread_count": 0,
            },
        }

        await alice_ws.send_json_to(
            {
                "type": "dialog.message.delete",
                "payload": {
                    "dialog_id": str(dialog.id),
                    "message_id": message_id,
                },
                "request_id": "req-delete",
            }
        )
        assert await next_event(alice_ws) == {
            "type": "ack",
            "payload": {"accepted": True},
            "request_id": "req-delete",
        }
        assert (await next_event(alice_ws, skip_types=("dialog.summary.updated",)))["type"] == "dialog.message.deleted"
        deleted_for_bob = await next_event(bob_ws, skip_types=("dialog.summary.updated",))
        assert deleted_for_bob == {
            "type": "dialog.message.deleted",
            "payload": {
                "dialog_id": str(dialog.id),
                "message_id": message_id,
            },
        }

        await alice_ws.disconnect()
        await bob_ws.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_presence_heartbeat_broadcasts_presence_updates() -> None:
    alice = create_user(email="alice@example.com", username="alice")
    observer = create_user(email="observer@example.com", username="observer")

    async def scenario():
        observer_ws = await connect_user(observer)
        alice_ws = WebsocketCommunicator(
            application,
            "ws/v1/chat",
            headers=websocket_headers_for_user(alice),
        )
        connected, _ = await alice_ws.connect()
        assert connected is True

        presence_online = await next_event(observer_ws)
        assert presence_online["type"] == "presence.updated"
        assert presence_online["payload"]["user_id"] == str(alice.id)
        assert presence_online["payload"]["presence"] == "online"
        await drain_events(alice_ws)

        stale_time = (timezone.now() - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
        await alice_ws.send_json_to(
            {
                "type": "presence.heartbeat",
                "payload": {
                    "tab_id": "tab-1",
                    "is_active": False,
                    "last_interaction_at": stale_time,
                },
                "request_id": "req-heartbeat",
            }
        )
        assert await next_event(alice_ws) == {
            "type": "ack",
            "payload": {"accepted": True},
            "request_id": "req-heartbeat",
        }
        presence_afk = await next_event(observer_ws)
        assert presence_afk["type"] == "presence.updated"
        assert presence_afk["payload"]["user_id"] == str(alice.id)
        assert presence_afk["payload"]["presence"] == "afk"

        await alice_ws.disconnect()
        presence_offline = await next_event(observer_ws)
        assert presence_offline["type"] == "presence.updated"
        assert presence_offline["payload"]["user_id"] == str(alice.id)
        assert presence_offline["payload"]["presence"] == "offline"

        await observer_ws.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_rest_notifications_dialog_updates_and_room_access_revocation_are_sent_over_websocket() -> None:
    sender = create_user(email="sender@example.com", username="sender")
    recipient = create_user(email="recipient@example.com", username="recipient")
    owner = create_user(email="owner@example.com", username="owner")
    private_room = create_room(owner=owner, name="private-room", visibility=RoomVisibility.PRIVATE)
    public_room = create_room(owner=owner, name="public-room", visibility=RoomVisibility.PUBLIC)
    RoomMembership.objects.create(
        room=public_room,
        user=recipient,
        role=RoomRole.MEMBER,
        joined_at=timezone.now(),
    )

    async def scenario():
        sender_ws = await connect_user(sender)
        recipient_ws = await connect_user(recipient)
        await drain_events(sender_ws)

        await recipient_ws.send_json_to(
            {
                "type": "room.subscribe",
                "payload": {"room_id": str(public_room.id)},
                "request_id": "req-room-sub",
            }
        )
        assert await next_event(recipient_ws) == {
            "type": "ack",
            "payload": {"accepted": True},
            "request_id": "req-room-sub",
        }

        friend_request_response = post_json_as(
            user=sender,
            url=reverse("friend-request-list-create"),
            payload={"username": recipient.username, "message": "Let's connect"},
        )
        assert friend_request_response.status_code == 201
        friend_request_id = friend_request_response.json()["data"]["friend_request"]["id"]
        friend_request_event = await next_event(recipient_ws)
        assert friend_request_event["type"] == "friend_request.created"
        assert friend_request_event["payload"]["request"]["from_user"]["username"] == sender.username

        accept_response = post_json_as(
            user=recipient,
            url=reverse("friend-request-accept", kwargs={"request_id": friend_request_id}),
            payload={},
        )
        assert accept_response.status_code == 200
        sender_request_update = await next_event(sender_ws, skip_types=("presence.updated",))
        assert sender_request_update["type"] == "friend_request.updated"
        assert sender_request_update["payload"]["request"]["id"] == friend_request_id
        assert sender_request_update["payload"]["request"]["status"] == "accepted"
        assert sender_request_update["payload"]["request"]["other_user"] == {
            "id": str(recipient.id),
            "username": recipient.username,
        }
        assert sender_request_update["payload"]["request"]["responded_at"] is not None
        recipient_request_update = await next_event(recipient_ws)
        assert recipient_request_update["type"] == "friend_request.updated"
        assert recipient_request_update["payload"]["request"]["status"] == "accepted"

        dialog_response = post_json_as(
            user=recipient,
            url=reverse("dialog-list-create"),
            payload={"user_id": str(sender.id)},
        )
        assert dialog_response.status_code == 200
        dialog_id = dialog_response.json()["data"]["dialog"]["id"]

        sender_dialog_summary = await next_event(sender_ws)
        assert sender_dialog_summary == {
            "type": "dialog.summary.updated",
            "payload": {
                "dialog": {
                    "id": dialog_id,
                    "other_user": {
                        "id": str(recipient.id),
                        "username": recipient.username,
                        "presence": "online",
                    },
                    "unread_count": 0,
                    "is_frozen": False,
                    "last_message": None,
                }
            },
        }
        recipient_dialog_summary = await next_event(recipient_ws)
        assert recipient_dialog_summary["type"] == "dialog.summary.updated"
        assert recipient_dialog_summary["payload"]["dialog"]["id"] == dialog_id
        assert recipient_dialog_summary["payload"]["dialog"]["last_message"] is None

        dialog_message_response = post_json_as(
            user=recipient,
            url=reverse("dialog-message-list-create", kwargs={"dialog_id": dialog_id}),
            payload={"text": "hello from recipient"},
        )
        assert dialog_message_response.status_code == 201

        sender_message_summary = await next_event(sender_ws)
        assert sender_message_summary == {
            "type": "dialog.summary.updated",
            "payload": {
                "dialog": {
                    "id": dialog_id,
                    "other_user": {
                        "id": str(recipient.id),
                        "username": recipient.username,
                        "presence": "online",
                    },
                    "unread_count": 1,
                    "is_frozen": False,
                    "last_message": {
                        "id": dialog_message_response.json()["data"]["message"]["id"],
                        "sender_id": str(recipient.id),
                        "text": "hello from recipient",
                        "created_at": dialog_message_response.json()["data"]["message"]["created_at"],
                    },
                }
            },
        }
        recipient_message_summary = await next_event(recipient_ws)
        assert recipient_message_summary == {
            "type": "dialog.summary.updated",
            "payload": {
                "dialog": {
                    "id": dialog_id,
                    "other_user": {
                        "id": str(sender.id),
                        "username": sender.username,
                        "presence": "online",
                    },
                    "unread_count": 0,
                    "is_frozen": False,
                    "last_message": {
                        "id": dialog_message_response.json()["data"]["message"]["id"],
                        "sender_id": str(recipient.id),
                        "text": "hello from recipient",
                        "created_at": dialog_message_response.json()["data"]["message"]["created_at"],
                    },
                }
            },
        }

        invitation_response = post_json_as(
            user=owner,
            url=reverse("room-invitation-list-create", kwargs={"room_id": private_room.id}),
            payload={"username": recipient.username},
        )
        assert invitation_response.status_code == 201
        invitation_event = await next_event(recipient_ws)
        assert invitation_event == {
            "type": "room.invitation.created",
            "payload": {
                "invitation": {
                    "id": invitation_response.json()["data"]["invitation"]["id"],
                    "room_id": str(private_room.id),
                    "room_name": private_room.name,
                    "created_at": invitation_response.json()["data"]["invitation"]["created_at"],
                }
            },
        }

        remove_response = post_json_as(
            user=owner,
            url=reverse("room-remove-member", kwargs={"room_id": public_room.id}),
            payload={"user_id": str(recipient.id)},
        )
        assert remove_response.status_code == 204
        membership_events = await drain_events(recipient_ws)
        if membership_events:
            assert membership_events[0] == {
                "type": "room.membership.updated",
                "payload": {
                    "room_id": str(public_room.id),
                    "user_id": str(recipient.id),
                    "action": "removed",
                },
            }
        await asyncio.sleep(0.2)

        message_response = post_json_as(
            user=owner,
            url=reverse("room-message-list-create", kwargs={"room_id": public_room.id}),
            payload={"text": "after removal"},
        )
        assert message_response.status_code == 201
        post_removal_events = await drain_events(recipient_ws)
        assert all(event["type"] != "room.message.created" for event in post_removal_events)

        await sender_ws.disconnect()
        await recipient_ws.disconnect()

    async_to_sync(scenario)()
