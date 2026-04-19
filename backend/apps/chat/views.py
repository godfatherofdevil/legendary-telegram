from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Room, RoomInvitation
from .realtime import (
    force_room_unsubscribe,
    publish_dialog_message_created,
    publish_dialog_message_deleted,
    publish_dialog_message_updated,
    publish_dialog_read_updated,
    publish_dialog_summary_updated,
    publish_room_invitation_created,
    publish_room_membership_updated,
    publish_room_message_created,
    publish_room_message_deleted,
    publish_room_message_updated,
    publish_room_read_updated,
)
from .serializers import (
    DialogCreateSerializer,
    MessageCreateSerializer,
    MessageUpdateSerializer,
    RoomCreateSerializer,
    RoomUpdateSerializer,
    UserIdSerializer,
    UsernameLookupSerializer,
    serialize_dialog_create,
    serialize_dialog_message,
    serialize_dialog_summary,
    serialize_joined_room_item,
    serialize_room_ban,
    serialize_room_create,
    serialize_room_detail,
    serialize_room_invitation,
    serialize_room_list_item,
    serialize_room_member,
    serialize_room_message,
    serialize_room_update,
)
from .services import (
    DomainConflictError,
    DomainForbiddenError,
    DomainValidationError,
    accept_room_invitation,
    create_dialog_message,
    create_room,
    create_room_ban,
    create_room_invitation,
    create_room_message,
    delete_dialog_message,
    delete_room,
    delete_room_message,
    demote_room_admin,
    encode_cursor,
    get_dialog_for_user,
    get_or_create_dialog,
    get_page_window,
    get_room_for_detail,
    get_user_room_role,
    join_room,
    leave_room,
    list_dialog_message_rows,
    list_dialog_rows,
    list_joined_room_rows,
    list_public_rooms,
    list_room_bans,
    list_room_invitations,
    list_room_members,
    list_room_message_rows,
    mark_dialog_read,
    mark_room_read,
    promote_room_admin,
    reject_room_invitation,
    remove_room_ban,
    update_dialog_message,
    update_room,
    update_room_message,
)
from ..common.api import error_response, success_response
from ..common.enums import ModerationActionType

User = get_user_model()


def _not_found_response():
    return error_response(
        code="not_found",
        message="The requested resource was not found.",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _room_action_view(room_id, user):
    room = Room.objects.filter(id=room_id).first()
    if room is None:
        raise Room.DoesNotExist
    if room.visibility == "private" and get_user_room_role(room=room, user=user) == "none":
        raise Room.DoesNotExist
    return room


class PublicRoomListView(APIView):
    def get(self, request):
        try:
            page = get_page_window(
                raw_limit=request.query_params.get("limit"),
                raw_cursor=request.query_params.get("cursor"),
                default_limit=50,
                max_limit=100,
            )
        except ValueError:
            return error_response(
                code="validation_error",
                message="Validation failed.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"cursor": ["Invalid pagination parameters."]},
            )
        queryset = list_public_rooms(search=request.query_params.get("search"))
        items = list(queryset[page.offset : page.offset + page.limit + 1])
        has_next = len(items) > page.limit
        payload = [serialize_room_list_item(room) for room in items[: page.limit]]
        return Response(
            {
                "data": payload,
                "pagination": {
                    "next_cursor": encode_cursor(page.offset + page.limit) if has_next else None,
                    "limit": page.limit,
                },
            }
        )


class JoinedRoomListView(APIView):
    def get(self, request):
        memberships, unread_counts = list_joined_room_rows(user=request.user)
        payload = [
            serialize_joined_room_item(
                membership=membership, unread_count=unread_counts[membership.room_id]
            )
            for membership in memberships
        ]
        return success_response(payload)


class RoomListCreateView(APIView):
    def post(self, request):
        serializer = RoomCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            room = create_room(owner_user=request.user, **serializer.validated_data)
        except IntegrityError:
            return error_response(
                code="duplicate_room_name",
                message="A room with this name already exists.",
                status_code=status.HTTP_409_CONFLICT,
            )
        return success_response({"room": serialize_room_create(room)}, status.HTTP_201_CREATED)


class RoomDetailView(APIView):
    def get_object(self, room_id, user):
        try:
            return get_room_for_detail(room_id=room_id, user=user)
        except Room.DoesNotExist as exc:
            raise Http404 from exc

    def get(self, request, room_id):
        room = self.get_object(room_id=room_id, user=request.user)
        role = get_user_room_role(room=room, user=request.user)
        return success_response(
            {
                "room": serialize_room_detail(
                    room=room,
                    current_user_role=role,
                    is_member=role != "none",
                )
            }
        )

    def patch(self, request, room_id):
        room = self.get_object(room_id=room_id, user=request.user)
        serializer = RoomUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            room = update_room(room=room, actor=request.user, **serializer.validated_data)
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except IntegrityError:
            return error_response(
                code="duplicate_room_name",
                message="A room with this name already exists.",
                status_code=status.HTTP_409_CONFLICT,
            )
        return success_response({"room": serialize_room_update(room)})

    def delete(self, request, room_id):
        room = self.get_object(room_id=room_id, user=request.user)
        try:
            delete_room(room=room, actor=request.user)
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoomJoinView(APIView):
    def post(self, request, room_id):
        room = Room.objects.filter(id=room_id).first()
        if room is None:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        try:
            join_room(room=room, user=request.user)
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except DomainConflictError as exc:
            return error_response(
                code="conflict",
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )
        publish_room_membership_updated(room_id=room.id, user_id=request.user.id, action="joined")
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoomLeaveView(APIView):
    def post(self, request, room_id):
        room = Room.objects.filter(id=room_id).first()
        if room is None:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        try:
            leave_room(room=room, user=request.user)
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except DomainConflictError as exc:
            return error_response(
                code="conflict",
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )
        publish_room_membership_updated(room_id=room.id, user_id=request.user.id, action="left")
        force_room_unsubscribe(user_id=request.user.id, room_id=room.id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoomMemberListView(APIView):
    def get(self, request, room_id):
        try:
            page = get_page_window(
                raw_limit=request.query_params.get("limit"),
                raw_cursor=request.query_params.get("cursor"),
                default_limit=100,
                max_limit=100,
            )
        except ValueError:
            return error_response(
                code="validation_error",
                message="Validation failed.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"cursor": ["Invalid pagination parameters."]},
            )
        try:
            room = get_room_for_detail(room_id=room_id, user=request.user)
        except Room.DoesNotExist:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if get_user_room_role(room=room, user=request.user) == "none":
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        memberships = list(list_room_members(room=room)[page.offset : page.offset + page.limit + 1])
        has_next = len(memberships) > page.limit
        return Response(
            {
                "data": [
                    serialize_room_member(membership) for membership in memberships[: page.limit]
                ],
                "pagination": {
                    "next_cursor": encode_cursor(page.offset + page.limit) if has_next else None,
                    "limit": page.limit,
                },
            }
        )


class RoomInvitationListCreateView(APIView):
    def get(self, request, room_id):
        try:
            room = _room_action_view(room_id=room_id, user=request.user)
            invitations = list_room_invitations(room=room, actor=request.user)
        except Room.DoesNotExist:
            return _not_found_response()
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return success_response([serialize_room_invitation(item) for item in invitations])

    def post(self, request, room_id):
        serializer = UsernameLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invited_user = User.objects.filter(username=serializer.validated_data["username"]).first()
        if invited_user is None:
            return _not_found_response()
        try:
            room = _room_action_view(room_id=room_id, user=request.user)
            invitation = create_room_invitation(
                room=room,
                actor=request.user,
                invited_user=invited_user,
            )
        except Room.DoesNotExist:
            return _not_found_response()
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except DomainConflictError as exc:
            return error_response(
                code="conflict",
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )
        except DomainValidationError as exc:
            return error_response(
                code="validation_error",
                message="Validation failed.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"message": [str(exc)]},
            )
        publish_room_invitation_created(invitation)
        return success_response(
            {"invitation": serialize_room_invitation(invitation)},
            status.HTTP_201_CREATED,
        )


class RoomInvitationAcceptView(APIView):
    def post(self, request, invitation_id):
        try:
            accept_room_invitation(invitation_id=invitation_id, actor=request.user)
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except DomainConflictError as exc:
            return error_response(
                code="conflict",
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return _not_found_response()
            raise
        invitation = RoomInvitation.objects.filter(
            id=invitation_id,
            invited_user=request.user,
        ).first()
        if invitation is not None:
            publish_room_membership_updated(
                room_id=invitation.room_id,
                user_id=request.user.id,
                action="joined",
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoomInvitationRejectView(APIView):
    def post(self, request, invitation_id):
        try:
            reject_room_invitation(invitation_id=invitation_id, actor=request.user)
        except DomainConflictError as exc:
            return error_response(
                code="conflict",
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return _not_found_response()
            raise
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoomAdminListView(APIView):
    def post(self, request, room_id):
        serializer = UserIdSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_user = User.objects.filter(id=serializer.validated_data["user_id"]).first()
        if target_user is None:
            return _not_found_response()
        try:
            room = _room_action_view(room_id=room_id, user=request.user)
            promote_room_admin(room=room, actor=request.user, target_user=target_user)
        except Room.DoesNotExist:
            return _not_found_response()
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except DomainConflictError as exc:
            return error_response(
                code="conflict",
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )
        publish_room_membership_updated(room_id=room.id, user_id=target_user.id, action="removed")
        force_room_unsubscribe(user_id=target_user.id, room_id=room.id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoomAdminDetailView(APIView):
    def delete(self, request, room_id, user_id):
        target_user = User.objects.filter(id=user_id).first()
        if target_user is None:
            return _not_found_response()
        try:
            room = _room_action_view(room_id=room_id, user=request.user)
            demote_room_admin(room=room, actor=request.user, target_user=target_user)
        except Room.DoesNotExist:
            return _not_found_response()
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except DomainConflictError as exc:
            return error_response(
                code="conflict",
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoomRemoveMemberView(APIView):
    def post(self, request, room_id):
        serializer = UserIdSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_user = User.objects.filter(id=serializer.validated_data["user_id"]).first()
        if target_user is None:
            return _not_found_response()
        try:
            room = _room_action_view(room_id=room_id, user=request.user)
            create_room_ban(
                room=room,
                actor=request.user,
                target_user=target_user,
                action_type=ModerationActionType.MEMBER_REMOVED,
            )
        except Room.DoesNotExist:
            return _not_found_response()
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except DomainConflictError as exc:
            return error_response(
                code="conflict",
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoomBanListCreateView(APIView):
    def get(self, request, room_id):
        try:
            room = _room_action_view(room_id=room_id, user=request.user)
            bans = list_room_bans(room=room, actor=request.user)
        except Room.DoesNotExist:
            return _not_found_response()
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return success_response([serialize_room_ban(item) for item in bans])

    def post(self, request, room_id):
        serializer = UserIdSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_user = User.objects.filter(id=serializer.validated_data["user_id"]).first()
        if target_user is None:
            return _not_found_response()
        try:
            room = _room_action_view(room_id=room_id, user=request.user)
            ban = create_room_ban(
                room=room,
                actor=request.user,
                target_user=target_user,
                action_type=ModerationActionType.MEMBER_BANNED,
            )
        except Room.DoesNotExist:
            return _not_found_response()
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except DomainConflictError as exc:
            return error_response(
                code="conflict",
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )
        publish_room_membership_updated(room_id=room.id, user_id=target_user.id, action="banned")
        force_room_unsubscribe(user_id=target_user.id, room_id=room.id)
        return success_response({"ban": serialize_room_ban(ban)}, status.HTTP_201_CREATED)


class RoomBanDetailView(APIView):
    def delete(self, request, room_id, user_id):
        target_user = User.objects.filter(id=user_id).first()
        if target_user is None:
            return _not_found_response()
        try:
            room = _room_action_view(room_id=room_id, user=request.user)
            remove_room_ban(room=room, actor=request.user, target_user=target_user)
        except Room.DoesNotExist:
            return _not_found_response()
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return _not_found_response()
            raise
        publish_room_membership_updated(room_id=room.id, user_id=target_user.id, action="unbanned")
        return Response(status=status.HTTP_204_NO_CONTENT)


class DialogListCreateView(APIView):
    def get(self, request):
        dialogs, unread_counts, last_messages = list_dialog_rows(user=request.user)
        payload = []
        for dialog in dialogs:
            other_user = (
                dialog.user_high if dialog.user_low_id == request.user.id else dialog.user_low
            )
            payload.append(
                serialize_dialog_summary(
                    dialog=dialog,
                    other_user=other_user,
                    unread_count=unread_counts.get(dialog.id, 0),
                    last_message=last_messages.get(dialog.id),
                )
            )
        return success_response(payload)

    def post(self, request):
        serializer = DialogCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        other_user = User.objects.filter(id=serializer.validated_data["user_id"]).first()
        if other_user is None:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        try:
            dialog, created = get_or_create_dialog(
                current_user=request.user, other_user=other_user
            )
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if created:
            publish_dialog_summary_updated(dialog)
        return success_response({"dialog": serialize_dialog_create(dialog, other_user)})


class RoomMessageListCreateView(APIView):
    def get(self, request, room_id):
        try:
            page = get_page_window(
                raw_limit=request.query_params.get("limit"),
                raw_cursor=request.query_params.get("cursor"),
                default_limit=50,
                max_limit=100,
            )
            room = get_room_for_detail(room_id=room_id, user=request.user)
            messages, has_next = list_room_message_rows(room=room, user=request.user, page=page)
        except ValueError:
            return error_response(
                code="validation_error",
                message="Validation failed.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"cursor": ["Invalid pagination parameters."]},
            )
        except Room.DoesNotExist:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "data": [serialize_room_message(message) for message in messages],
                "pagination": {
                    "next_cursor": encode_cursor(page.offset + page.limit) if has_next else None,
                    "limit": page.limit,
                },
            }
        )

    def post(self, request, room_id):
        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            room = get_room_for_detail(room_id=room_id, user=request.user)
            message = create_room_message(
                room=room,
                sender=request.user,
                text=serializer.validated_data.get("text"),
                reply_to_message_id=serializer.validated_data.get("reply_to_message_id"),
                attachment_ids=[
                    str(value) for value in serializer.validated_data.get("attachment_ids", [])
                ],
            )
        except Room.DoesNotExist:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        except DomainValidationError as exc:
            return error_response(
                code="validation_error",
                message="Validation failed.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"message": [str(exc)]},
            )
        publish_room_message_created(message)
        return success_response(
            {"message": serialize_room_message(message)}, status.HTTP_201_CREATED
        )


class RoomMessageDetailView(APIView):
    def patch(self, request, room_id, message_id):
        serializer = MessageUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            room = get_room_for_detail(room_id=room_id, user=request.user)
            message = update_room_message(
                room=room,
                message_id=message_id,
                actor=request.user,
                text=serializer.validated_data.get("text"),
            )
        except Room.DoesNotExist:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except DomainValidationError as exc:
            return error_response(
                code="validation_error",
                message="Validation failed.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"message": [str(exc)]},
            )
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return error_response(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            raise
        publish_room_message_updated(message)
        return success_response({"message": serialize_room_message(message)})

    def delete(self, request, room_id, message_id):
        try:
            room = get_room_for_detail(room_id=room_id, user=request.user)
            delete_room_message(room=room, message_id=message_id, actor=request.user)
        except Room.DoesNotExist:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return error_response(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            raise
        publish_room_message_deleted(room_id=room.id, message_id=message_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DialogMessageListCreateView(APIView):
    def get(self, request, dialog_id):
        try:
            page = get_page_window(
                raw_limit=request.query_params.get("limit"),
                raw_cursor=request.query_params.get("cursor"),
                default_limit=50,
                max_limit=100,
            )
            dialog = get_dialog_for_user(dialog_id=dialog_id, user=request.user)
            messages, has_next = list_dialog_message_rows(
                dialog=dialog, user=request.user, page=page
            )
        except ValueError:
            return error_response(
                code="validation_error",
                message="Validation failed.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"cursor": ["Invalid pagination parameters."]},
            )
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return error_response(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            raise
        return Response(
            {
                "data": [serialize_dialog_message(message) for message in messages],
                "pagination": {
                    "next_cursor": encode_cursor(page.offset + page.limit) if has_next else None,
                    "limit": page.limit,
                },
            }
        )

    def post(self, request, dialog_id):
        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            dialog = get_dialog_for_user(dialog_id=dialog_id, user=request.user)
            message = create_dialog_message(
                dialog=dialog,
                sender=request.user,
                text=serializer.validated_data.get("text"),
                reply_to_message_id=serializer.validated_data.get("reply_to_message_id"),
                attachment_ids=[
                    str(value) for value in serializer.validated_data.get("attachment_ids", [])
                ],
            )
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except DomainValidationError as exc:
            return error_response(
                code="validation_error",
                message="Validation failed.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"message": [str(exc)]},
            )
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return error_response(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            raise
        publish_dialog_message_created(message)
        publish_dialog_summary_updated(message.dialog, last_message=message)
        return success_response(
            {"message": serialize_dialog_message(message)}, status.HTTP_201_CREATED
        )


class DialogMessageDetailView(APIView):
    def patch(self, request, dialog_id, message_id):
        serializer = MessageUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            dialog = get_dialog_for_user(dialog_id=dialog_id, user=request.user)
            message = update_dialog_message(
                dialog=dialog,
                message_id=message_id,
                actor=request.user,
                text=serializer.validated_data.get("text"),
            )
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except DomainValidationError as exc:
            return error_response(
                code="validation_error",
                message="Validation failed.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"message": [str(exc)]},
            )
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return error_response(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            raise
        publish_dialog_message_updated(message)
        return success_response({"message": serialize_dialog_message(message)})

    def delete(self, request, dialog_id, message_id):
        try:
            dialog = get_dialog_for_user(dialog_id=dialog_id, user=request.user)
            delete_dialog_message(dialog=dialog, message_id=message_id, actor=request.user)
        except DomainForbiddenError as exc:
            return error_response(
                code="forbidden",
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return error_response(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            raise
        publish_dialog_message_deleted(dialog_id=dialog.id, message_id=message_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoomReadView(APIView):
    def post(self, request, room_id):
        try:
            room = get_room_for_detail(room_id=room_id, user=request.user)
            mark_room_read(room=room, user=request.user)
        except Room.DoesNotExist:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        publish_room_read_updated(room_id=room.id, user_id=request.user.id, unread_count=0)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DialogReadView(APIView):
    def post(self, request, dialog_id):
        try:
            dialog = get_dialog_for_user(dialog_id=dialog_id, user=request.user)
            mark_dialog_read(dialog=dialog, user=request.user)
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist":
                return error_response(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            raise
        publish_dialog_read_updated(dialog_id=dialog.id, user_id=request.user.id, unread_count=0)
        return Response(status=status.HTTP_204_NO_CONTENT)
