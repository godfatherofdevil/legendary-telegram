from django.urls import path

from apps.accounts.views import (
    ChangePasswordView,
    DeleteAccountView,
    LoginView,
    LogoutView,
    MeView,
    RegisterView,
    RequestPasswordResetView,
    ResetPasswordView,
    SessionDetailView,
    SessionListView,
)

urlpatterns = [
    path("auth/register", RegisterView.as_view(), name="auth-register"),
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("auth/me", MeView.as_view(), name="auth-me"),
    path("auth/change-password", ChangePasswordView.as_view(), name="auth-change-password"),
    path(
        "auth/request-password-reset",
        RequestPasswordResetView.as_view(),
        name="auth-request-password-reset",
    ),
    path("auth/reset-password", ResetPasswordView.as_view(), name="auth-reset-password"),
    path("account", DeleteAccountView.as_view(), name="account-delete"),
    path("sessions", SessionListView.as_view(), name="session-list"),
    path("sessions/<uuid:session_id>", SessionDetailView.as_view(), name="session-detail"),
]
