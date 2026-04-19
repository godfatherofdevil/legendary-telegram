import re
from collections.abc import Iterator

from django.http import HttpResponse, StreamingHttpResponse
from django.utils.http import content_disposition_header
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Attachment
from .serializers import AttachmentUploadSerializer
from .services import (
    AttachmentConflictError,
    AttachmentValidationError,
    create_attachment,
    delete_unbound_attachment,
    require_attachment_access,
    serialize_attachment_created,
    serialize_attachment_metadata,
)
from .storage import AttachmentObjectNotFoundError, open_attachment_for_download
from ..common.api import error_response, success_response

STREAM_CHUNK_SIZE = 64 * 1024
INLINE_CONTENT_TYPE_PREFIXES = ("image/", "video/", "audio/")
SINGLE_RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")


class RangeNotSatisfiableError(Exception):
    pass


def _iter_attachment_chunks(file_handle, *, remaining_bytes: int | None) -> Iterator[bytes]:
    try:
        while True:
            read_size = STREAM_CHUNK_SIZE
            if remaining_bytes is not None:
                if remaining_bytes <= 0:
                    break
                read_size = min(read_size, remaining_bytes)

            chunk = file_handle.read(read_size)
            if not chunk:
                break
            yield chunk

            if remaining_bytes is not None:
                remaining_bytes -= len(chunk)
    finally:
        file_handle.close()


def _is_inline_media_content_type(content_type: str) -> bool:
    return content_type.startswith(INLINE_CONTENT_TYPE_PREFIXES)


def _parse_single_range_header(
    *, range_header: str | None, total_size: int
) -> tuple[int, int] | None:
    if not range_header:
        return None
    if "," in range_header:
        return None

    match = SINGLE_RANGE_PATTERN.fullmatch(range_header.strip())
    if match is None:
        return None

    start_text, end_text = match.groups()
    if not start_text and not end_text:
        return None

    if not start_text:
        suffix_length = int(end_text)
        if suffix_length <= 0:
            return None
        if suffix_length >= total_size:
            return (0, total_size - 1)
        return (total_size - suffix_length, total_size - 1)

    start = int(start_text)
    if start >= total_size:
        raise RangeNotSatisfiableError

    if end_text:
        end = int(end_text)
        if end < start:
            return None
    else:
        end = total_size - 1

    return (start, min(end, total_size - 1))


def _build_attachment_download_response(*, attachment, file_handle, byte_range: tuple[int, int] | None):
    is_partial = byte_range is not None
    content_length = attachment.size_bytes
    if is_partial:
        range_start, range_end = byte_range
        content_length = range_end - range_start + 1

    response = StreamingHttpResponse(
        _iter_attachment_chunks(file_handle, remaining_bytes=content_length),
        status=status.HTTP_206_PARTIAL_CONTENT if is_partial else status.HTTP_200_OK,
        content_type=attachment.content_type,
    )
    response["Accept-Ranges"] = "bytes"
    response["Content-Length"] = str(content_length)
    response["Content-Disposition"] = content_disposition_header(
        as_attachment=not _is_inline_media_content_type(attachment.content_type),
        filename=attachment.original_filename,
    )
    if is_partial:
        response["Content-Range"] = (
            f"bytes {range_start}-{range_end}/{attachment.size_bytes}"
        )
    return response


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
            byte_range = _parse_single_range_header(
                range_header=request.headers.get("Range"),
                total_size=attachment.size_bytes,
            )
        except RangeNotSatisfiableError:
            response = HttpResponse(status=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
            response["Accept-Ranges"] = "bytes"
            response["Content-Range"] = f"bytes */{attachment.size_bytes}"
            return response
        try:
            file_handle = open_attachment_for_download(
                storage_key=attachment.storage_key,
                byte_range=byte_range,
            )
        except AttachmentObjectNotFoundError:
            return error_response(
                code="not_found",
                message="The requested resource was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return _build_attachment_download_response(
            attachment=attachment,
            file_handle=file_handle,
            byte_range=byte_range,
        )
