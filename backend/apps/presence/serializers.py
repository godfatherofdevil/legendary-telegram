from rest_framework import serializers


class PresenceQuerySerializer(serializers.Serializer):
    user_ids = serializers.ListField(
        child=serializers.UUIDField(format="hex_verbose"),
        allow_empty=False,
        max_length=100,
    )
