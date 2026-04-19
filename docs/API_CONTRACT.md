# API_CONTRACT.md

## 1. Purpose

This document defines the complete API contract for the Online Chat Server.

It is normative and implementation-facing. Backend, frontend, websocket consumers, and automated agents MUST follow this contract exactly unless an explicit versioned change is introduced.

This contract covers:

- REST API endpoints
- WebSocket endpoint and message protocol
- Authentication rules
- Error model
- Pagination model
- Presence model
- Room and personal chat semantics
- Attachments and access control
- Moderation actions
- Session management

This contract assumes:

- classic web chat application
- persistent storage
- browser-based frontend
- authenticated REST + authenticated WebSocket
- support for up to 300 concurrent users

---

## 2. General Conventions

### 2.1 Base URL

All REST endpoints MUST be served under:

```text
/api/v1
````

Example:

```text
/api/v1/auth/login
```

### 2.2 WebSocket Base URL

WebSocket connections MUST be served under:

```text
/ws/v1/chat
```

### 2.3 Content Type

REST requests and responses MUST use:

```http
Content-Type: application/json
```

except for file upload endpoints which MUST use:

```http
Content-Type: multipart/form-data
```

### 2.4 Time Format

All timestamps MUST be ISO 8601 UTC timestamps.

Example:

```json
"2026-04-18T10:15:30Z"
```

### 2.5 Identifier Format

This contract does not mandate a specific database identifier type, but all public identifiers MUST be serialized as strings.

Examples:

```json
"id": "usr_01"
"id": "room_01"
"id": "msg_01"
```

### 2.6 Authentication Transport

REST authentication MUST use secure cookie-based session authentication.

Requirements:

* login MUST create a server-managed authenticated session
* session cookie MUST be `HttpOnly`
* session cookie MUST be `Secure` in production
* persistent login MUST be supported
* logout MUST invalidate only the current session unless explicitly terminating another session via session management API

WebSocket authentication MUST reuse the authenticated browser session cookie.

### 2.7 UTF-8

All text fields MUST support UTF-8.

### 2.8 Message Size Limit

Plain text message body MUST NOT exceed 3 KB after UTF-8 encoding.

### 2.9 Room Name Uniqueness

Room names MUST be globally unique.

### 2.10 Username Immutability

Usernames MUST be immutable after registration.

---

## 3. API Versioning

### 3.1 Version Prefix

All endpoints MUST be versioned under `/api/v1` and `/ws/v1`.

### 3.1.1 Documentation Endpoints

The backend MAY expose non-product documentation endpoints outside the versioned API namespace for developer discovery.

Current documentation endpoints:

```text
/api/schema/
/api/docs/
```

Rules:

* `/api/schema/` returns an OpenAPI document for the currently implemented backend REST surface
* `/api/docs/` serves a Swagger UI backed by `/api/schema/`
* these endpoints do not change the versioning rules for product REST endpoints under `/api/v1`

### 3.2 Breaking Changes

Breaking changes MUST NOT be introduced without a new version namespace.

---

## 4. Standard Response Model

### 4.1 Success Response Pattern

REST success responses SHOULD use a consistent JSON object shape:

```json
{
  "data": {}
}
```

For list endpoints:

```json
{
  "data": [],
  "pagination": {}
}
```

### 4.2 Error Response Pattern

All non-2xx responses MUST return:

```json
{
  "error": {
    "code": "string_code",
    "message": "Human readable message",
    "details": {}
  }
}
```

### 4.3 Error Object Fields

* `code`: stable machine-readable code
* `message`: human-readable summary
* `details`: optional object with structured fields

Example:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Room name is required",
    "details": {
      "field": "name"
    }
  }
}
```

---

## 5. HTTP Status Code Rules

The API MUST use the following status codes consistently:

* `200 OK` — successful read/update/delete action returning payload
* `201 Created` — successful creation
* `202 Accepted` — accepted asynchronous processing, only if ever needed
* `204 No Content` — successful action with no response body
* `400 Bad Request` — malformed request or invalid semantics
* `401 Unauthorized` — unauthenticated
* `403 Forbidden` — authenticated but not allowed
* `404 Not Found` — resource not found or not visible
* `409 Conflict` — uniqueness or state conflict
* `413 Payload Too Large` — attachment or message too large
* `415 Unsupported Media Type` — unsupported upload content type where enforced
* `422 Unprocessable Entity` — validation failure
* `429 Too Many Requests` — rate limited
* `500 Internal Server Error` — server-side failure

### 5.1 Visibility-Safe 404

The server MAY return `404 Not Found` instead of `403 Forbidden` for private resources when that better preserves privacy.

---

## 6. Pagination Contract

List endpoints returning potentially large collections MUST support cursor pagination.

### 6.1 Request Parameters

```text
?limit=50&cursor=opaque_cursor
```

### 6.2 Response Shape

```json
{
  "data": [],
  "pagination": {
    "next_cursor": "opaque_cursor_or_null",
    "limit": 50
  }
}
```

### 6.3 Rules

* `limit` defaults MUST be endpoint-specific
* `limit` MUST have a safe maximum
* cursors MUST be opaque to clients
* ordering MUST be stable for a given cursor stream

---

## 7. Authentication API

## 7.1 Session Status

### Endpoint

```http
GET /api/v1/auth/session-status
```

### Behavior

* MUST be callable without authentication
* MUST report whether the current browser session is authenticated
* MUST be safe to use before login or registration

### Response

```json
{
  "data": {
    "authenticated": false
  }
}
```

---

## 7.2 Register

### Endpoint

```http
POST /api/v1/auth/register
```

### Request

```json
{
  "email": "alice@example.com",
  "username": "alice",
  "password": "StrongPassword123!"
}
```

### Validation Rules

* `email` is required
* `email` must be unique
* `username` is required
* `username` must be unique
* `username` cannot be changed later
* `password` is required

### Response

```http
201 Created
```

```json
{
  "data": {
    "user": {
      "id": "usr_01",
      "email": "alice@example.com",
      "username": "alice",
      "created_at": "2026-04-18T10:00:00Z"
    }
  }
}
```

### Errors

* `409 Conflict` — duplicate email
* `409 Conflict` — duplicate username
* `422 Unprocessable Entity` — validation failure

---

## 7.3 Login

### Endpoint

```http
POST /api/v1/auth/login
```

### Request

```json
{
  "email": "alice@example.com",
  "password": "StrongPassword123!",
  "remember_me": true
}
```

### Behavior

* MUST authenticate by email + password
* MUST create a server-side session
* MUST set session cookie
* MUST support persistent login when `remember_me = true`

### Response

```http
200 OK
```

```json
{
  "data": {
    "user": {
      "id": "usr_01",
      "email": "alice@example.com",
      "username": "alice"
    },
    "session": {
      "id": "sess_current",
      "created_at": "2026-04-18T10:05:00Z",
      "expires_at": "2026-05-18T10:05:00Z",
      "is_current": true
    }
  }
}
```

### Errors

* `401 Unauthorized` — invalid credentials

---

## 7.4 Logout Current Session

### Endpoint

```http
POST /api/v1/auth/logout
```

### Behavior

* MUST invalidate only current browser session

### Response

```http
204 No Content
```

---

## 7.5 Get Current Authenticated User

### Endpoint

```http
GET /api/v1/auth/me
```

### Response

```json
{
  "data": {
    "user": {
      "id": "usr_01",
      "email": "alice@example.com",
      "username": "alice",
      "presence": "online",
      "created_at": "2026-04-18T10:00:00Z"
    }
  }
}
```

### Errors

* `401 Unauthorized`

---

## 7.6 Change Password

### Endpoint

```http
POST /api/v1/auth/change-password
```

### Request

```json
{
  "current_password": "OldPassword123!",
  "new_password": "NewPassword123!"
}
```

### Response

```http
204 No Content
```

### Errors

* `401 Unauthorized`
* `422 Unprocessable Entity`
* `403 Forbidden` if current password is wrong

---

## 7.7 Request Password Reset

### Endpoint

```http
POST /api/v1/auth/request-password-reset
```

### Request

```json
{
  "email": "alice@example.com"
}
```

### Behavior

* MUST initiate password reset flow
* response MUST NOT reveal whether email exists

### Response

```json
{
  "data": {
    "accepted": true
  }
}
```

---

## 7.8 Confirm Password Reset

### Endpoint

```http
POST /api/v1/auth/reset-password
```

### Request

```json
{
  "token": "reset_token",
  "new_password": "NewPassword123!"
}
```

### Response

```http
204 No Content
```

### Errors

* `400 Bad Request`
* `403 Forbidden`
* `422 Unprocessable Entity`

---

## 7.9 Delete Account

### Endpoint

```http
DELETE /api/v1/account
```

### Request

```json
{
  "password": "CurrentPassword123!"
}
```

### Behavior

When successful:

* user account MUST be deleted
* rooms owned by user MUST be deleted
* all messages/files/images in those owned rooms MUST be deleted permanently
* membership in all other rooms MUST be removed

### Response

```http
204 No Content
```

---

## 8. Sessions API

## 8.1 List Active Sessions

### Endpoint

```http
GET /api/v1/sessions
```

### Response

```json
{
  "data": [
    {
      "id": "sess_01",
      "ip_address": "203.0.113.5",
      "user_agent": "Chrome on Linux",
      "created_at": "2026-04-18T10:05:00Z",
      "last_seen_at": "2026-04-18T10:15:00Z",
      "is_current": true
    },
    {
      "id": "sess_02",
      "ip_address": "203.0.113.8",
      "user_agent": "Firefox on Windows",
      "created_at": "2026-04-17T15:05:00Z",
      "last_seen_at": "2026-04-18T08:00:00Z",
      "is_current": false
    }
  ]
}
```

---

## 8.2 Revoke Specific Session

### Endpoint

```http
DELETE /api/v1/sessions/{session_id}
```

### Behavior

* MUST invalidate the selected session
* MUST allow revoking current or non-current session
* if current session is revoked, current browser becomes logged out

### Response

```http
204 No Content
```

### Errors

* `404 Not Found`

---

## 9. Users API

## 9.1 Get User Public Profile

### Endpoint

```http
GET /api/v1/users/{user_id}
```

### Response

```json
{
  "data": {
    "user": {
      "id": "usr_02",
      "username": "bob",
      "presence": "afk"
    }
  }
}
```

### Notes

* private fields such as email MUST NOT be exposed here

---

## 9.2 Find User by Username

### Endpoint

```http
GET /api/v1/users/by-username/{username}
```

### Response

```json
{
  "data": {
    "user": {
      "id": "usr_02",
      "username": "bob",
      "presence": "offline"
    }
  }
}
```

---

## 10. Friends API

## 10.1 List Friends

### Endpoint

```http
GET /api/v1/friends
```

### Response

```json
{
  "data": [
    {
      "user": {
        "id": "usr_02",
        "username": "bob",
        "presence": "online"
      },
      "friend_since": "2026-04-01T09:00:00Z"
    }
  ]
}
```

---

## 10.2 List Incoming Friend Requests

### Endpoint

```http
GET /api/v1/friend-requests/incoming
```

### Response

```json
{
  "data": [
    {
      "id": "fr_01",
      "from_user": {
        "id": "usr_02",
        "username": "bob"
      },
      "message": "Let's connect",
      "created_at": "2026-04-18T10:20:00Z"
    }
  ]
}
```

---

## 10.3 List Outgoing Friend Requests

### Endpoint

```http
GET /api/v1/friend-requests/outgoing
```

### Response

```json
{
  "data": [
    {
      "id": "fr_02",
      "to_user": {
        "id": "usr_03",
        "username": "carol"
      },
      "message": "Hi",
      "created_at": "2026-04-18T10:21:00Z"
    }
  ]
}
```

---

## 10.4 Send Friend Request

### Endpoint

```http
POST /api/v1/friend-requests
```

### Request

```json
{
  "username": "bob",
  "message": "Let's connect"
}
```

### Response

```http
201 Created
```

```json
{
  "data": {
    "friend_request": {
      "id": "fr_01",
      "to_user": {
        "id": "usr_02",
        "username": "bob"
      },
      "message": "Let's connect",
      "status": "pending",
      "created_at": "2026-04-18T10:20:00Z"
    }
  }
}
```

### Errors

* `404 Not Found` — username does not exist
* `409 Conflict` — already friends or already requested
* `403 Forbidden` — blocked by target user

---

## 10.5 Accept Friend Request

### Endpoint

```http
POST /api/v1/friend-requests/{request_id}/accept
```

### Response

```json
{
  "data": {
    "friendship": {
      "user": {
        "id": "usr_02",
        "username": "bob"
      },
      "friend_since": "2026-04-18T10:25:00Z"
    }
  }
}
```

---

## 10.6 Reject Friend Request

### Endpoint

```http
POST /api/v1/friend-requests/{request_id}/reject
```

### Response

```http
204 No Content
```

---

## 10.7 Remove Friend

### Endpoint

```http
DELETE /api/v1/friends/{user_id}
```

### Behavior

* MUST remove friendship relationship
* MUST also disable personal messaging until re-friended

### Response

```http
204 No Content
```

---

## 10.8 Ban User at Peer Level

### Endpoint

```http
POST /api/v1/user-bans
```

### Request

```json
{
  "user_id": "usr_02"
}
```

### Behavior

* banned user MUST NOT be able to contact banning user
* existing personal dialog MUST remain visible but read-only/frozen
* friendship MUST be terminated

### Response

```http
201 Created
```

```json
{
  "data": {
    "ban": {
      "user_id": "usr_02",
      "created_at": "2026-04-18T10:30:00Z"
    }
  }
}
```

---

## 10.9 Unban User at Peer Level

### Endpoint

```http
DELETE /api/v1/user-bans/{user_id}
```

### Response

```http
204 No Content
```

---

## 10.10 List Peer Bans

### Endpoint

```http
GET /api/v1/user-bans
```

### Response

```json
{
  "data": [
    {
      "user": {
        "id": "usr_02",
        "username": "bob"
      },
      "created_at": "2026-04-18T10:30:00Z"
    }
  ]
}
```

---

## 11. Room API

## 11.1 List Public Rooms

### Endpoint

```http
GET /api/v1/rooms/public?search=eng&limit=50&cursor=opaque
```

### Response

```json
{
  "data": [
    {
      "id": "room_01",
      "name": "engineering",
      "description": "Backend and frontend discussions",
      "visibility": "public",
      "member_count": 38,
      "owner": {
        "id": "usr_01",
        "username": "alice"
      }
    }
  ],
  "pagination": {
    "next_cursor": null,
    "limit": 50
  }
}
```

---

## 11.2 List Joined Rooms

### Endpoint

```http
GET /api/v1/rooms/joined
```

### Response

```json
{
  "data": [
    {
      "id": "room_01",
      "name": "engineering",
      "description": "Backend and frontend discussions",
      "visibility": "public",
      "member_count": 38,
      "unread_count": 3
    },
    {
      "id": "room_02",
      "name": "core-team",
      "description": "Private planning",
      "visibility": "private",
      "member_count": 5,
      "unread_count": 0
    }
  ]
}
```

---

## 11.3 Create Room

### Endpoint

```http
POST /api/v1/rooms
```

### Request

```json
{
  "name": "engineering",
  "description": "Backend and frontend discussions",
  "visibility": "public"
}
```

### Rules

* `name` required and globally unique
* `visibility` MUST be `public` or `private`

### Response

```http
201 Created
```

```json
{
  "data": {
    "room": {
      "id": "room_01",
      "name": "engineering",
      "description": "Backend and frontend discussions",
      "visibility": "public",
      "owner": {
        "id": "usr_01",
        "username": "alice"
      },
      "created_at": "2026-04-18T10:35:00Z"
    }
  }
}
```

### Errors

* `409 Conflict` — duplicate room name
* `422 Unprocessable Entity`

---

## 11.4 Get Room Details

### Endpoint

```http
GET /api/v1/rooms/{room_id}
```

### Response

```json
{
  "data": {
    "room": {
      "id": "room_01",
      "name": "engineering",
      "description": "Backend and frontend discussions",
      "visibility": "public",
      "owner": {
        "id": "usr_01",
        "username": "alice"
      },
      "admins": [
        {
          "id": "usr_01",
          "username": "alice"
        },
        {
          "id": "usr_04",
          "username": "dave"
        }
      ],
      "member_count": 38,
      "created_at": "2026-04-18T10:35:00Z",
      "current_user_role": "admin",
      "is_member": true
    }
  }
}
```

---

## 11.5 Update Room

### Endpoint

```http
PATCH /api/v1/rooms/{room_id}
```

### Authorization

* owner only

### Request

```json
{
  "description": "Updated description",
  "visibility": "private"
}
```

### Rules

* owner MAY update description
* owner MAY change visibility
* room name MUST remain globally unique if name changes are ever allowed
* for simplicity and strictness, this contract allows room name updates only if uniqueness is preserved

### Full Supported Payload

```json
{
  "name": "engineering",
  "description": "Updated description",
  "visibility": "private"
}
```

### Response

```json
{
  "data": {
    "room": {
      "id": "room_01",
      "name": "engineering",
      "description": "Updated description",
      "visibility": "private"
    }
  }
}
```

---

## 11.6 Delete Room

### Endpoint

```http
DELETE /api/v1/rooms/{room_id}
```

### Authorization

* owner only

### Behavior

* MUST permanently delete room
* MUST permanently delete all room messages
* MUST permanently delete all room attachments

### Response

```http
204 No Content
```

---

## 11.7 Join Public Room

### Endpoint

```http
POST /api/v1/rooms/{room_id}/join
```

### Behavior

* MUST only allow joining public rooms
* MUST deny banned users

### Response

```http
204 No Content
```

### Errors

* `403 Forbidden` — banned
* `403 Forbidden` — room is private
* `409 Conflict` — already member

---

## 11.8 Leave Room

### Endpoint

```http
POST /api/v1/rooms/{room_id}/leave
```

### Rules

* owner MUST NOT be allowed to leave own room
* non-owner members MAY leave freely

### Response

```http
204 No Content
```

### Errors

* `403 Forbidden` — owner cannot leave
* `409 Conflict` — not a member

---

## 11.9 List Room Members

### Endpoint

```http
GET /api/v1/rooms/{room_id}/members?limit=100&cursor=opaque
```

### Response

```json
{
  "data": [
    {
      "user": {
        "id": "usr_01",
        "username": "alice",
        "presence": "online"
      },
      "role": "owner"
    },
    {
      "user": {
        "id": "usr_04",
        "username": "dave",
        "presence": "afk"
      },
      "role": "admin"
    },
    {
      "user": {
        "id": "usr_02",
        "username": "bob",
        "presence": "offline"
      },
      "role": "member"
    }
  ],
  "pagination": {
    "next_cursor": null,
    "limit": 100
  }
}
```

---

## 11.10 Invite User to Private Room

### Endpoint

```http
POST /api/v1/rooms/{room_id}/invitations
```

### Authorization

* owner or admin

### Request

```json
{
  "username": "bob"
}
```

### Behavior

* SHOULD be used for private rooms
* MAY also be allowed for public rooms, but implementation MAY reject as unnecessary
* invited user MUST be able to join private room

### Response

```http
201 Created
```

```json
{
  "data": {
    "invitation": {
      "id": "inv_01",
      "room_id": "room_02",
      "user": {
        "id": "usr_02",
        "username": "bob"
      },
      "created_at": "2026-04-18T10:40:00Z"
    }
  }
}
```

---

## 11.11 List Room Invitations

### Endpoint

```http
GET /api/v1/rooms/{room_id}/invitations
```

### Authorization

* owner or admin

### Response

```json
{
  "data": [
    {
      "id": "inv_01",
      "user": {
        "id": "usr_02",
        "username": "bob"
      },
      "created_at": "2026-04-18T10:40:00Z"
    }
  ]
}
```

---

## 11.12 Accept Room Invitation

### Endpoint

```http
POST /api/v1/room-invitations/{invitation_id}/accept
```

### Response

```http
204 No Content
```

---

## 11.13 Reject Room Invitation

### Endpoint

```http
POST /api/v1/room-invitations/{invitation_id}/reject
```

### Response

```http
204 No Content
```

---

## 12. Room Roles and Moderation API

## 12.1 Promote Member to Admin

### Endpoint

```http
POST /api/v1/rooms/{room_id}/admins
```

### Authorization

* owner only

### Request

```json
{
  "user_id": "usr_02"
}
```

### Response

```http
204 No Content
```

---

## 12.2 Demote Admin

### Endpoint

```http
DELETE /api/v1/rooms/{room_id}/admins/{user_id}
```

### Authorization

* owner MAY demote any non-owner admin
* admin MAY demote other admins except owner only if product chooses to permit that behavior
* to match original requirements:

  * admins MAY remove admin status from other admins except owner
  * owner MAY remove any admin

### Response

```http
204 No Content
```

### Errors

* `403 Forbidden` — cannot remove owner admin status

---

## 12.3 Remove Member from Room

### Endpoint

```http
POST /api/v1/rooms/{room_id}/remove-member
```

### Authorization

* admin or owner

### Request

```json
{
  "user_id": "usr_02"
}
```

### Behavior

This action MUST be treated as a ban.

Effects:

* user is removed from room
* user is added to room ban list
* user loses access to room messages/files/images

### Response

```http
204 No Content
```

---

## 12.4 Ban Member from Room

### Endpoint

```http
POST /api/v1/rooms/{room_id}/bans
```

### Authorization

* admin or owner

### Request

```json
{
  "user_id": "usr_02"
}
```

### Response

```http
201 Created
```

```json
{
  "data": {
    "ban": {
      "user": {
        "id": "usr_02",
        "username": "bob"
      },
      "banned_by": {
        "id": "usr_01",
        "username": "alice"
      },
      "created_at": "2026-04-18T10:45:00Z"
    }
  }
}
```

---

## 12.5 List Room Bans

### Endpoint

```http
GET /api/v1/rooms/{room_id}/bans
```

### Authorization

* admin or owner

### Response

```json
{
  "data": [
    {
      "user": {
        "id": "usr_02",
        "username": "bob"
      },
      "banned_by": {
        "id": "usr_01",
        "username": "alice"
      },
      "created_at": "2026-04-18T10:45:00Z"
    }
  ]
}
```

---

## 12.6 Unban User from Room

### Endpoint

```http
DELETE /api/v1/rooms/{room_id}/bans/{user_id}
```

### Authorization

* admin or owner

### Response

```http
204 No Content
```

---

## 13. Personal Chat API

## 13.1 List Personal Dialogs

### Endpoint

```http
GET /api/v1/dialogs
```

### Response

```json
{
  "data": [
    {
      "id": "dlg_01",
      "other_user": {
        "id": "usr_02",
        "username": "bob",
        "presence": "online"
      },
      "last_message": {
        "id": "msg_99",
        "sender_id": "usr_02",
        "text": "Hello",
        "created_at": "2026-04-18T10:50:00Z"
      },
      "unread_count": 2,
      "is_frozen": false
    }
  ]
}
```

### Rules

* a personal dialog MUST have exactly two participants
* dialog MUST only allow new messaging if:

  * users are friends
  * neither has banned the other

---

## 13.2 Get or Create Personal Dialog

### Endpoint

```http
POST /api/v1/dialogs
```

### Request

```json
{
  "user_id": "usr_02"
}
```

### Behavior

* if dialog exists, return existing dialog
* if allowed and absent, create dialog
* MUST fail if users are not friends
* MUST fail if either side banned the other

### Response

```json
{
  "data": {
    "dialog": {
      "id": "dlg_01",
      "other_user": {
        "id": "usr_02",
        "username": "bob"
      },
      "is_frozen": false,
      "created_at": "2026-04-18T10:52:00Z"
    }
  }
}
```

### Errors

* `403 Forbidden`

---

## 14. Messages API

## 14.1 Shared Message Object

All room and personal dialog message payloads MUST conform to this shape:

```json
{
  "id": "msg_01",
  "chat_type": "room",
  "chat_id": "room_01",
  "sender": {
    "id": "usr_01",
    "username": "alice"
  },
  "text": "Hello world",
  "reply_to": {
    "id": "msg_00",
    "sender": {
      "id": "usr_02",
      "username": "bob"
    },
    "text": "Previous message"
  },
  "attachments": [
    {
      "id": "att_01",
      "filename": "spec-v3.pdf",
      "content_type": "application/pdf",
      "size_bytes": 120393,
      "comment": "latest requirements",
      "download_url": "/api/v1/attachments/att_01/download"
    }
  ],
  "is_edited": false,
  "created_at": "2026-04-18T10:55:00Z",
  "updated_at": "2026-04-18T10:55:00Z"
}
```

### Rules

* `chat_type` MUST be `room` or `dialog`
* `chat_id` MUST reference room or dialog id
* `reply_to` MAY be null
* `attachments` MAY be empty

---

## 14.2 List Room Messages

### Endpoint

```http
GET /api/v1/rooms/{room_id}/messages?limit=50&cursor=opaque
```

### Ordering

* response MUST be chronological within page
* cursor pagination MUST support infinite scroll for older history

### Response

```json
{
  "data": [
    {
      "id": "msg_01",
      "chat_type": "room",
      "chat_id": "room_01",
      "sender": {
        "id": "usr_01",
        "username": "alice"
      },
      "text": "Hello team",
      "reply_to": null,
      "attachments": [],
      "is_edited": false,
      "created_at": "2026-04-18T10:55:00Z",
      "updated_at": "2026-04-18T10:55:00Z"
    }
  ],
  "pagination": {
    "next_cursor": "opaque_next",
    "limit": 50
  }
}
```

---

## 14.3 Send Room Message

### Endpoint

```http
POST /api/v1/rooms/{room_id}/messages
```

### Request

```json
{
  "text": "Hello team",
  "reply_to_message_id": "msg_00",
  "attachment_ids": ["att_01", "att_02"]
}
```

### Rules

* sender MUST be current room member
* banned or removed users MUST NOT send
* `text` MAY be empty only if at least one attachment is present
* `text` MUST NOT exceed 3 KB
* attachment ids MUST be authorized and pending/owned by current user before binding to message

### Response

```http
201 Created
```

```json
{
  "data": {
    "message": {
      "id": "msg_01",
      "chat_type": "room",
      "chat_id": "room_01",
      "sender": {
        "id": "usr_01",
        "username": "alice"
      },
      "text": "Hello team",
      "reply_to": null,
      "attachments": [],
      "is_edited": false,
      "created_at": "2026-04-18T10:55:00Z",
      "updated_at": "2026-04-18T10:55:00Z"
    }
  }
}
```

---

## 14.4 Edit Room Message

### Endpoint

```http
PATCH /api/v1/rooms/{room_id}/messages/{message_id}
```

### Authorization

* author only

### Request

```json
{
  "text": "Hello updated team"
}
```

### Rules

* only message author MAY edit
* edited message MUST expose `is_edited = true`

### Response

```json
{
  "data": {
    "message": {
      "id": "msg_01",
      "text": "Hello updated team",
      "is_edited": true,
      "created_at": "2026-04-18T10:55:00Z",
      "updated_at": "2026-04-18T10:57:00Z"
    }
  }
}
```

---

## 14.5 Delete Room Message

### Endpoint

```http
DELETE /api/v1/rooms/{room_id}/messages/{message_id}
```

### Authorization

* author OR room admin OR room owner

### Response

```http
204 No Content
```

---

## 14.6 List Dialog Messages

### Endpoint

```http
GET /api/v1/dialogs/{dialog_id}/messages?limit=50&cursor=opaque
```

### Rules

* only dialog participants MAY view
* if dialog is frozen, history MUST remain readable

### Response

Same shape as room messages, but:

```json
"chat_type": "dialog"
```

---

## 14.7 Send Dialog Message

### Endpoint

```http
POST /api/v1/dialogs/{dialog_id}/messages
```

### Request

```json
{
  "text": "Hi Bob",
  "reply_to_message_id": null,
  "attachment_ids": []
}
```

### Rules

* sender MUST be dialog participant
* dialog MUST NOT be frozen
* users MUST still satisfy friendship and no-ban constraints

### Response

```http
201 Created
```

```json
{
  "data": {
    "message": {
      "id": "msg_201",
      "chat_type": "dialog",
      "chat_id": "dlg_01",
      "sender": {
        "id": "usr_01",
        "username": "alice"
      },
      "text": "Hi Bob",
      "reply_to": null,
      "attachments": [],
      "is_edited": false,
      "created_at": "2026-04-18T11:00:00Z",
      "updated_at": "2026-04-18T11:00:00Z"
    }
  }
}
```

---

## 14.8 Edit Dialog Message

### Endpoint

```http
PATCH /api/v1/dialogs/{dialog_id}/messages/{message_id}
```

### Authorization

* author only

### Response

Same contract as room message edit.

---

## 14.9 Delete Dialog Message

### Endpoint

```http
DELETE /api/v1/dialogs/{dialog_id}/messages/{message_id}
```

### Authorization

* author only

### Response

```http
204 No Content
```

---

## 14.10 Mark Chat Read

### Room Endpoint

```http
POST /api/v1/rooms/{room_id}/read
```

### Dialog Endpoint

```http
POST /api/v1/dialogs/{dialog_id}/read
```

### Behavior

* MUST clear unread indicator for current user in that chat

### Response

```http
204 No Content
```

---

## 15. Attachments API

## 15.1 Upload Attachment

### Endpoint

```http
POST /api/v1/attachments
Content-Type: multipart/form-data
```

### Multipart Fields

* `file` — required binary
* `comment` — optional text

### Validation Rules

* arbitrary file max size: 20 MB
* image max size: 3 MB
* original filename MUST be preserved

### Response

```http
201 Created
```

```json
{
  "data": {
    "attachment": {
      "id": "att_01",
      "filename": "photo.png",
      "content_type": "image/png",
      "size_bytes": 204800,
      "comment": "Screenshot",
      "created_at": "2026-04-18T11:05:00Z",
      "uploaded_by": {
        "id": "usr_01",
        "username": "alice"
      },
      "status": "uploaded"
    }
  }
}
```

### Notes

Uploaded attachment remains unbound until referenced by a message.

---

## 15.2 Get Attachment Metadata

### Endpoint

```http
GET /api/v1/attachments/{attachment_id}
```

### Access Rules

* room attachments: current room members only
* dialog attachments: authorized dialog participants only
* removed users MUST lose access

### Response

```json
{
  "data": {
    "attachment": {
      "id": "att_01",
      "filename": "photo.png",
      "content_type": "image/png",
      "size_bytes": 204800,
      "comment": "Screenshot",
      "created_at": "2026-04-18T11:05:00Z"
    }
  }
}
```

---

## 15.3 Download Attachment

### Endpoint

```http
GET /api/v1/attachments/{attachment_id}/download
```

### Behavior

* MUST stream/download file
* MUST enforce authorization at request time
* MUST keep the backend as the authorization boundary; presigned public object URLs MUST NOT be exposed
* MUST stream object-storage-backed files without buffering the full object in backend memory
* SHOULD return `Content-Disposition: inline` for image, audio, and video attachments so browser previews do not force eager download behavior
* SHOULD return `Content-Disposition: attachment` for non-inline attachment types
* SHOULD support single `Range: bytes=...` requests for browser media playback and seeking
* when a valid single range is requested, MUST return `206 Partial Content` with `Accept-Ranges: bytes` and `Content-Range`
* when a requested range is unsatisfiable, SHOULD return `416 Requested Range Not Satisfiable` with `Content-Range: bytes */{full_size}`
* legacy filesystem-backed blobs MAY continue to be streamed through the same endpoint during storage cutover, but authorization and revocation rules remain identical

### Responses

* `200 OK` with file stream
* `206 Partial Content` with ranged file stream when applicable
* `403 Forbidden` or `404 Not Found` if not allowed

---

## 15.4 Delete Unbound Attachment

### Endpoint

```http
DELETE /api/v1/attachments/{attachment_id}
```

### Rules

* MAY be allowed only before attachment is bound to a message
* if already bound to a message, deletion MUST be done through message deletion and retention rules

### Response

```http
204 No Content
```

---

## 16. Notifications Summary API

## 16.1 Get Notification Summary

### Endpoint

```http
GET /api/v1/notifications/summary
```

### Response

```json
{
  "data": {
    "rooms": [
      {
        "room_id": "room_01",
        "unread_count": 3
      }
    ],
    "dialogs": [
      {
        "dialog_id": "dlg_01",
        "unread_count": 2
      }
    ],
    "incoming_friend_requests": 1
  }
}
```

---

## 17. Presence API

REST presence endpoints are optional convenience endpoints. Real-time presence MUST be driven primarily via WebSocket events.

## 17.1 Get Presence for Users

### Endpoint

```http
POST /api/v1/presence/query
```

### Request

```json
{
  "user_ids": ["usr_01", "usr_02", "usr_03"]
}
```

### Response

```json
{
  "data": [
    {
      "user_id": "usr_01",
      "presence": "online",
      "last_changed_at": "2026-04-18T11:10:00Z"
    },
    {
      "user_id": "usr_02",
      "presence": "afk",
      "last_changed_at": "2026-04-18T11:09:00Z"
    },
    {
      "user_id": "usr_03",
      "presence": "offline",
      "last_changed_at": "2026-04-18T10:50:00Z"
    }
  ]
}
```

---

## 18. WebSocket Contract

## 18.1 Endpoint

```text
/ws/v1/chat
```

### Authentication

* MUST use authenticated session cookie
* unauthenticated connections MUST be rejected

### Connection Query Params

This contract does not require query params.

Allowed example:

```text
/ws/v1/chat
```

---

## 18.2 WebSocket Envelope

All client-to-server and server-to-client messages MUST use this envelope:

```json
{
  "type": "event_type",
  "payload": {},
  "request_id": "optional_client_generated_string"
}
```

### Fields

* `type`: required event type
* `payload`: required object
* `request_id`: optional correlation id

---

## 18.3 Client-to-Server Event Types

### 18.3.1 Ping

```json
{
  "type": "ping",
  "payload": {}
}
```

### Server Response

```json
{
  "type": "pong",
  "payload": {}
}
```

---

### 18.3.2 Presence Heartbeat

Used to indicate tab activity.

```json
{
  "type": "presence.heartbeat",
  "payload": {
    "tab_id": "tab_abc123",
    "is_active": true,
    "last_interaction_at": "2026-04-18T11:15:00Z"
  },
  "request_id": "req_01"
}
```

### Rules

* client SHOULD send periodically while connected
* server MUST aggregate across tabs/sessions
* server MUST compute:

  * online if any tab active
  * afk if all tabs inactive for > 1 minute
  * offline when no active connections/tabs remain

### Ack

```json
{
  "type": "ack",
  "payload": {
    "accepted": true
  },
  "request_id": "req_01"
}
```

---

### 18.3.3 Subscribe to Room

```json
{
  "type": "room.subscribe",
  "payload": {
    "room_id": "room_01"
  },
  "request_id": "req_02"
}
```

### Rules

* only members MAY subscribe

---

### 18.3.4 Unsubscribe from Room

```json
{
  "type": "room.unsubscribe",
  "payload": {
    "room_id": "room_01"
  },
  "request_id": "req_03"
}
```

---

### 18.3.5 Subscribe to Dialog

```json
{
  "type": "dialog.subscribe",
  "payload": {
    "dialog_id": "dlg_01"
  },
  "request_id": "req_04"
}
```

---

### 18.3.6 Unsubscribe from Dialog

```json
{
  "type": "dialog.unsubscribe",
  "payload": {
    "dialog_id": "dlg_01"
  },
  "request_id": "req_05"
}
```

---

### 18.3.7 Send Room Message

```json
{
  "type": "room.message.send",
  "payload": {
    "room_id": "room_01",
    "text": "Hello team",
    "reply_to_message_id": null,
    "attachment_ids": ["att_01"]
  },
  "request_id": "req_06"
}
```

### Server Behavior

* MUST validate same rules as REST send room message
* MUST persist message before broadcasting
* MUST broadcast created message event to subscribed authorized users

---

### 18.3.8 Send Dialog Message

```json
{
  "type": "dialog.message.send",
  "payload": {
    "dialog_id": "dlg_01",
    "text": "Hi Bob",
    "reply_to_message_id": null,
    "attachment_ids": []
  },
  "request_id": "req_07"
}
```

---

### 18.3.9 Edit Room Message

```json
{
  "type": "room.message.edit",
  "payload": {
    "room_id": "room_01",
    "message_id": "msg_01",
    "text": "Updated"
  },
  "request_id": "req_08"
}
```

---

### 18.3.10 Delete Room Message

```json
{
  "type": "room.message.delete",
  "payload": {
    "room_id": "room_01",
    "message_id": "msg_01"
  },
  "request_id": "req_09"
}
```

---

### 18.3.11 Edit Dialog Message

```json
{
  "type": "dialog.message.edit",
  "payload": {
    "dialog_id": "dlg_01",
    "message_id": "msg_201",
    "text": "Updated DM"
  },
  "request_id": "req_10"
}
```

---

### 18.3.12 Delete Dialog Message

```json
{
  "type": "dialog.message.delete",
  "payload": {
    "dialog_id": "dlg_01",
    "message_id": "msg_201"
  },
  "request_id": "req_11"
}
```

---

### 18.3.13 Mark Room Read

```json
{
  "type": "room.read",
  "payload": {
    "room_id": "room_01"
  },
  "request_id": "req_12"
}
```

---

### 18.3.14 Mark Dialog Read

```json
{
  "type": "dialog.read",
  "payload": {
    "dialog_id": "dlg_01"
  },
  "request_id": "req_13"
}
```

---

## 18.4 Server-to-Client Event Types

### 18.4.1 Ack

```json
{
  "type": "ack",
  "payload": {
    "accepted": true
  },
  "request_id": "req_06"
}
```

---

### 18.4.2 Error

```json
{
  "type": "error",
  "payload": {
    "code": "forbidden",
    "message": "You are not allowed to send messages to this dialog",
    "details": {}
  },
  "request_id": "req_07"
}
```

---

### 18.4.3 Presence Updated

```json
{
  "type": "presence.updated",
  "payload": {
    "user_id": "usr_02",
    "presence": "afk",
    "last_changed_at": "2026-04-18T11:20:00Z"
  }
}
```

---

### 18.4.4 Room Message Created

```json
{
  "type": "room.message.created",
  "payload": {
    "message": {
      "id": "msg_300",
      "chat_type": "room",
      "chat_id": "room_01",
      "sender": {
        "id": "usr_02",
        "username": "bob"
      },
      "text": "Hello everyone",
      "reply_to": null,
      "attachments": [],
      "is_edited": false,
      "created_at": "2026-04-18T11:21:00Z",
      "updated_at": "2026-04-18T11:21:00Z"
    }
  }
}
```

---

### 18.4.5 Room Message Updated

```json
{
  "type": "room.message.updated",
  "payload": {
    "message": {
      "id": "msg_300",
      "chat_type": "room",
      "chat_id": "room_01",
      "sender": {
        "id": "usr_02",
        "username": "bob"
      },
      "text": "Edited text",
      "reply_to": null,
      "attachments": [],
      "is_edited": true,
      "created_at": "2026-04-18T11:21:00Z",
      "updated_at": "2026-04-18T11:22:00Z"
    }
  }
}
```

---

### 18.4.6 Room Message Deleted

```json
{
  "type": "room.message.deleted",
  "payload": {
    "room_id": "room_01",
    "message_id": "msg_300"
  }
}
```

---

### 18.4.7 Dialog Message Created

```json
{
  "type": "dialog.message.created",
  "payload": {
    "message": {
      "id": "msg_401",
      "chat_type": "dialog",
      "chat_id": "dlg_01",
      "sender": {
        "id": "usr_02",
        "username": "bob"
      },
      "text": "Hi Alice",
      "reply_to": null,
      "attachments": [],
      "is_edited": false,
      "created_at": "2026-04-18T11:25:00Z",
      "updated_at": "2026-04-18T11:25:00Z"
    }
  }
}
```

---

### 18.4.8 Dialog Message Updated

```json
{
  "type": "dialog.message.updated",
  "payload": {
    "message": {
      "id": "msg_401",
      "chat_type": "dialog",
      "chat_id": "dlg_01",
      "sender": {
        "id": "usr_02",
        "username": "bob"
      },
      "text": "Updated DM text",
      "reply_to": null,
      "attachments": [],
      "is_edited": true,
      "created_at": "2026-04-18T11:25:00Z",
      "updated_at": "2026-04-18T11:26:00Z"
    }
  }
}
```

---

### 18.4.9 Dialog Message Deleted

```json
{
  "type": "dialog.message.deleted",
  "payload": {
    "dialog_id": "dlg_01",
    "message_id": "msg_401"
  }
}
```

---

### 18.4.10 Chat Read Updated

Room example:

```json
{
  "type": "room.read.updated",
  "payload": {
    "room_id": "room_01",
    "user_id": "usr_01",
    "unread_count": 0
  }
}
```

Dialog example:

```json
{
  "type": "dialog.read.updated",
  "payload": {
    "dialog_id": "dlg_01",
    "user_id": "usr_01",
    "unread_count": 0
  }
}
```

---

### 18.4.11 Friend Request Created

```json
{
  "type": "friend_request.created",
  "payload": {
    "request": {
      "id": "fr_01",
      "from_user": {
        "id": "usr_02",
        "username": "bob"
      },
      "message": "Let's connect",
      "created_at": "2026-04-18T11:30:00Z"
    }
  }
}
```

---

### 18.4.12 Room Invitation Created

```json
{
  "type": "room.invitation.created",
  "payload": {
    "invitation": {
      "id": "inv_01",
      "room_id": "room_02",
      "room_name": "core-team",
      "created_at": "2026-04-18T11:31:00Z"
    }
  }
}
```

---

### 18.4.13 Friend Request Updated

```json
{
  "type": "friend_request.updated",
  "payload": {
    "request": {
      "id": "fr_01",
      "status": "accepted",
      "other_user": {
        "id": "usr_02",
        "username": "bob"
      },
      "responded_at": "2026-04-18T11:32:00Z"
    }
  }
}
```

### Rules

* MUST be sent to both involved users when a pending friend request is accepted or rejected
* MUST reflect the persisted final status

---

### 18.4.14 Dialog Summary Updated

```json
{
  "type": "dialog.summary.updated",
  "payload": {
    "dialog": {
      "id": "dlg_01",
      "other_user": {
        "id": "usr_02",
        "username": "bob",
        "presence": "online"
      },
      "unread_count": 1,
      "is_frozen": false,
      "last_message": {
        "id": "msg_401",
        "sender_id": "usr_02",
        "text": "Hi Alice",
        "created_at": "2026-04-18T11:25:00Z"
      }
    }
  }
}
```

### Rules

* MUST be sent to both dialog participants when a dialog is first created
* MUST be sent to both dialog participants after dialog message creation so non-subscribed clients can update sidebar state without a full reload
* MUST expose the unread count from the perspective of the receiving user

---

### 18.4.15 Room Membership Updated

User removed or joined:

```json
{
  "type": "room.membership.updated",
  "payload": {
    "room_id": "room_01",
    "user_id": "usr_02",
    "action": "removed"
  }
}
```

Allowed `action` values:

* `joined`
* `left`
* `removed`
* `banned`
* `unbanned`

---

## 19. WebSocket Authorization Errors

If a client attempts a forbidden action, server MUST send:

```json
{
  "type": "error",
  "payload": {
    "code": "forbidden",
    "message": "Not allowed",
    "details": {}
  },
  "request_id": "req_123"
}
```

If validation fails:

```json
{
  "type": "error",
  "payload": {
    "code": "validation_error",
    "message": "Message text exceeds 3 KB",
    "details": {
      "field": "text"
    }
  },
  "request_id": "req_123"
}
```

---

## 20. Presence Computation Rules

Presence MUST be computed with these exact rules:

* `online` if user has at least one connected and active tab
* `afk` if user has one or more open tabs, but all are inactive for more than 1 minute
* `offline` if user has no open tabs / no active application presence

The backend MUST treat presence as a user-level aggregate across tabs and sessions.

Presence updates SHOULD propagate within 2 seconds.

---

## 21. Authorization Matrix

## 21.1 Room Access

| Action                      | Room Member | Room Admin | Room Owner | Non-Member |
| --------------------------- | ----------: | ---------: | ---------: | ---------: |
| View room details (public)  |         Yes |        Yes |        Yes |        Yes |
| View room details (private) |         Yes |        Yes |        Yes |         No |
| Read room messages          |         Yes |        Yes |        Yes |         No |
| Send room message           |         Yes |        Yes |        Yes |         No |
| Edit own room message       |         Yes |        Yes |        Yes |         No |
| Delete own room message     |         Yes |        Yes |        Yes |         No |
| Delete any room message     |          No |        Yes |        Yes |         No |
| Invite to private room      |          No |        Yes |        Yes |         No |
| View bans                   |          No |        Yes |        Yes |         No |
| Ban member                  |          No |        Yes |        Yes |         No |
| Unban member                |          No |        Yes |        Yes |         No |
| Promote to admin            |          No |         No |        Yes |         No |
| Demote admin                |          No |       Yes* |        Yes |         No |
| Delete room                 |          No |         No |        Yes |         No |

`*` Admin cannot demote owner.

## 21.2 Dialog Access

| Action              |        Participant | Non-Participant |
| ------------------- | -----------------: | --------------: |
| Read dialog         |                Yes |              No |
| Send dialog message | Yes, if not frozen |              No |
| Edit own message    |                Yes |              No |
| Delete own message  |                Yes |              No |

## 21.3 Peer Ban Effects

| Action                          | Allowed after peer ban |
| ------------------------------- | ---------------------: |
| Read existing dialog history    |                    Yes |
| Send new personal message       |                     No |
| Create new friend request       |                     No |
| Contact banning user in any way |                     No |

---

## 22. Rate Limiting

The implementation SHOULD apply rate limits to:

* login attempts
* registration attempts
* friend requests
* message sending
* attachment uploads
* room creation
* invitations

If rate limited, server MUST return:

```http
429 Too Many Requests
```

```json
{
  "error": {
    "code": "rate_limited",
    "message": "Too many requests",
    "details": {}
  }
}
```

---

## 23. Audit-Relevant Events

The system SHOULD persist audit metadata for moderation-sensitive actions:

* room created
* room updated
* room deleted
* member removed
* member banned
* member unbanned
* admin promoted
* admin demoted
* peer ban created
* peer ban removed
* session revoked

Audit storage is an implementation detail, but API-visible ban metadata MUST include who performed the room ban.

---

## 24. Data Deletion Rules

### 24.1 Account Deletion

On account deletion:

* owned rooms MUST be deleted
* all room messages in owned rooms MUST be deleted
* all room attachments in owned rooms MUST be deleted
* user membership in all other rooms MUST be removed

### 24.2 Room Deletion

On room deletion:

* room MUST be deleted permanently
* room messages MUST be deleted permanently
* room attachments MUST be deleted permanently

### 24.3 Access Loss

If a user loses access to a room:

* user MUST lose access to room messages in UI and API
* user MUST lose access to room attachments
* files MAY remain stored if room still exists

---

## 25. Minimal Frontend Consumption Expectations

A frontend consuming this API MUST assume:

* room and dialog lists come from REST
* initial history loads from REST
* live updates come from WebSocket
* read state can be updated via REST and/or WebSocket
* presence is eventually synchronized by WebSocket events
* optimistic UI is optional, not required by this contract

---

## 26. OpenAPI Mapping Guidance

This contract is intentionally human-readable. A generated OpenAPI spec SHOULD preserve:

* same endpoint paths
* same field names
* same error codes
* same enum values
* same authorization semantics

Enums that SHOULD be represented explicitly:

* `presence`: `online | afk | offline`
* `room.visibility`: `public | private`
* `current_user_role`: `owner | admin | member | none`
* `chat_type`: `room | dialog`
* membership update action: `joined | left | removed | banned | unbanned`

---

## 27. Non-Goals

This contract does not define:

* internal database schema
* internal event bus implementation
* storage engine details
* deployment topology
* exact password reset token format
* exact session expiration duration
* attachment virus scanning
* end-to-end encryption
* XMPP/Jabber integration contract

Those may be defined separately.

---

## 28. Compliance Requirements

An implementation is compliant only if:

* all required endpoints exist
* all authorization rules are enforced
* room/private dialog constraints are enforced
* message persistence rules are enforced
* presence rules match this document
* room member removal behaves as a room ban
* peer bans freeze existing personal dialogs and block new personal messaging
* access to room files/messages is revoked immediately on room access loss
* logout invalidates only the current session unless another session is explicitly revoked
* WebSocket events reflect persisted state, not speculative state

---
