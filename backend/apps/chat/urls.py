from django.urls import path

from apps.chat.views import (
    DialogListCreateView,
    JoinedRoomListView,
    PublicRoomListView,
    RoomDetailView,
    RoomJoinView,
    RoomLeaveView,
    RoomListCreateView,
    RoomMemberListView,
)

urlpatterns = [
    path("rooms/public", PublicRoomListView.as_view(), name="room-public-list"),
    path("rooms/joined", JoinedRoomListView.as_view(), name="room-joined-list"),
    path("rooms", RoomListCreateView.as_view(), name="room-list-create"),
    path("rooms/<uuid:room_id>", RoomDetailView.as_view(), name="room-detail"),
    path("rooms/<uuid:room_id>/join", RoomJoinView.as_view(), name="room-join"),
    path("rooms/<uuid:room_id>/leave", RoomLeaveView.as_view(), name="room-leave"),
    path("rooms/<uuid:room_id>/members", RoomMemberListView.as_view(), name="room-member-list"),
    path("dialogs", DialogListCreateView.as_view(), name="dialog-list-create"),
]
