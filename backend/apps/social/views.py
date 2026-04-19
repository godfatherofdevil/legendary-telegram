from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..chat.realtime import (
    publish_dialog_summary_updated,
    publish_friend_request_created,
    publish_friend_request_updated,
)
from ..common.api import error_response, success_response
from .serializers import (
    FriendRequestCreateSerializer,
    PeerBanCreateSerializer,
    serialize_created_friend_request,
    serialize_friend_item,
    serialize_incoming_friend_request,
    serialize_outgoing_friend_request,
    serialize_peer_ban,
)
from .services import (
    SocialConflictError,
    SocialForbiddenError,
    SocialValidationError,
    accept_friend_request,
    create_friend_request,
    create_peer_ban,
    list_friends,
    list_incoming_friend_requests,
    list_outgoing_friend_requests,
    list_peer_bans,
    reject_friend_request,
    remove_friend,
    remove_peer_ban,
)


class FriendListView(APIView):
    def get(self, request):
        data = [
            serialize_friend_item(
                user=item.friend,
                friend_since=item.created_at,
                include_presence=True,
            )
            for item in list_friends(user=request.user)
        ]
        return success_response(data)


class IncomingFriendRequestListView(APIView):
    def get(self, request):
        items = list_incoming_friend_requests(user=request.user)
        return success_response([serialize_incoming_friend_request(item) for item in items])


class OutgoingFriendRequestListView(APIView):
    def get(self, request):
        items = list_outgoing_friend_requests(user=request.user)
        return success_response([serialize_outgoing_friend_request(item) for item in items])


class FriendRequestListCreateView(APIView):
    def post(self, request):
        serializer = FriendRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            friend_request = create_friend_request(
                from_user=request.user,
                username=serializer.validated_data["username"],
                message=serializer.validated_data.get("message"),
            )
        except SocialValidationError as exc:
            return error_response(
                code="validation_error",
                message="Validation failed.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"message": [str(exc)]},
            )
        except SocialForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except SocialConflictError as exc:
            return error_response(
                code="conflict",
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return error_response(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            raise
        publish_friend_request_created(friend_request)
        return success_response(
            {"friend_request": serialize_created_friend_request(friend_request)},
            status.HTTP_201_CREATED,
        )


class FriendRequestAcceptView(APIView):
    def post(self, request, request_id):
        try:
            friendship = accept_friend_request(request_id=request_id, actor=request.user)
        except SocialConflictError as exc:
            return error_response(
                code="conflict",
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return error_response(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            raise
        publish_friend_request_updated(friendship.request)
        return success_response(
            {
                "friendship": serialize_friend_item(
                    user=friendship.friend,
                    friend_since=friendship.created_at,
                    include_presence=False,
                )
            }
        )


class FriendRequestRejectView(APIView):
    def post(self, request, request_id):
        try:
            friend_request = reject_friend_request(request_id=request_id, actor=request.user)
        except SocialConflictError as exc:
            return error_response(
                code="conflict",
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return error_response(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            raise
        publish_friend_request_updated(friend_request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class FriendDetailView(APIView):
    def delete(self, request, user_id):
        try:
            dialog = remove_friend(actor=request.user, other_user_id=user_id)
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return error_response(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            raise
        if dialog is not None:
            publish_dialog_summary_updated(dialog)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PeerBanListCreateView(APIView):
    def get(self, request):
        return success_response(
            [serialize_peer_ban(item) for item in list_peer_bans(user=request.user)]
        )

    def post(self, request):
        serializer = PeerBanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ban = create_peer_ban(
                actor=request.user,
                target_user_id=serializer.validated_data["user_id"],
            )
        except SocialValidationError as exc:
            return error_response(
                code="validation_error",
                message="Validation failed.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"message": [str(exc)]},
            )
        except SocialConflictError as exc:
            return error_response(
                code="conflict",
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return error_response(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            raise
        return success_response(
            {
                "ban": {
                    "user_id": str(ban.target_user_id),
                    "created_at": ban.created_at.isoformat().replace("+00:00", "Z"),
                }
            },
            status.HTTP_201_CREATED,
        )


class PeerBanDetailView(APIView):
    def delete(self, request, user_id):
        try:
            remove_peer_ban(actor=request.user, target_user_id=user_id)
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return error_response(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            raise
        return Response(status=status.HTTP_204_NO_CONTENT)
