from django.contrib import admin
from django.urls import include, path

from apps.common.views import live_view, ready_view
from config.openapi import api_schema_view, swagger_ui_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live/", live_view, name="health-live"),
    path("health/ready/", ready_view, name="health-ready"),
    path("api/schema/", api_schema_view, name="api-schema"),
    path("api/docs/", swagger_ui_view, name="api-docs"),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.presence.urls")),
    path("api/v1/", include("apps.social.urls")),
    path("api/v1/", include("apps.chat.urls")),
    path("api/v1/", include("apps.attachments.urls")),
]
