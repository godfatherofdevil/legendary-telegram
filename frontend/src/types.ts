export type PresenceState = "online" | "afk" | "offline";
export type RoomVisibility = "public" | "private";
export type RoomRole = "owner" | "admin" | "member" | "none";
export type ChatKind = "room" | "dialog";

export interface Pagination {
  next_cursor: string | null;
  limit: number;
}

export interface ApiErrorPayload {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}

export interface User {
  id: string;
  username: string;
  email?: string;
  created_at?: string;
  presence?: PresenceState;
}

export interface SessionRecord {
  id: string;
  created_at: string;
  is_current: boolean;
  ip_address?: string | null;
  user_agent?: string | null;
  last_seen_at?: string;
  expires_at?: string;
}

export interface RoomListItem {
  id: string;
  name: string;
  description: string | null;
  visibility: RoomVisibility;
  member_count: number;
  owner?: {
    id: string;
    username: string;
  };
  unread_count?: number;
}

export interface RoomDetail {
  id: string;
  name: string;
  description: string | null;
  visibility: RoomVisibility;
  owner: {
    id: string;
    username: string;
  };
  admins: Array<{
    id: string;
    username: string;
  }>;
  member_count: number;
  created_at: string;
  current_user_role: RoomRole;
  is_member: boolean;
}

export interface RoomMember {
  user: User;
  role: Exclude<RoomRole, "none">;
}

export interface RoomInvitation {
  id: string;
  room_id: string;
  room_name?: string;
  user?: User;
  created_at: string;
}

export interface RoomBan {
  user: User;
  banned_by: User;
  created_at: string;
}

export interface DialogSummary {
  id: string;
  other_user: User;
  unread_count: number;
  is_frozen: boolean;
  last_message: {
    id: string;
    sender_id: string;
    text: string;
    created_at: string;
  } | null;
}

export interface AttachmentSummary {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  comment: string | null;
  download_url: string;
}

export interface ReplySummary {
  id: string;
  sender: User;
  text: string;
}

export interface Message {
  id: string;
  chat_type: ChatKind;
  chat_id: string;
  sender: User;
  text: string;
  reply_to: ReplySummary | null;
  attachments: AttachmentSummary[];
  is_edited: boolean;
  created_at: string;
  updated_at: string;
}

export interface FriendItem {
  user: User;
  friend_since: string;
}

export interface IncomingFriendRequest {
  id: string;
  from_user: User;
  message: string | null;
  created_at: string;
}

export interface OutgoingFriendRequest {
  id: string;
  to_user: User;
  message: string | null;
  created_at: string;
}

export interface PeerBan {
  user: User;
  created_at: string;
}

export interface NotificationSummary {
  rooms: Array<{
    room_id: string;
    unread_count: number;
  }>;
  dialogs: Array<{
    dialog_id: string;
    unread_count: number;
  }>;
  incoming_friend_requests: number;
}

export interface PresenceSnapshot {
  user_id: string;
  presence: PresenceState;
  last_changed_at: string;
}

export interface UploadedAttachment {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  comment: string | null;
  created_at: string;
}

export interface ActiveChat {
  kind: ChatKind;
  id: string;
}
