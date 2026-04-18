from django.urls import path

from apps.chat.views import (
    DialogListCreateView,
    DialogMessageDetailView,
    DialogMessageListCreateView,
    DialogReadView,
    JoinedRoomListView,
    PublicRoomListView,
    RoomDetailView,
    RoomJoinView,
    RoomLeaveView,
    RoomListCreateView,
    RoomMemberListView,
    RoomMessageDetailView,
    RoomMessageListCreateView,
    RoomReadView,
)

urlpatterns = [
    path("rooms/public", PublicRoomListView.as_view(), name="room-public-list"),
    path("rooms/joined", JoinedRoomListView.as_view(), name="room-joined-list"),
    path("rooms", RoomListCreateView.as_view(), name="room-list-create"),
    path("rooms/<uuid:room_id>", RoomDetailView.as_view(), name="room-detail"),
    path("rooms/<uuid:room_id>/join", RoomJoinView.as_view(), name="room-join"),
    path("rooms/<uuid:room_id>/leave", RoomLeaveView.as_view(), name="room-leave"),
    path("rooms/<uuid:room_id>/members", RoomMemberListView.as_view(), name="room-member-list"),
    path(
        "rooms/<uuid:room_id>/messages",
        RoomMessageListCreateView.as_view(),
        name="room-message-list-create",
    ),
    path(
        "rooms/<uuid:room_id>/messages/<uuid:message_id>",
        RoomMessageDetailView.as_view(),
        name="room-message-detail",
    ),
    path("rooms/<uuid:room_id>/read", RoomReadView.as_view(), name="room-read"),
    path("dialogs", DialogListCreateView.as_view(), name="dialog-list-create"),
    path(
        "dialogs/<uuid:dialog_id>/messages",
        DialogMessageListCreateView.as_view(),
        name="dialog-message-list-create",
    ),
    path(
        "dialogs/<uuid:dialog_id>/messages/<uuid:message_id>",
        DialogMessageDetailView.as_view(),
        name="dialog-message-detail",
    ),
    path("dialogs/<uuid:dialog_id>/read", DialogReadView.as_view(), name="dialog-read"),
]
