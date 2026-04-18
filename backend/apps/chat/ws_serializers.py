from rest_framework import serializers


class PresenceHeartbeatSerializer(serializers.Serializer):
    tab_id = serializers.CharField(max_length=255)
    is_active = serializers.BooleanField()
    last_interaction_at = serializers.DateTimeField()


class RoomSubscriptionSerializer(serializers.Serializer):
    room_id = serializers.UUIDField()


class DialogSubscriptionSerializer(serializers.Serializer):
    dialog_id = serializers.UUIDField()


class RoomMessageSendSerializer(serializers.Serializer):
    room_id = serializers.UUIDField()
    text = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    reply_to_message_id = serializers.UUIDField(required=False, allow_null=True)
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )


class DialogMessageSendSerializer(serializers.Serializer):
    dialog_id = serializers.UUIDField()
    text = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    reply_to_message_id = serializers.UUIDField(required=False, allow_null=True)
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )


class RoomMessageEditSerializer(serializers.Serializer):
    room_id = serializers.UUIDField()
    message_id = serializers.UUIDField()
    text = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class RoomMessageDeleteSerializer(serializers.Serializer):
    room_id = serializers.UUIDField()
    message_id = serializers.UUIDField()


class DialogMessageEditSerializer(serializers.Serializer):
    dialog_id = serializers.UUIDField()
    message_id = serializers.UUIDField()
    text = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class DialogMessageDeleteSerializer(serializers.Serializer):
    dialog_id = serializers.UUIDField()
    message_id = serializers.UUIDField()


class RoomReadSerializer(serializers.Serializer):
    room_id = serializers.UUIDField()


class DialogReadSerializer(serializers.Serializer):
    dialog_id = serializers.UUIDField()
