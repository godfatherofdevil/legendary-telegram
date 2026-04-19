from django.urls import path

from .views import NotificationSummaryView, PresenceQueryView

urlpatterns = [
    path("presence/query", PresenceQueryView.as_view(), name="presence-query"),
    path("notifications/summary", NotificationSummaryView.as_view(), name="notifications-summary"),
]
