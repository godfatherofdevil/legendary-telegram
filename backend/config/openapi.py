from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse


def _json_request_body(required_fields: list[str] | None = None) -> dict:
    return {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": required_fields or [],
                }
            }
        },
    }


def _path_parameter(name: str, description: str, schema_format: str | None = None) -> dict:
    schema = {"type": "string"}
    if schema_format:
        schema["format"] = schema_format
    return {
        "name": name,
        "in": "path",
        "required": True,
        "description": description,
        "schema": schema,
    }


def _operation(
    *,
    summary: str,
    tags: list[str],
    description: str,
    response_description: str,
    request_body: dict | None = None,
    parameters: list[dict] | None = None,
    auth_required: bool = True,
    status_code: str = "200",
) -> dict:
    operation = {
        "summary": summary,
        "description": description,
        "tags": tags,
        "responses": {
            status_code: {"description": response_description},
            "401": {"description": "Authentication required."},
            "403": {"description": "Authenticated but not allowed."},
            "404": {"description": "Resource not found or not visible."},
        },
    }
    if request_body is not None:
        operation["requestBody"] = request_body
    if parameters:
        operation["parameters"] = parameters
    operation["security"] = [{"sessionAuth": []}] if auth_required else []
    return operation


def build_openapi_schema(request) -> dict:
    schema_url = request.build_absolute_uri(reverse("api-schema"))
    docs_url = request.build_absolute_uri(reverse("api-docs"))

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Online Chat Server API",
            "version": "v1",
            "description": (
                "Backend REST API documentation for the classic chat application. "
                "Authentication uses Django session cookies."
            ),
        },
        "servers": [{"url": request.build_absolute_uri("/")}],
        "components": {
            "securitySchemes": {
                "sessionAuth": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": settings.SESSION_COOKIE_NAME,
                    "description": "Authenticated Django session cookie.",
                }
            }
        },
        "tags": [
            {"name": "Auth"},
            {"name": "Account"},
            {"name": "Sessions"},
            {"name": "Users"},
            {"name": "Rooms"},
            {"name": "Dialogs"},
            {"name": "Attachments"},
            {"name": "Documentation"},
        ],
        "paths": {
            "/api/schema/": {
                "get": _operation(
                    summary="Get OpenAPI schema",
                    tags=["Documentation"],
                    description="Returns the machine-readable OpenAPI document for the backend.",
                    response_description="OpenAPI schema document.",
                    auth_required=False,
                )
            },
            "/api/docs/": {
                "get": _operation(
                    summary="Open Swagger UI",
                    tags=["Documentation"],
                    description=(
                        "Serves the Swagger UI configured against the backend "
                        "OpenAPI schema."
                    ),
                    response_description="Swagger UI HTML page.",
                    auth_required=False,
                )
            },
            "/api/v1/auth/register": {
                "post": _operation(
                    summary="Register user",
                    tags=["Auth"],
                    description="Creates a new user account.",
                    response_description="Registered user payload.",
                    request_body=_json_request_body(["email", "username", "password"]),
                    auth_required=False,
                    status_code="201",
                )
            },
            "/api/v1/auth/login": {
                "post": _operation(
                    summary="Log in",
                    tags=["Auth"],
                    description="Authenticates a user and issues a session cookie.",
                    response_description="Authenticated user and current session payload.",
                    request_body=_json_request_body(["email", "password", "remember_me"]),
                    auth_required=False,
                )
            },
            "/api/v1/auth/logout": {
                "post": _operation(
                    summary="Log out current session",
                    tags=["Auth"],
                    description="Invalidates only the current browser session.",
                    response_description="Current session invalidated.",
                    status_code="204",
                )
            },
            "/api/v1/auth/me": {
                "get": _operation(
                    summary="Get current user",
                    tags=["Auth"],
                    description="Returns the authenticated user profile.",
                    response_description="Current user payload.",
                )
            },
            "/api/v1/auth/change-password": {
                "post": _operation(
                    summary="Change password",
                    tags=["Auth"],
                    description="Changes the authenticated user's password.",
                    response_description="Password changed.",
                    request_body=_json_request_body(["current_password", "new_password"]),
                    status_code="204",
                )
            },
            "/api/v1/auth/request-password-reset": {
                "post": _operation(
                    summary="Request password reset",
                    tags=["Auth"],
                    description="Requests a password reset email in a privacy-safe way.",
                    response_description="Request accepted.",
                    request_body=_json_request_body(["email"]),
                    auth_required=False,
                )
            },
            "/api/v1/auth/reset-password": {
                "post": _operation(
                    summary="Reset password",
                    tags=["Auth"],
                    description="Resets a password with a valid reset token.",
                    response_description="Password reset.",
                    request_body=_json_request_body(["token", "new_password"]),
                    auth_required=False,
                    status_code="204",
                )
            },
            "/api/v1/account": {
                "delete": _operation(
                    summary="Delete account",
                    tags=["Account"],
                    description="Deletes the authenticated account after password confirmation.",
                    response_description="Account deleted.",
                    request_body=_json_request_body(["password"]),
                    status_code="204",
                )
            },
            "/api/v1/sessions": {
                "get": _operation(
                    summary="List active sessions",
                    tags=["Sessions"],
                    description="Lists active sessions for the authenticated user.",
                    response_description="Session list payload.",
                )
            },
            "/api/v1/sessions/{session_id}": {
                "delete": _operation(
                    summary="Revoke session",
                    tags=["Sessions"],
                    description="Revokes the targeted active session.",
                    response_description="Session revoked.",
                    parameters=[
                        _path_parameter("session_id", "Session identifier.", schema_format="uuid")
                    ],
                    status_code="204",
                )
            },
            "/api/v1/users/by-username/{username}": {
                "get": _operation(
                    summary="Get user by username",
                    tags=["Users"],
                    description="Returns the public user profile for the given username.",
                    response_description="Public user payload.",
                    parameters=[_path_parameter("username", "Immutable username.")],
                )
            },
            "/api/v1/users/{user_id}": {
                "get": _operation(
                    summary="Get user by id",
                    tags=["Users"],
                    description="Returns the public user profile for the given user id.",
                    response_description="Public user payload.",
                    parameters=[
                        _path_parameter("user_id", "User identifier.", schema_format="uuid")
                    ],
                )
            },
            "/api/v1/rooms/public": {
                "get": _operation(
                    summary="List public rooms",
                    tags=["Rooms"],
                    description="Returns paginated public rooms, optionally filtered by search.",
                    response_description="Public room list payload.",
                )
            },
            "/api/v1/rooms/joined": {
                "get": _operation(
                    summary="List joined rooms",
                    tags=["Rooms"],
                    description=(
                        "Returns rooms joined by the authenticated user, "
                        "including unread counts."
                    ),
                    response_description="Joined room list payload.",
                )
            },
            "/api/v1/rooms": {
                "post": _operation(
                    summary="Create room",
                    tags=["Rooms"],
                    description="Creates a new chat room and its owner membership.",
                    response_description="Created room payload.",
                    request_body=_json_request_body(["name", "description", "visibility"]),
                    status_code="201",
                )
            },
            "/api/v1/rooms/{room_id}": {
                "get": _operation(
                    summary="Get room",
                    tags=["Rooms"],
                    description="Returns room details visible to the authenticated user.",
                    response_description="Room detail payload.",
                    parameters=[
                        _path_parameter("room_id", "Room identifier.", schema_format="uuid")
                    ],
                ),
                "patch": _operation(
                    summary="Update room",
                    tags=["Rooms"],
                    description="Updates room properties for authorized users.",
                    response_description="Updated room payload.",
                    request_body=_json_request_body(),
                    parameters=[
                        _path_parameter("room_id", "Room identifier.", schema_format="uuid")
                    ],
                ),
                "delete": _operation(
                    summary="Delete room",
                    tags=["Rooms"],
                    description="Deletes a room for authorized owners.",
                    response_description="Room deleted.",
                    parameters=[
                        _path_parameter("room_id", "Room identifier.", schema_format="uuid")
                    ],
                    status_code="204",
                ),
            },
            "/api/v1/rooms/{room_id}/join": {
                "post": _operation(
                    summary="Join room",
                    tags=["Rooms"],
                    description="Joins a public room when allowed.",
                    response_description="Room joined.",
                    parameters=[
                        _path_parameter("room_id", "Room identifier.", schema_format="uuid")
                    ],
                    status_code="204",
                )
            },
            "/api/v1/rooms/{room_id}/leave": {
                "post": _operation(
                    summary="Leave room",
                    tags=["Rooms"],
                    description="Leaves a joined room when allowed.",
                    response_description="Room left.",
                    parameters=[
                        _path_parameter("room_id", "Room identifier.", schema_format="uuid")
                    ],
                    status_code="204",
                )
            },
            "/api/v1/rooms/{room_id}/members": {
                "get": _operation(
                    summary="List room members",
                    tags=["Rooms"],
                    description="Returns paginated room membership data for room members.",
                    response_description="Room member list payload.",
                    parameters=[
                        _path_parameter("room_id", "Room identifier.", schema_format="uuid")
                    ],
                )
            },
            "/api/v1/dialogs": {
                "get": _operation(
                    summary="List dialogs",
                    tags=["Dialogs"],
                    description="Lists direct-message dialogs for the authenticated user.",
                    response_description="Dialog list payload.",
                ),
                "post": _operation(
                    summary="Create or get dialog",
                    tags=["Dialogs"],
                    description="Creates or retrieves a direct-message dialog with another user.",
                    response_description="Dialog payload.",
                    request_body=_json_request_body(["user_id"]),
                ),
            },
            "/api/v1/attachments": {
                "post": _operation(
                    summary="Upload attachment",
                    tags=["Attachments"],
                    description="Uploads a new unbound attachment for later message binding.",
                    response_description="Created attachment payload.",
                    request_body={
                        "required": True,
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "required": ["file"],
                                }
                            }
                        },
                    },
                    status_code="201",
                )
            },
            "/api/v1/attachments/{attachment_id}": {
                "get": _operation(
                    summary="Get attachment metadata",
                    tags=["Attachments"],
                    description=(
                        "Returns attachment metadata when the authenticated user is authorized."
                    ),
                    response_description="Attachment metadata payload.",
                    parameters=[
                        _path_parameter(
                            "attachment_id",
                            "Attachment identifier.",
                            schema_format="uuid",
                        )
                    ],
                ),
                "delete": _operation(
                    summary="Delete unbound attachment",
                    tags=["Attachments"],
                    description="Deletes an unbound attachment owned by the authenticated user.",
                    response_description="Attachment deleted.",
                    parameters=[
                        _path_parameter(
                            "attachment_id",
                            "Attachment identifier.",
                            schema_format="uuid",
                        )
                    ],
                    status_code="204",
                ),
            },
            "/api/v1/attachments/{attachment_id}/download": {
                "get": _operation(
                    summary="Download attachment",
                    tags=["Attachments"],
                    description="Streams the attachment when the authenticated user is authorized.",
                    response_description="Attachment download stream.",
                    parameters=[
                        _path_parameter(
                            "attachment_id",
                            "Attachment identifier.",
                            schema_format="uuid",
                        )
                    ],
                )
            },
        },
        "externalDocs": {
            "description": "Repository API contract",
            "url": "API_CONTRACT.md",
        },
        "x-docs": {
            "schema_url": schema_url,
            "swagger_ui_url": docs_url,
        },
    }


def api_schema_view(request):
    return JsonResponse(build_openapi_schema(request))


def swagger_ui_view(request):
    return render(
        request,
        "swagger_ui.html",
        {
            "schema_url": reverse("api-schema"),
            "page_title": "Online Chat Server Swagger UI",
        },
    )
