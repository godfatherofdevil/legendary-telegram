from django.contrib import admin
from django.urls import include, path

from config.openapi import api_schema_view, swagger_ui_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", api_schema_view, name="api-schema"),
    path("api/docs/", swagger_ui_view, name="api-docs"),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.chat.urls")),
]
