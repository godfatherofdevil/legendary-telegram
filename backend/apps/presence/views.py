from rest_framework import status
from rest_framework.views import APIView

from ..common.api import success_response
from .serializers import PresenceQuerySerializer
from .services import get_notification_summary, get_presence_snapshots


class PresenceQueryView(APIView):
    def post(self, request):
        serializer = PresenceQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success_response(
            get_presence_snapshots(user_ids=serializer.validated_data["user_ids"])
        )


class NotificationSummaryView(APIView):
    def get(self, request):
        return success_response(get_notification_summary(user=request.user), status.HTTP_200_OK)
