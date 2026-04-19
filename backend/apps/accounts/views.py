from django.contrib.auth import get_user_model
from django.db import IntegrityError
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UserSession
from .serializers import (
    AccountDeletionSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegistrationSerializer,
    serialize_public_user,
    serialize_session,
    serialize_user,
)
from .services import (
    authenticate_user,
    change_password,
    cleanup_expired_session_records,
    create_authenticated_session,
    delete_account,
    issue_password_reset,
    reset_password,
    revoke_current_session,
    revoke_session_record,
    sync_session_record,
)
from ..common.api import ConflictError, error_response, success_response

User = get_user_model()


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if User.objects.filter(email__iexact=serializer.validated_data["email"]).exists():
            return error_response(
                code="duplicate_email",
                message="An account with this email already exists.",
                status_code=status.HTTP_409_CONFLICT,
            )
        if User.objects.filter(username=serializer.validated_data["username"]).exists():
            return error_response(
                code="duplicate_username",
                message="This username is already taken.",
                status_code=status.HTTP_409_CONFLICT,
            )

        try:
            user = User.objects.create_user(**serializer.validated_data)
        except IntegrityError as exc:
            raise ConflictError("A user with the provided credentials already exists.") from exc

        return success_response(
            {"user": serialize_user(user, include_presence=False, include_created_at=True)},
            status.HTTP_201_CREATED,
        )


class SessionStatusView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        is_authenticated = bool(getattr(request.user, "is_authenticated", False))
        return success_response({"authenticated": is_authenticated})


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate_user(
            request=request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return error_response(
                code="invalid_credentials",
                message="Invalid email or password.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        session_record = create_authenticated_session(
            request=request,
            user=user,
            remember_me=serializer.validated_data["remember_me"],
        )
        user_data = serialize_user(user, include_presence=False, include_created_at=False)
        session_data = serialize_session(
            session_record,
            is_current=True,
            include_last_seen=False,
            include_expires_at=True,
            include_client_meta=False,
        )
        return success_response({"user": user_data, "session": session_data})


class LogoutView(APIView):
    def post(self, request):
        revoke_current_session(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        sync_session_record(request)
        user_data = serialize_user(request.user, include_presence=True, include_created_at=True)
        return success_response({"user": user_data})


class ChangePasswordView(APIView):
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        try:
            change_password(request=request, **serializer.validated_data)
        except PermissionError:
            return error_response(
                code="invalid_current_password",
                message="Current password is incorrect.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class RequestPasswordResetView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(email__iexact=serializer.validated_data["email"]).first()
        if user:
            issue_password_reset(user=user)

        return success_response({"accepted": True})


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            reset_password(
                raw_token=serializer.validated_data["token"],
                new_password=serializer.validated_data["new_password"],
            )
        except ValueError:
            return error_response(
                code="invalid_reset_token",
                message="The password reset token is invalid or expired.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class DeleteAccountView(APIView):
    def delete(self, request):
        serializer = AccountDeletionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not request.user.check_password(serializer.validated_data["password"]):
            return error_response(
                code="invalid_password",
                message="Password is incorrect.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        user = request.user
        revoke_current_session(request)
        delete_account(user=user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SessionListView(APIView):
    def get(self, request):
        current_session = sync_session_record(request)
        cleanup_expired_session_records()
        sessions = UserSession.objects.filter(
            user=request.user,
            is_currently_valid=True,
        ).order_by("-last_seen_at")
        data = [
            serialize_session(
                session,
                is_current=current_session is not None and session.id == current_session.id,
                include_last_seen=True,
                include_expires_at=False,
                include_client_meta=True,
            )
            for session in sessions
        ]
        return success_response(data)


class SessionDetailView(APIView):
    def delete(self, request, session_id: str):
        current_session = sync_session_record(request)
        session_record = UserSession.objects.filter(
            user=request.user,
            id=session_id,
            is_currently_valid=True,
        ).first()
        if session_record is None:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        is_current = current_session is not None and session_record.id == current_session.id
        revoke_session_record(session_record, actor=request.user)
        if is_current:
            revoke_current_session(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserProfileView(APIView):
    def get(self, request, user_id: str):
        user = User.objects.filter(id=user_id).first()
        if user is None:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return success_response({"user": serialize_public_user(user, include_presence=True)})


class UserByUsernameView(APIView):
    def get(self, request, username: str):
        user = User.objects.filter(username=username).first()
        if user is None:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return success_response({"user": serialize_public_user(user, include_presence=True)})
