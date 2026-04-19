from django.urls import path

from .views import (
    FriendDetailView,
    FriendListView,
    FriendRequestAcceptView,
    FriendRequestListCreateView,
    FriendRequestRejectView,
    IncomingFriendRequestListView,
    OutgoingFriendRequestListView,
    PeerBanDetailView,
    PeerBanListCreateView,
)

urlpatterns = [
    path("friends", FriendListView.as_view(), name="friend-list"),
    path("friends/<uuid:user_id>", FriendDetailView.as_view(), name="friend-detail"),
    path(
        "friend-requests/incoming",
        IncomingFriendRequestListView.as_view(),
        name="friend-request-incoming-list",
    ),
    path(
        "friend-requests/outgoing",
        OutgoingFriendRequestListView.as_view(),
        name="friend-request-outgoing-list",
    ),
    path("friend-requests", FriendRequestListCreateView.as_view(), name="friend-request-list-create"),
    path(
        "friend-requests/<uuid:request_id>/accept",
        FriendRequestAcceptView.as_view(),
        name="friend-request-accept",
    ),
    path(
        "friend-requests/<uuid:request_id>/reject",
        FriendRequestRejectView.as_view(),
        name="friend-request-reject",
    ),
    path("user-bans", PeerBanListCreateView.as_view(), name="peer-ban-list-create"),
    path("user-bans/<uuid:user_id>", PeerBanDetailView.as_view(), name="peer-ban-detail"),
]
