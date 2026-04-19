from django.http import FileResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.attachments.models import Attachment
from apps.attachments.serializers import AttachmentUploadSerializer
from apps.attachments.services import (
    AttachmentConflictError,
    AttachmentValidationError,
    create_attachment,
    delete_unbound_attachment,
    require_attachment_access,
    serialize_attachment_created,
    serialize_attachment_metadata,
)
from apps.attachments.storage import AttachmentObjectNotFoundError, open_attachment_for_download
from apps.common.api import error_response, success_response


class AttachmentListCreateView(APIView):
    def post(self, request):
        serializer = AttachmentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            attachment = create_attachment(
                uploaded_by_user=request.user,
                uploaded_file=serializer.validated_data["file"],
                comment=serializer.validated_data.get("comment"),
            )
        except AttachmentValidationError as exc:
            return error_response(
                code="validation_error",
                message="Validation failed.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"file": [str(exc)]},
            )
        return success_response(
            {"attachment": serialize_attachment_created(attachment)},
            status.HTTP_201_CREATED,
        )


class AttachmentDetailView(APIView):
    def get_object(self, attachment_id, user) -> Attachment:
        attachment = (
            Attachment.objects.select_related("uploaded_by_user")
            .filter(id=attachment_id)
            .first()
        )
        if attachment is None:
            raise Attachment.DoesNotExist
        require_attachment_access(attachment=attachment, user=user)
        return attachment

    def get(self, request, attachment_id):
        try:
            attachment = self.get_object(attachment_id=attachment_id, user=request.user)
        except Attachment.DoesNotExist:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return success_response({"attachment": serialize_attachment_metadata(attachment)})

    def delete(self, request, attachment_id):
        attachment = Attachment.objects.filter(id=attachment_id).first()
        if attachment is None:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        try:
            delete_unbound_attachment(attachment=attachment, actor=request.user)
        except Attachment.DoesNotExist:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        except AttachmentConflictError as exc:
            return error_response(
                code="conflict",
                message=str(exc),
                status_code=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AttachmentDownloadView(APIView):
    def get(self, request, attachment_id):
        attachment = Attachment.objects.filter(id=attachment_id).first()
        if attachment is None:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        try:
            require_attachment_access(attachment=attachment, user=request.user)
        except Attachment.DoesNotExist:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        try:
            file_handle = open_attachment_for_download(storage_key=attachment.storage_key)
        except AttachmentObjectNotFoundError:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=attachment.original_filename,
            content_type=attachment.content_type,
        )
        response["Content-Length"] = str(attachment.size_bytes)
        return response
