from rest_framework import serializers


class AttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)
