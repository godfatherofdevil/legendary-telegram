import type {
  ActiveChat,
  ApiErrorPayload,
  DialogSummary,
  FriendItem,
  IncomingFriendRequest,
  Message,
  NotificationSummary,
  OutgoingFriendRequest,
  Pagination,
  PeerBan,
  RoomBan,
  RoomDetail,
  RoomInvitation,
  RoomListItem,
  RoomMember,
  SessionRecord,
  UploadedAttachment,
  User,
} from "../types";

declare const __API_BASE_URL__: string;

export class ApiError extends Error {
  code: string;
  details: Record<string, unknown>;
  status: number;

  constructor(message: string, options: { code: string; status: number; details?: Record<string, unknown> }) {
    super(message);
    this.name = "ApiError";
    this.code = options.code;
    this.status = options.status;
    this.details = options.details ?? {};
  }
}

function getCookie(name: string): string | null {
  const match = document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

function joinUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const origin = typeof window === "undefined" ? "http://localhost" : window.location.origin;
  const base = new URL(
    __API_BASE_URL__.startsWith("http://") || __API_BASE_URL__.startsWith("https://")
      ? __API_BASE_URL__
      : `${origin}${__API_BASE_URL__.startsWith("/") ? "" : "/"}${__API_BASE_URL__}`,
  );
  const normalizedBase = base.href.endsWith("/") ? base.href : `${base.href}/`;
  if (path.startsWith("/api/")) {
    return new URL(path, origin).toString();
  }
  if (path.startsWith("/")) {
    return new URL(path.slice(1), normalizedBase).toString();
  }
  return new URL(path, normalizedBase).toString();
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  options: { skipJson?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  const body = init.body;

  if (!(body instanceof FormData) && !headers.has("Content-Type") && method !== "GET") {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
    const csrfToken = getCookie("csrftoken");
    if (csrfToken) {
      headers.set("X-CSRFToken", csrfToken);
    }
  }

  const response = await fetch(joinUrl(path), {
    ...init,
    credentials: "include",
    headers,
  });

  if (!response.ok) {
    let payload: ApiErrorPayload | undefined;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = undefined;
    }
    throw new ApiError(payload?.error.message ?? "Request failed.", {
      code: payload?.error.code ?? "error",
      status: response.status,
      details: payload?.error.details ?? {},
    });
  }

  if (response.status === 204 || options.skipJson) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function toPublicUrl(path: string): string {
  return joinUrl(path);
}

export async function fetchSessionStatus(): Promise<boolean> {
  const response = await request<{ data: { authenticated: boolean } }>("/auth/session-status");
  return response.data.authenticated;
}

export async function fetchCurrentUser(): Promise<User | null> {
  try {
    const response = await request<{ data: { user: User } }>("/auth/me");
    return response.data.user;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null;
    }
    throw error;
  }
}

export async function login(payload: {
  email: string;
  password: string;
  remember_me: boolean;
}): Promise<User> {
  const response = await request<{ data: { user: User } }>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return response.data.user;
}

export async function register(payload: {
  email: string;
  username: string;
  password: string;
}): Promise<void> {
  await request("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function requestPasswordReset(email: string): Promise<void> {
  await request("/auth/request-password-reset", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function logout(): Promise<void> {
  await request("/auth/logout", { method: "POST" }, { skipJson: true });
}

export async function fetchJoinedRooms(): Promise<RoomListItem[]> {
  const response = await request<{ data: RoomListItem[] }>("/rooms/joined");
  return response.data;
}

export async function fetchPublicRooms(search: string): Promise<RoomListItem[]> {
  const query = search.trim() ? `?search=${encodeURIComponent(search.trim())}` : "";
  const response = await request<{ data: RoomListItem[] }>(`/rooms/public${query}`);
  return response.data;
}

export async function createRoom(payload: {
  name: string;
  description: string;
  visibility: "public" | "private";
}): Promise<RoomDetail> {
  const response = await request<{ data: { room: RoomDetail } }>("/rooms", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return response.data.room;
}

export async function updateRoom(
  roomId: string,
  payload: Partial<{ name: string; description: string; visibility: "public" | "private" }>,
): Promise<RoomDetail> {
  const response = await request<{ data: { room: RoomDetail } }>(`/rooms/${roomId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return response.data.room;
}

export async function deleteRoom(roomId: string): Promise<void> {
  await request(`/rooms/${roomId}`, { method: "DELETE" }, { skipJson: true });
}

export async function joinRoom(roomId: string): Promise<void> {
  await request(`/rooms/${roomId}/join`, { method: "POST" }, { skipJson: true });
}

export async function leaveRoom(roomId: string): Promise<void> {
  await request(`/rooms/${roomId}/leave`, { method: "POST" }, { skipJson: true });
}

export async function fetchRoomDetail(roomId: string): Promise<RoomDetail> {
  const response = await request<{ data: { room: RoomDetail } }>(`/rooms/${roomId}`);
  return response.data.room;
}

export async function fetchRoomMembers(roomId: string): Promise<RoomMember[]> {
  const response = await request<{ data: RoomMember[]; pagination: Pagination }>(`/rooms/${roomId}/members`);
  return response.data;
}

export async function fetchRoomInvitations(roomId: string): Promise<RoomInvitation[]> {
  const response = await request<{ data: RoomInvitation[] }>(`/rooms/${roomId}/invitations`);
  return response.data;
}

export async function inviteUserToRoom(roomId: string, username: string): Promise<void> {
  await request(`/rooms/${roomId}/invitations`, {
    method: "POST",
    body: JSON.stringify({ username }),
  });
}

export async function acceptRoomInvitation(invitationId: string): Promise<void> {
  await request(`/room-invitations/${invitationId}/accept`, { method: "POST" }, { skipJson: true });
}

export async function rejectRoomInvitation(invitationId: string): Promise<void> {
  await request(`/room-invitations/${invitationId}/reject`, { method: "POST" }, { skipJson: true });
}

export async function promoteRoomAdmin(roomId: string, userId: string): Promise<void> {
  await request(`/rooms/${roomId}/admins`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  }, { skipJson: true });
}

export async function demoteRoomAdmin(roomId: string, userId: string): Promise<void> {
  await request(`/rooms/${roomId}/admins/${userId}`, { method: "DELETE" }, { skipJson: true });
}

export async function fetchRoomBans(roomId: string): Promise<RoomBan[]> {
  const response = await request<{ data: RoomBan[] }>(`/rooms/${roomId}/bans`);
  return response.data;
}

export async function banRoomUser(roomId: string, userId: string): Promise<void> {
  await request(`/rooms/${roomId}/bans`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export async function unbanRoomUser(roomId: string, userId: string): Promise<void> {
  await request(`/rooms/${roomId}/bans/${userId}`, { method: "DELETE" }, { skipJson: true });
}

export async function removeRoomMember(roomId: string, userId: string): Promise<void> {
  await request(`/rooms/${roomId}/remove-member`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  }, { skipJson: true });
}

export async function fetchDialogs(): Promise<DialogSummary[]> {
  const response = await request<{ data: DialogSummary[] }>("/dialogs");
  return response.data;
}

export async function ensureDialog(userId: string): Promise<{ id: string }> {
  const response = await request<{ data: { dialog: { id: string } } }>("/dialogs", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
  return response.data.dialog;
}

export async function fetchMessages(
  activeChat: ActiveChat,
  cursor?: string | null,
): Promise<{ messages: Message[]; pagination: Pagination }> {
  const params = new URLSearchParams();
  params.set("limit", "50");
  if (cursor) {
    params.set("cursor", cursor);
  }
  const path =
    activeChat.kind === "room"
      ? `/rooms/${activeChat.id}/messages?${params.toString()}`
      : `/dialogs/${activeChat.id}/messages?${params.toString()}`;
  const response = await request<{ data: Message[]; pagination: Pagination }>(path);
  return { messages: response.data, pagination: response.pagination };
}

export async function sendMessage(
  activeChat: ActiveChat,
  payload: { text: string; reply_to_message_id?: string | null; attachment_ids?: string[] },
): Promise<Message> {
  const path =
    activeChat.kind === "room" ? `/rooms/${activeChat.id}/messages` : `/dialogs/${activeChat.id}/messages`;
  const response = await request<{ data: { message: Message } }>(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return response.data.message;
}

export async function editMessage(activeChat: ActiveChat, messageId: string, text: string): Promise<Message> {
  const path =
    activeChat.kind === "room"
      ? `/rooms/${activeChat.id}/messages/${messageId}`
      : `/dialogs/${activeChat.id}/messages/${messageId}`;
  const response = await request<{ data: { message: Message } }>(path, {
    method: "PATCH",
    body: JSON.stringify({ text }),
  });
  return response.data.message;
}

export async function deleteMessage(activeChat: ActiveChat, messageId: string): Promise<void> {
  const path =
    activeChat.kind === "room"
      ? `/rooms/${activeChat.id}/messages/${messageId}`
      : `/dialogs/${activeChat.id}/messages/${messageId}`;
  await request(path, { method: "DELETE" }, { skipJson: true });
}

export async function markChatRead(activeChat: ActiveChat): Promise<void> {
  const path = activeChat.kind === "room" ? `/rooms/${activeChat.id}/read` : `/dialogs/${activeChat.id}/read`;
  await request(path, { method: "POST" }, { skipJson: true });
}

export async function uploadAttachment(file: File, comment: string): Promise<UploadedAttachment> {
  const formData = new FormData();
  formData.append("file", file);
  if (comment.trim()) {
    formData.append("comment", comment.trim());
  }
  const response = await request<{ data: { attachment: UploadedAttachment } }>("/attachments", {
    method: "POST",
    body: formData,
  });
  return response.data.attachment;
}

export async function deleteAttachment(attachmentId: string): Promise<void> {
  await request(`/attachments/${attachmentId}`, { method: "DELETE" }, { skipJson: true });
}

export async function fetchFriends(): Promise<FriendItem[]> {
  const response = await request<{ data: FriendItem[] }>("/friends");
  return response.data;
}

export async function removeFriend(userId: string): Promise<void> {
  await request(`/friends/${userId}`, { method: "DELETE" }, { skipJson: true });
}

export async function fetchIncomingRequests(): Promise<IncomingFriendRequest[]> {
  const response = await request<{ data: IncomingFriendRequest[] }>("/friend-requests/incoming");
  return response.data;
}

export async function fetchOutgoingRequests(): Promise<OutgoingFriendRequest[]> {
  const response = await request<{ data: OutgoingFriendRequest[] }>("/friend-requests/outgoing");
  return response.data;
}

export async function sendFriendRequest(username: string, message: string): Promise<void> {
  await request("/friend-requests", {
    method: "POST",
    body: JSON.stringify({ username, message: message.trim() || null }),
  });
}

export async function acceptFriendRequest(requestId: string): Promise<void> {
  await request(`/friend-requests/${requestId}/accept`, { method: "POST" }, { skipJson: true });
}

export async function rejectFriendRequest(requestId: string): Promise<void> {
  await request(`/friend-requests/${requestId}/reject`, { method: "POST" }, { skipJson: true });
}

export async function fetchPeerBans(): Promise<PeerBan[]> {
  const response = await request<{ data: PeerBan[] }>("/user-bans");
  return response.data;
}

export async function createPeerBan(userId: string): Promise<void> {
  await request("/user-bans", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export async function removePeerBan(userId: string): Promise<void> {
  await request(`/user-bans/${userId}`, { method: "DELETE" }, { skipJson: true });
}

export async function fetchNotificationSummary(): Promise<NotificationSummary> {
  const response = await request<{ data: NotificationSummary }>("/notifications/summary");
  return response.data;
}

export async function fetchSessions(): Promise<SessionRecord[]> {
  const response = await request<{ data: SessionRecord[] }>("/sessions");
  return response.data;
}

export async function revokeSession(sessionId: string): Promise<void> {
  await request(`/sessions/${sessionId}`, { method: "DELETE" }, { skipJson: true });
}
