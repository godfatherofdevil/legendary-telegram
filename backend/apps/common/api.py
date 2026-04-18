from collections.abc import Mapping

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler


def success_response(data, status_code: int = status.HTTP_200_OK) -> Response:
    return Response({"data": data}, status=status_code)


def error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    details: Mapping | list | None = None,
) -> Response:
    payload = {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }
    return Response(payload, status=status_code)


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_detail = "Conflict."


def _format_validation_details(details):
    if isinstance(details, list):
        return {"non_field_errors": details}
    return details


def custom_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)

    response = exception_handler(exc, context)
    if response is None:
        return response

    details = {}
    code = "error"
    message = "Request failed."

    if isinstance(exc, (ValidationError, DjangoValidationError)):
        code = "validation_error"
        message = "Validation failed."
        details = _format_validation_details(response.data)
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif isinstance(exc, NotAuthenticated):
        code = "unauthorized"
        message = "Authentication credentials were not provided."
        response.status_code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(exc, AuthenticationFailed):
        code = "authentication_failed"
        message = "Authentication failed."
        response.status_code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(exc, PermissionDenied):
        code = "forbidden"
        message = "You do not have permission to perform this action."
    elif isinstance(exc, NotFound):
        code = "not_found"
        message = "The requested resource was not found."
    elif isinstance(exc, ConflictError):
        code = str(exc.default_code)
        message = str(exc.detail)
    else:
        if isinstance(response.data, dict):
            details = response.data

    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }
    return response
