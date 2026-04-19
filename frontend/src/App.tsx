import type { ChangeEvent, FormEvent, ReactNode } from "react";
import { startTransition, useDeferredValue, useEffect, useRef, useState } from "react";
import {
  acceptFriendRequest,
  acceptRoomInvitation,
  ApiError,
  banRoomUser,
  createPeerBan,
  createRoom,
  deleteAttachment,
  deleteMessage,
  deleteRoom,
  demoteRoomAdmin,
  editMessage,
  ensureDialog,
  fetchCurrentUser,
  fetchDialogs,
  fetchFriends,
  fetchIncomingRequests,
  fetchJoinedRooms,
  fetchMessages,
  fetchNotificationSummary,
  fetchOutgoingRequests,
  fetchPeerBans,
  fetchPublicRooms,
  fetchRoomBans,
  fetchRoomDetail,
  fetchRoomInvitations,
  fetchRoomMembers,
  fetchSessionStatus,
  fetchSessions,
  inviteUserToRoom,
  joinRoom,
  leaveRoom,
  login,
  logout,
  markChatRead,
  promoteRoomAdmin,
  register,
  rejectFriendRequest,
  rejectRoomInvitation,
  removeFriend,
  removePeerBan,
  removeRoomMember,
  requestPasswordReset,
  revokeSession,
  sendFriendRequest,
  sendMessage,
  toPublicUrl,
  unbanRoomUser,
  updateRoom,
  uploadAttachment,
} from "./lib/api";
import type {
  ActiveChat,
  DialogSummary,
  FriendItem,
  IncomingFriendRequest,
  Message,
  NotificationSummary,
  OutgoingFriendRequest,
  PeerBan,
  RoomBan,
  RoomDetail,
  RoomInvitation,
  RoomListItem,
  RoomMember,
  SessionRecord,
  UploadedAttachment,
  User,
} from "./types";

declare const __WS_BASE_URL__: string;

type AuthMode = "login" | "register" | "reset";
type ShellStatus = "booting" | "guest" | "ready";
type ConnectionState = "connecting" | "open" | "closed";
type SidebarTab = "rooms" | "people";
type ToastTone = "info" | "error";

interface ToastState {
  tone: ToastTone;
  message: string;
}

interface QueuedAttachment {
  id: string;
  filename: string;
  size_bytes: number;
  content_type: string;
  comment: string | null;
}

const EMPTY_SUMMARY: NotificationSummary = {
  rooms: [],
  dialogs: [],
  incoming_friend_requests: 0,
};

const HEARTBEAT_MS = 30_000;

function getWebSocketUrl(): string {
  if (__WS_BASE_URL__.startsWith("ws://") || __WS_BASE_URL__.startsWith("wss://")) {
    return __WS_BASE_URL__;
  }
  if (__WS_BASE_URL__.startsWith("http://")) {
    return __WS_BASE_URL__.replace("http://", "ws://");
  }
  if (__WS_BASE_URL__.startsWith("https://")) {
    return __WS_BASE_URL__.replace("https://", "wss://");
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  if (__WS_BASE_URL__.startsWith("/")) {
    return `${protocol}//${window.location.host}${__WS_BASE_URL__}`;
  }
  return `${protocol}//${window.location.host}/${__WS_BASE_URL__}`;
}

function chooseInitialChat(joinedRooms: RoomListItem[], dialogs: DialogSummary[]): ActiveChat | null {
  const unreadRoom = joinedRooms.find((room) => (room.unread_count ?? 0) > 0);
  if (unreadRoom) {
    return { kind: "room", id: unreadRoom.id };
  }
  const unreadDialog = dialogs.find((dialog) => dialog.unread_count > 0);
  if (unreadDialog) {
    return { kind: "dialog", id: unreadDialog.id };
  }
  if (joinedRooms[0]) {
    return { kind: "room", id: joinedRooms[0].id };
  }
  if (dialogs[0]) {
    return { kind: "dialog", id: dialogs[0].id };
  }
  return null;
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatRelative(value: string): string {
  const date = new Date(value);
  const delta = Math.round((Date.now() - date.getTime()) / 60_000);
  if (delta < 1) {
    return "now";
  }
  if (delta < 60) {
    return `${delta}m`;
  }
  if (delta < 1_440) {
    return `${Math.round(delta / 60)}h`;
  }
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

function compactCount(value: number): string {
  if (value <= 99) {
    return String(value);
  }
  return "99+";
}

function isImageAttachment(contentType: string): boolean {
  return contentType.toLowerCase().startsWith("image/");
}

function isVideoAttachment(contentType: string): boolean {
  return contentType.toLowerCase().startsWith("video/");
}

function upsertMessage(list: Message[], message: Message): Message[] {
  const existingIndex = list.findIndex((item) => item.id === message.id);
  if (existingIndex >= 0) {
    const next = list.slice();
    next[existingIndex] = message;
    return next.sort((left, right) => left.created_at.localeCompare(right.created_at));
  }
  return [...list, message].sort((left, right) => left.created_at.localeCompare(right.created_at));
}

function upsertDialog(list: DialogSummary[], dialog: DialogSummary): DialogSummary[] {
  return [dialog, ...list.filter((item) => item.id !== dialog.id)];
}

function removeMessage(list: Message[], messageId: string): Message[] {
  return list.filter((item) => item.id !== messageId);
}

function patchPresenceInUser(user: User, targetUserId: string, presence: User["presence"]): User {
  if (user.id !== targetUserId) {
    return user;
  }
  return { ...user, presence };
}

function updateUnreadCountsFromSummary(
  joinedRooms: RoomListItem[],
  dialogs: DialogSummary[],
  summary: NotificationSummary,
): { joinedRooms: RoomListItem[]; dialogs: DialogSummary[] } {
  const roomCounts = new Map(summary.rooms.map((room) => [room.room_id, room.unread_count]));
  const dialogCounts = new Map(summary.dialogs.map((dialog) => [dialog.dialog_id, dialog.unread_count]));
  return {
    joinedRooms: joinedRooms.map((room) => ({
      ...room,
      unread_count: roomCounts.get(room.id) ?? 0,
    })),
    dialogs: dialogs.map((dialog) => ({
      ...dialog,
      unread_count: dialogCounts.get(dialog.id) ?? 0,
    })),
  };
}

function isChatEqual(left: ActiveChat | null, right: ActiveChat | null): boolean {
  if (!left || !right) {
    return left === right;
  }
  return left.kind === right.kind && left.id === right.id;
}

type IconName =
  | "leave"
  | "reply"
  | "edit"
  | "delete"
  | "save"
  | "cancel"
  | "clear"
  | "attach"
  | "send"
  | "promote"
  | "demote"
  | "remove"
  | "ban"
  | "unban"
  | "invite"
  | "friend-remove"
  | "peer-ban"
  | "peer-unban";

function Icon(props: { name: IconName }) {
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 1.8,
  };

  switch (props.name) {
    case "leave":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path {...common} d="M10 17l-5-5 5-5" />
          <path {...common} d="M5 12h10" />
          <path {...common} d="M14 5h3a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-3" />
        </svg>
      );
    case "reply":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path {...common} d="M10 9l-5 4 5 4" />
          <path {...common} d="M5 13h8a6 6 0 0 1 6 6" />
          <path {...common} d="M13 7a6 6 0 0 1 6 6" />
        </svg>
      );
    case "edit":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path {...common} d="M4 20h4l10-10-4-4L4 16v4z" />
          <path {...common} d="M12 6l4 4" />
        </svg>
      );
    case "delete":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path {...common} d="M4 7h16" />
          <path {...common} d="M9 7V4h6v3" />
          <path {...common} d="M7 7l1 13h8l1-13" />
          <path {...common} d="M10 11v5M14 11v5" />
        </svg>
      );
    case "save":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path {...common} d="M5 4h11l3 3v13H5z" />
          <path {...common} d="M8 4v6h8V4" />
          <path {...common} d="M9 18h6" />
        </svg>
      );
    case "cancel":
    case "clear":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path {...common} d="M6 6l12 12M18 6L6 18" />
        </svg>
      );
    case "attach":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path {...common} d="M8 12.5l6.4-6.4a3.5 3.5 0 1 1 5 5L10 20.5a5 5 0 0 1-7-7L12 4.5" />
        </svg>
      );
    case "send":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path {...common} d="M4 20l16-8L4 4l3 8-3 8z" />
          <path {...common} d="M7 12h13" />
        </svg>
      );
    case "promote":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path {...common} d="M12 18V7" />
          <path {...common} d="M8.5 10.5L12 7l3.5 3.5" />
          <path {...common} d="M5 20h14" />
        </svg>
      );
    case "demote":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path {...common} d="M12 6v11" />
          <path {...common} d="M8.5 13.5L12 17l3.5-3.5" />
          <path {...common} d="M5 20h14" />
        </svg>
      );
    case "remove":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <circle {...common} cx="9" cy="8" r="3" />
          <path {...common} d="M4 19a5 5 0 0 1 10 0" />
          <path {...common} d="M16 11h5" />
        </svg>
      );
    case "ban":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <circle {...common} cx="12" cy="12" r="8" />
          <path {...common} d="M8.5 8.5l7 7" />
        </svg>
      );
    case "unban":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <circle {...common} cx="12" cy="12" r="8" />
          <path {...common} d="M8.5 12h7" />
        </svg>
      );
    case "invite":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <circle {...common} cx="9" cy="8" r="3" />
          <path {...common} d="M4 19a5 5 0 0 1 10 0" />
          <path {...common} d="M18 8v6M15 11h6" />
        </svg>
      );
    case "friend-remove":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <circle {...common} cx="9" cy="8" r="3" />
          <path {...common} d="M4 19a5 5 0 0 1 10 0" />
          <path {...common} d="M16 8l4 4M20 8l-4 4" />
        </svg>
      );
    case "peer-ban":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <circle {...common} cx="9" cy="8" r="3" />
          <path {...common} d="M4 19a5 5 0 0 1 10 0" />
          <circle {...common} cx="18" cy="10" r="3" />
          <path {...common} d="M16 8l4 4" />
        </svg>
      );
    case "peer-unban":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <circle {...common} cx="9" cy="8" r="3" />
          <path {...common} d="M4 19a5 5 0 0 1 10 0" />
          <path {...common} d="M15 10h6" />
        </svg>
      );
  }
}

function IconButton(props: {
  icon: IconName;
  label: string;
  onClick?: () => void;
  type?: "button" | "submit";
  disabled?: boolean;
  variant?: "default" | "positive" | "danger";
}) {
  const variantClass =
    props.variant === "positive" ? "positive" : props.variant === "danger" ? "danger" : "";

  return (
    <button
      aria-label={props.label}
      className={`icon-button ${variantClass}`.trim()}
      disabled={props.disabled}
      onClick={props.onClick}
      title={props.label}
      type={props.type ?? "button"}
    >
      <Icon name={props.icon} />
      <span className="sr-only">{props.label}</span>
    </button>
  );
}

export default function App() {
  const [shellStatus, setShellStatus] = useState<ShellStatus>("booting");
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [profile, setProfile] = useState<User | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [busy, setBusy] = useState(false);

  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [registerEmail, setRegisterEmail] = useState("");
  const [registerUsername, setRegisterUsername] = useState("");
  const [registerPassword, setRegisterPassword] = useState("");
  const [resetEmail, setResetEmail] = useState("");

  const [joinedRooms, setJoinedRooms] = useState<RoomListItem[]>([]);
  const [publicRooms, setPublicRooms] = useState<RoomListItem[]>([]);
  const [dialogs, setDialogs] = useState<DialogSummary[]>([]);
  const [friends, setFriends] = useState<FriendItem[]>([]);
  const [incomingRequests, setIncomingRequests] = useState<IncomingFriendRequest[]>([]);
  const [outgoingRequests, setOutgoingRequests] = useState<OutgoingFriendRequest[]>([]);
  const [peerBans, setPeerBans] = useState<PeerBan[]>([]);
  const [notificationSummary, setNotificationSummary] = useState<NotificationSummary>(EMPTY_SUMMARY);
  const [pendingInvitations, setPendingInvitations] = useState<RoomInvitation[]>([]);

  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("rooms");
  const [publicSearch, setPublicSearch] = useState("");
  const deferredPublicSearch = useDeferredValue(publicSearch);
  const [activeChat, setActiveChat] = useState<ActiveChat | null>(null);

  const [activeRoom, setActiveRoom] = useState<RoomDetail | null>(null);
  const [activeRoomMembers, setActiveRoomMembers] = useState<RoomMember[]>([]);
  const [activeRoomBans, setActiveRoomBans] = useState<RoomBan[]>([]);
  const [activeRoomInvitations, setActiveRoomInvitations] = useState<RoomInvitation[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [messageCursor, setMessageCursor] = useState<string | null>(null);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [composerText, setComposerText] = useState("");
  const [replyTarget, setReplyTarget] = useState<Message | null>(null);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");
  const [queuedAttachments, setQueuedAttachments] = useState<QueuedAttachment[]>([]);
  const [attachmentComment, setAttachmentComment] = useState("");

  const [showCreateRoomModal, setShowCreateRoomModal] = useState(false);
  const [newRoomName, setNewRoomName] = useState("");
  const [newRoomDescription, setNewRoomDescription] = useState("");
  const [newRoomVisibility, setNewRoomVisibility] = useState<RoomDetail["visibility"]>("public");

  const [showPeopleModal, setShowPeopleModal] = useState(false);
  const [friendRequestUsername, setFriendRequestUsername] = useState("");
  const [friendRequestMessage, setFriendRequestMessage] = useState("");

  const [showSessionsModal, setShowSessionsModal] = useState(false);
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);

  const [inviteUsername, setInviteUsername] = useState("");
  const [roomEditName, setRoomEditName] = useState("");
  const [roomEditDescription, setRoomEditDescription] = useState("");
  const [roomEditVisibility, setRoomEditVisibility] = useState<RoomDetail["visibility"]>("public");
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");

  const wsRef = useRef<WebSocket | null>(null);
  const activeChatRef = useRef<ActiveChat | null>(null);
  const profileRef = useRef<User | null>(null);
  const tabIdRef = useRef(`tab-${crypto.randomUUID()}`);
  const subscribedChatRef = useRef<ActiveChat | null>(null);
  const messageViewportRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef(true);
  const restoreScrollRef = useRef<number | null>(null);

  useEffect(() => {
    activeChatRef.current = activeChat;
  }, [activeChat]);

  useEffect(() => {
    profileRef.current = profile;
  }, [profile]);

  useEffect(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      subscribedChatRef.current = activeChat;
      return;
    }
    const previous = subscribedChatRef.current;
    if (previous && !isChatEqual(previous, activeChat)) {
      unsubscribeFromChat(previous);
    }
    if (activeChat && !isChatEqual(previous, activeChat)) {
      subscribeToChat(activeChat);
    }
    subscribedChatRef.current = activeChat;
  }, [activeChat]);

  useEffect(() => {
    if (!toast) {
      return undefined;
    }
    const timeout = window.setTimeout(() => setToast(null), 4_000);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        const isAuthenticated = await fetchSessionStatus();
        if (cancelled) {
          return;
        }
        if (!isAuthenticated) {
          setShellStatus("guest");
          return;
        }
        const user = await fetchCurrentUser();
        if (cancelled) {
          return;
        }
        if (!user) {
          setShellStatus("guest");
          return;
        }
        setProfile(user);
        await refreshShell(user, true);
      } catch (error) {
        if (!cancelled) {
          setShellStatus("guest");
          pushError(error);
        }
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (shellStatus !== "ready") {
      return undefined;
    }
    let cancelled = false;
    startTransition(() => {
      fetchPublicRooms(deferredPublicSearch)
        .then((rooms) => {
          if (!cancelled) {
            setPublicRooms(rooms);
          }
        })
        .catch((error) => {
          if (!cancelled) {
            pushError(error);
          }
        });
    });
    return () => {
      cancelled = true;
    };
  }, [deferredPublicSearch, shellStatus]);

  useEffect(() => {
    if (shellStatus !== "ready" || !profile) {
      return undefined;
    }
    const socket = new WebSocket(getWebSocketUrl());
    wsRef.current = socket;
    setConnectionState("connecting");

    socket.onopen = () => {
      setConnectionState("open");
      sendPresenceHeartbeat(true);
      if (activeChatRef.current) {
        subscribeToChat(activeChatRef.current);
        subscribedChatRef.current = activeChatRef.current;
      }
    };

    socket.onclose = () => {
      setConnectionState("closed");
      wsRef.current = null;
    };

    socket.onerror = () => {
      setConnectionState("closed");
    };

    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as {
        type: string;
        payload: Record<string, unknown>;
      };
      handleSocketEvent(payload.type, payload.payload);
    };

    const heartbeat = window.setInterval(() => {
      sendPresenceHeartbeat(!document.hidden);
    }, HEARTBEAT_MS);

    const updatePresence = () => sendPresenceHeartbeat(!document.hidden);
    window.addEventListener("focus", updatePresence);
    document.addEventListener("visibilitychange", updatePresence);
    document.addEventListener("keydown", updatePresence);
    document.addEventListener("pointerdown", updatePresence);

    return () => {
      window.clearInterval(heartbeat);
      window.removeEventListener("focus", updatePresence);
      document.removeEventListener("visibilitychange", updatePresence);
      document.removeEventListener("keydown", updatePresence);
      document.removeEventListener("pointerdown", updatePresence);
      socket.close();
    };
  }, [profile, shellStatus]);

  useEffect(() => {
    if (shellStatus !== "ready" || !activeChat) {
      setMessages([]);
      setMessageCursor(null);
      setActiveRoom(null);
      setActiveRoomMembers([]);
      setActiveRoomBans([]);
      setActiveRoomInvitations([]);
      return;
    }

    let cancelled = false;
    const currentChat = activeChat;
    setMessagesLoading(true);
    setReplyTarget(null);
    setEditingMessageId(null);
    setEditingText("");

    async function loadChat() {
      try {
        const [{ messages: nextMessages, pagination }, roomDetail, roomMembers, roomBans, roomInvitations] =
          await Promise.all([
            fetchMessages(currentChat),
            currentChat.kind === "room" ? fetchRoomDetail(currentChat.id) : Promise.resolve(null),
            currentChat.kind === "room" ? fetchRoomMembers(currentChat.id) : Promise.resolve([]),
            currentChat.kind === "room" ? fetchRoomBans(currentChat.id).catch(() => []) : Promise.resolve([]),
            currentChat.kind === "room"
              ? fetchRoomInvitations(currentChat.id).catch(() => [])
              : Promise.resolve([]),
          ]);

        if (cancelled) {
          return;
        }

        setMessages(nextMessages);
        setMessageCursor(pagination.next_cursor);
        setActiveRoom(roomDetail);
        setActiveRoomMembers(roomMembers);
        setActiveRoomBans(roomBans);
        setActiveRoomInvitations(roomInvitations);

        if (roomDetail) {
          setRoomEditName(roomDetail.name);
          setRoomEditDescription(roomDetail.description ?? "");
          setRoomEditVisibility(roomDetail.visibility);
        }

        queueScrollToBottom();
        await markCurrentChatRead(currentChat);
      } catch (error) {
        if (!cancelled) {
          pushError(error);
        }
      } finally {
        if (!cancelled) {
          setMessagesLoading(false);
        }
      }
    }

    loadChat();
    return () => {
      cancelled = true;
    };
  }, [activeChat, shellStatus]);

  useEffect(() => {
    const viewport = messageViewportRef.current;
    if (!viewport) {
      return;
    }
    if (restoreScrollRef.current !== null) {
      const previousHeight = restoreScrollRef.current;
      restoreScrollRef.current = null;
      viewport.scrollTop = viewport.scrollHeight - previousHeight;
      return;
    }
    if (stickToBottomRef.current) {
      viewport.scrollTop = viewport.scrollHeight;
    }
  }, [messages]);

  async function refreshShell(user: User, preserveSelection: boolean) {
    const [
      nextJoinedRooms,
      nextPublicRooms,
      nextDialogs,
      nextFriends,
      nextIncomingRequests,
      nextOutgoingRequests,
      nextPeerBans,
      nextSummary,
    ] = await Promise.all([
      fetchJoinedRooms(),
      fetchPublicRooms(deferredPublicSearch),
      fetchDialogs(),
      fetchFriends(),
      fetchIncomingRequests(),
      fetchOutgoingRequests(),
      fetchPeerBans(),
      fetchNotificationSummary(),
    ]);

    const synced = updateUnreadCountsFromSummary(nextJoinedRooms, nextDialogs, nextSummary);

    setJoinedRooms(synced.joinedRooms);
    setPublicRooms(nextPublicRooms);
    setDialogs(synced.dialogs);
    setFriends(nextFriends);
    setIncomingRequests(nextIncomingRequests);
    setOutgoingRequests(nextOutgoingRequests);
    setPeerBans(nextPeerBans);
    setNotificationSummary(nextSummary);
    setShellStatus("ready");

    if (!preserveSelection || !activeChatRef.current) {
      startTransition(() => {
        setActiveChat(chooseInitialChat(synced.joinedRooms, synced.dialogs));
      });
    } else {
      const selection = activeChatRef.current;
      const stillExists =
        selection.kind === "room"
          ? synced.joinedRooms.some((room) => room.id === selection.id)
          : synced.dialogs.some((dialog) => dialog.id === selection.id);
      if (!stillExists) {
        startTransition(() => {
          setActiveChat(chooseInitialChat(synced.joinedRooms, synced.dialogs));
        });
      }
    }

    setProfile(user);
  }

  function pushError(error: unknown) {
    const message = error instanceof ApiError ? error.message : "Something went wrong.";
    setToast({ tone: "error", message });
  }

  function pushInfo(message: string) {
    setToast({ tone: "info", message });
  }

  function queueScrollToBottom() {
    stickToBottomRef.current = true;
    requestAnimationFrame(() => {
      if (messageViewportRef.current) {
        messageViewportRef.current.scrollTop = messageViewportRef.current.scrollHeight;
      }
    });
  }

  function writeSocket(type: string, payload: Record<string, unknown>) {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }
    wsRef.current.send(JSON.stringify({ type, payload }));
  }

  function sendPresenceHeartbeat(isActive: boolean) {
    writeSocket("presence.heartbeat", {
      tab_id: tabIdRef.current,
      is_active: isActive,
      last_interaction_at: new Date().toISOString(),
    });
  }

  function subscribeToChat(chat: ActiveChat) {
    writeSocket(chat.kind === "room" ? "room.subscribe" : "dialog.subscribe", {
      [`${chat.kind}_id`]: chat.id,
    });
  }

  function unsubscribeFromChat(chat: ActiveChat) {
    writeSocket(chat.kind === "room" ? "room.unsubscribe" : "dialog.unsubscribe", {
      [`${chat.kind}_id`]: chat.id,
    });
  }

  async function markCurrentChatRead(chat: ActiveChat) {
    try {
      await markChatRead(chat);
      if (chat.kind === "room") {
        setJoinedRooms((current) =>
          current.map((room) => (room.id === chat.id ? { ...room, unread_count: 0 } : room)),
        );
      } else {
        setDialogs((current) =>
          current.map((dialog) => (dialog.id === chat.id ? { ...dialog, unread_count: 0 } : dialog)),
        );
      }
    } catch {
      // Read updates are best effort on the client; the server remains authoritative.
    }
  }

  function handleSocketEvent(type: string, payload: Record<string, unknown>) {
    const currentUserId = profileRef.current?.id;
    if (!currentUserId) {
      return;
    }

    if (type === "presence.updated") {
      const userId = String(payload.user_id);
      const presence = payload.presence as User["presence"];
      setDialogs((current) =>
        current.map((dialog) => ({
          ...dialog,
          other_user: patchPresenceInUser(dialog.other_user, userId, presence),
        })),
      );
      setFriends((current) =>
        current.map((friend) => ({
          ...friend,
          user: patchPresenceInUser(friend.user, userId, presence),
        })),
      );
      setActiveRoomMembers((current) =>
        current.map((member) => ({
          ...member,
          user: patchPresenceInUser(member.user, userId, presence),
        })),
      );
      return;
    }

    if (type === "friend_request.created") {
      const request = payload.request as IncomingFriendRequest;
      setIncomingRequests((current) => [request, ...current.filter((item) => item.id !== request.id)]);
      setNotificationSummary((current) => ({
        ...current,
        incoming_friend_requests: current.incoming_friend_requests + 1,
      }));
      pushInfo(`New friend request from ${request.from_user.username}.`);
      return;
    }

    if (type === "friend_request.updated") {
      const request = payload.request as {
        id: string;
        status: "accepted" | "rejected" | "cancelled";
        other_user: User;
      };
      refreshCurrentShellSilently();
      if (request.status === "accepted") {
        pushInfo(`${request.other_user.username} accepted the friend request.`);
      } else if (request.status === "rejected") {
        pushInfo(`${request.other_user.username} rejected the friend request.`);
      }
      return;
    }

    if (type === "dialog.summary.updated") {
      const dialog = payload.dialog as DialogSummary;
      const isCurrent = activeChatRef.current?.kind === "dialog" && activeChatRef.current.id === dialog.id;
      const nextDialog = isCurrent ? { ...dialog, unread_count: 0 } : dialog;
      setDialogs((current) => upsertDialog(current, nextDialog));
      if (dialog.is_frozen) {
        refreshCurrentShellSilently();
      }
      if (!isCurrent && dialog.last_message && dialog.last_message.sender_id !== currentUserId) {
        pushInfo(`New message from ${dialog.other_user.username}.`);
      }
      return;
    }

    if (type === "room.invitation.created") {
      const invitation = payload.invitation as RoomInvitation;
      setPendingInvitations((current) => [
        { ...invitation, room_name: invitation.room_name ?? "Private room" },
        ...current.filter((item) => item.id !== invitation.id),
      ]);
      pushInfo(`Invitation received for ${invitation.room_name ?? "a private room"}.`);
      return;
    }

    if (type === "room.membership.updated") {
      const roomId = String(payload.room_id);
      const userId = String(payload.user_id);
      const action = String(payload.action);
      if (userId === currentUserId && ["left", "removed", "banned"].includes(action)) {
        if (activeChatRef.current?.kind === "room" && activeChatRef.current.id === roomId) {
          setActiveChat(null);
        }
      }
      refreshCurrentShellSilently();
      if (activeChatRef.current?.kind === "room" && activeChatRef.current.id === roomId) {
        refreshActiveRoomSilently(roomId);
      }
      return;
    }

    if (type === "room.message.created") {
      const message = payload.message as Message;
      setJoinedRooms((current) =>
        current.map((room) => {
          if (room.id !== message.chat_id) {
            return room;
          }
          const isCurrent = activeChatRef.current?.kind === "room" && activeChatRef.current.id === room.id;
          const unread = isCurrent ? 0 : (room.unread_count ?? 0) + (message.sender.id === currentUserId ? 0 : 1);
          return { ...room, unread_count: unread };
        }),
      );

      if (activeChatRef.current?.kind === "room" && activeChatRef.current.id === message.chat_id) {
        setMessages((current) => upsertMessage(current, message));
        if (message.sender.id !== currentUserId && !document.hidden && stickToBottomRef.current) {
          void markCurrentChatRead({ kind: "room", id: message.chat_id });
        }
      }
      return;
    }

    if (type === "dialog.message.created") {
      const message = payload.message as Message;
      setDialogs((current) =>
        current.map((dialog) => {
          if (dialog.id !== message.chat_id) {
            return dialog;
          }
          const isCurrent = activeChatRef.current?.kind === "dialog" && activeChatRef.current.id === dialog.id;
          return {
            ...dialog,
            unread_count: isCurrent ? 0 : dialog.unread_count + (message.sender.id === currentUserId ? 0 : 1),
            last_message: {
              id: message.id,
              sender_id: message.sender.id,
              text: message.text,
              created_at: message.created_at,
            },
          };
        }),
      );

      if (activeChatRef.current?.kind === "dialog" && activeChatRef.current.id === message.chat_id) {
        setMessages((current) => upsertMessage(current, message));
        if (message.sender.id !== currentUserId && !document.hidden && stickToBottomRef.current) {
          void markCurrentChatRead({ kind: "dialog", id: message.chat_id });
        }
      }
      return;
    }

    if (type === "room.message.updated" || type === "dialog.message.updated") {
      const message = payload.message as Message;
      if (isChatEqual(activeChatRef.current, { kind: message.chat_type, id: message.chat_id })) {
        setMessages((current) => upsertMessage(current, message));
      }
      if (message.chat_type === "dialog") {
        setDialogs((current) =>
          current.map((dialog) =>
            dialog.id === message.chat_id && dialog.last_message?.id === message.id
              ? {
                  ...dialog,
                  last_message: {
                    id: message.id,
                    sender_id: message.sender.id,
                    text: message.text,
                    created_at: message.created_at,
                  },
                }
              : dialog,
          ),
        );
      }
      return;
    }

    if (type === "room.message.deleted" || type === "dialog.message.deleted") {
      const chatId = String(payload.room_id ?? payload.dialog_id);
      const messageId = String(payload.message_id);
      if (activeChatRef.current?.id === chatId) {
        setMessages((current) => removeMessage(current, messageId));
      }
      return;
    }

    if (type === "room.read.updated") {
      const roomId = String(payload.room_id);
      const userId = String(payload.user_id);
      if (userId === currentUserId) {
        setJoinedRooms((current) =>
          current.map((room) =>
            room.id === roomId ? { ...room, unread_count: Number(payload.unread_count) } : room,
          ),
        );
      }
      return;
    }

    if (type === "dialog.read.updated") {
      const dialogId = String(payload.dialog_id);
      const userId = String(payload.user_id);
      if (userId === currentUserId) {
        setDialogs((current) =>
          current.map((dialog) =>
            dialog.id === dialogId ? { ...dialog, unread_count: Number(payload.unread_count) } : dialog,
          ),
        );
      }
    }
  }

  function refreshCurrentShellSilently() {
    const currentUser = profileRef.current;
    if (!currentUser) {
      return;
    }
    refreshShell(currentUser, true).catch(() => undefined);
  }

  function refreshActiveRoomSilently(roomId: string) {
    Promise.all([
      fetchRoomDetail(roomId).catch(() => null),
      fetchRoomMembers(roomId).catch(() => []),
      fetchRoomBans(roomId).catch(() => []),
      fetchRoomInvitations(roomId).catch(() => []),
    ])
      .then(([room, members, bans, invitations]) => {
        if (activeChatRef.current?.kind !== "room" || activeChatRef.current.id !== roomId) {
          return;
        }
        setActiveRoom(room);
        setActiveRoomMembers(members);
        setActiveRoomBans(bans);
        setActiveRoomInvitations(invitations);
      })
      .catch(() => undefined);
  }

  async function handleLoginSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      const user = await login({
        email: loginEmail,
        password: loginPassword,
        remember_me: rememberMe,
      });
      setProfile(user);
      await refreshShell(user, false);
      setLoginPassword("");
    } catch (error) {
      pushError(error);
    } finally {
      setBusy(false);
    }
  }

  async function handleRegisterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      await register({
        email: registerEmail,
        username: registerUsername,
        password: registerPassword,
      });
      pushInfo("Registration complete. Sign in with the new account.");
      setAuthMode("login");
      setLoginEmail(registerEmail);
      setRegisterPassword("");
    } catch (error) {
      pushError(error);
    } finally {
      setBusy(false);
    }
  }

  async function handleResetSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      await requestPasswordReset(resetEmail);
      pushInfo("If the address exists, a reset token has been issued.");
      setAuthMode("login");
    } catch (error) {
      pushError(error);
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    try {
      await logout();
    } catch (error) {
      pushError(error);
    } finally {
      setProfile(null);
      setShellStatus("guest");
      setActiveChat(null);
    }
  }

  async function handleSelectChat(nextChat: ActiveChat) {
    if (activeChatRef.current && isChatEqual(activeChatRef.current, nextChat)) {
      return;
    }
    startTransition(() => {
      setActiveChat(nextChat);
    });
  }

  async function handleOpenDialog(friend: FriendItem) {
    try {
      const existing = dialogs.find((dialog) => dialog.other_user.id === friend.user.id);
      if (existing) {
        await handleSelectChat({ kind: "dialog", id: existing.id });
        return;
      }
      const dialog = await ensureDialog(friend.user.id);
      const refreshedDialogs = await fetchDialogs();
      setDialogs(refreshedDialogs);
      await handleSelectChat({ kind: "dialog", id: dialog.id });
    } catch (error) {
      pushError(error);
    }
  }

  async function handleJoinRoom(roomId: string) {
    try {
      await joinRoom(roomId);
      pushInfo("Room joined.");
      refreshCurrentShellSilently();
      await handleSelectChat({ kind: "room", id: roomId });
    } catch (error) {
      pushError(error);
    }
  }

  async function handleLeaveRoom(roomId: string) {
    try {
      await leaveRoom(roomId);
      pushInfo("Room left.");
      refreshCurrentShellSilently();
    } catch (error) {
      pushError(error);
    }
  }

  async function handleLoadOlder() {
    if (!activeChat || !messageCursor || loadingOlder || !messageViewportRef.current) {
      return;
    }
    setLoadingOlder(true);
    restoreScrollRef.current = messageViewportRef.current.scrollHeight;
    try {
      const response = await fetchMessages(activeChat, messageCursor);
      setMessages((current) => [...response.messages, ...current]);
      setMessageCursor(response.pagination.next_cursor);
    } catch (error) {
      pushError(error);
    } finally {
      setLoadingOlder(false);
    }
  }

  async function handleComposerSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeChat) {
      return;
    }
    if (!composerText.trim() && queuedAttachments.length === 0) {
      return;
    }
    setBusy(true);
    try {
      const message = await sendMessage(activeChat, {
        text: composerText.trim(),
        reply_to_message_id: replyTarget?.id ?? null,
        attachment_ids: queuedAttachments.map((item) => item.id),
      });
      setMessages((current) => upsertMessage(current, message));
      setComposerText("");
      setReplyTarget(null);
      setQueuedAttachments([]);
      setAttachmentComment("");
      queueScrollToBottom();
      await markCurrentChatRead(activeChat);
    } catch (error) {
      pushError(error);
    } finally {
      setBusy(false);
    }
  }

  async function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) {
      return;
    }
    setBusy(true);
    try {
      const uploaded = await Promise.all(files.map((file) => uploadAttachment(file, attachmentComment)));
      setQueuedAttachments((current) => [...current, ...uploaded]);
      setAttachmentComment("");
    } catch (error) {
      pushError(error);
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  async function handleRemoveQueuedAttachment(attachmentId: string) {
    try {
      await deleteAttachment(attachmentId);
      setQueuedAttachments((current) => current.filter((item) => item.id !== attachmentId));
    } catch (error) {
      pushError(error);
    }
  }

  async function handleSaveEdit(messageId: string) {
    if (!activeChat) {
      return;
    }
    try {
      const updated = await editMessage(activeChat, messageId, editingText);
      setMessages((current) => upsertMessage(current, updated));
      setEditingMessageId(null);
      setEditingText("");
    } catch (error) {
      pushError(error);
    }
  }

  async function handleDeleteMessage(messageId: string) {
    if (!activeChat) {
      return;
    }
    try {
      await deleteMessage(activeChat, messageId);
      setMessages((current) => removeMessage(current, messageId));
    } catch (error) {
      pushError(error);
    }
  }

  async function handleCreateRoom(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const room = await createRoom({
        name: newRoomName,
        description: newRoomDescription,
        visibility: newRoomVisibility,
      });
      setShowCreateRoomModal(false);
      setNewRoomName("");
      setNewRoomDescription("");
      refreshCurrentShellSilently();
      await handleSelectChat({ kind: "room", id: room.id });
    } catch (error) {
      pushError(error);
    }
  }

  async function handleInviteUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeRoom) {
      return;
    }
    try {
      await inviteUserToRoom(activeRoom.id, inviteUsername);
      setInviteUsername("");
      pushInfo("Invitation sent.");
      refreshActiveRoomSilently(activeRoom.id);
    } catch (error) {
      pushError(error);
    }
  }

  async function handleSaveRoom(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeRoom) {
      return;
    }
    try {
      const updated = await updateRoom(activeRoom.id, {
        name: roomEditName,
        description: roomEditDescription,
        visibility: roomEditVisibility,
      });
      setActiveRoom((current) => (current ? { ...current, ...updated } : current));
      refreshCurrentShellSilently();
      pushInfo("Room updated.");
    } catch (error) {
      pushError(error);
    }
  }

  async function handleDeleteRoom() {
    if (!activeRoom) {
      return;
    }
    try {
      await deleteRoom(activeRoom.id);
      pushInfo("Room deleted.");
      setActiveChat(null);
      refreshCurrentShellSilently();
    } catch (error) {
      pushError(error);
    }
  }

  async function handleSendFriendRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await sendFriendRequest(friendRequestUsername, friendRequestMessage);
      pushInfo(`Friend request sent to ${friendRequestUsername}.`);
      setFriendRequestUsername("");
      setFriendRequestMessage("");
      setShowPeopleModal(false);
      refreshCurrentShellSilently();
    } catch (error) {
      pushError(error);
    }
  }

  async function handleAcceptInvitation(invitationId: string) {
    try {
      await acceptRoomInvitation(invitationId);
      setPendingInvitations((current) => current.filter((item) => item.id !== invitationId));
      refreshCurrentShellSilently();
    } catch (error) {
      pushError(error);
    }
  }

  async function handleRejectInvitation(invitationId: string) {
    try {
      await rejectRoomInvitation(invitationId);
      setPendingInvitations((current) => current.filter((item) => item.id !== invitationId));
    } catch (error) {
      pushError(error);
    }
  }

  async function loadSessions() {
    setSessionsLoading(true);
    try {
      setSessions(await fetchSessions());
    } catch (error) {
      pushError(error);
    } finally {
      setSessionsLoading(false);
    }
  }

  async function runAction(action: () => Promise<void>, onSuccess?: () => void) {
    try {
      await action();
      onSuccess?.();
    } catch (error) {
      pushError(error);
    }
  }

  function renderAuthCard() {
    return (
      <main className="auth-shell">
        <section className="auth-panel">
          <div className="eyebrow">M10 UI Integration</div>
          <h1>Welcome to Web Chat</h1>
          <p className="lede">
            Cookie-backed auth, room and dialog navigation, live history, moderation controls,
            attachments, unread state, and session management all run from the React client.
          </p>
          <div className="auth-tabs">
            <button className={authMode === "login" ? "is-active" : ""} onClick={() => setAuthMode("login")}>
              Sign In
            </button>
            <button
              className={authMode === "register" ? "is-active" : ""}
              onClick={() => setAuthMode("register")}
            >
              Register
            </button>
            <button className={authMode === "reset" ? "is-active" : ""} onClick={() => setAuthMode("reset")}>
              Reset
            </button>
          </div>

          {authMode === "login" ? (
            <form className="auth-form" onSubmit={handleLoginSubmit}>
              <label>
                Email
                <input value={loginEmail} onChange={(event) => setLoginEmail(event.target.value)} type="email" required />
              </label>
              <label>
                Password
                <input
                  value={loginPassword}
                  onChange={(event) => setLoginPassword(event.target.value)}
                  type="password"
                  required
                />
              </label>
              <label className="checkbox-row">
                <input checked={rememberMe} onChange={(event) => setRememberMe(event.target.checked)} type="checkbox" />
                Keep this browser signed in
              </label>
              <button className="primary-button" disabled={busy} type="submit">
                {busy ? "Signing in..." : "Sign In"}
              </button>
            </form>
          ) : null}

          {authMode === "register" ? (
            <form className="auth-form" onSubmit={handleRegisterSubmit}>
              <label>
                Email
                <input value={registerEmail} onChange={(event) => setRegisterEmail(event.target.value)} type="email" required />
              </label>
              <label>
                Username
                <input
                  value={registerUsername}
                  onChange={(event) => setRegisterUsername(event.target.value)}
                  type="text"
                  required
                />
              </label>
              <label>
                Password
                <input
                  value={registerPassword}
                  onChange={(event) => setRegisterPassword(event.target.value)}
                  type="password"
                  required
                />
              </label>
              <button className="primary-button" disabled={busy} type="submit">
                {busy ? "Creating..." : "Create Account"}
              </button>
            </form>
          ) : null}

          {authMode === "reset" ? (
            <form className="auth-form" onSubmit={handleResetSubmit}>
              <label>
                Account email
                <input value={resetEmail} onChange={(event) => setResetEmail(event.target.value)} type="email" required />
              </label>
              <button className="primary-button" disabled={busy} type="submit">
                {busy ? "Submitting..." : "Request Reset"}
              </button>
            </form>
          ) : null}

          <footer className="auth-footer">
            <span>WebSocket: {connectionState}</span>
            <span>Presence is driven from the live session socket.</span>
          </footer>
        </section>
      </main>
    );
  }

  if (shellStatus === "booting") {
    return (
      <main className="loading-shell">
        <div className="spinner" />
        <p>Bootstrapping chat client…</p>
      </main>
    );
  }

  if (shellStatus === "guest" || !profile) {
    return (
      <>
        {renderAuthCard()}
        {toast ? <Toast tone={toast.tone} message={toast.message} /> : null}
      </>
    );
  }

  const currentDialog =
    activeChat?.kind === "dialog" ? dialogs.find((dialog) => dialog.id === activeChat.id) ?? null : null;
  const activeFriend = currentDialog
    ? friends.find((friend) => friend.user.id === currentDialog.other_user.id) ?? null
    : null;
  const activePeerBan = currentDialog
    ? peerBans.find((ban) => ban.user.id === currentDialog.other_user.id) ?? null
    : null;
  const unreadRooms = joinedRooms.filter((room) => (room.unread_count ?? 0) > 0).length;
  const unreadDialogs = dialogs.filter((dialog) => dialog.unread_count > 0).length;

  return (
    <>
      <main className="app-shell">
        <header className="topbar">
          <div>
            <div className="eyebrow">Online Chat Server</div>
            <h1>Classic chat client</h1>
          </div>
          <div className="topbar-meta">
            <div className="connection-pill" data-state={connectionState}>
              {connectionState === "open" ? "Live" : connectionState === "connecting" ? "Connecting" : "Offline"}
            </div>
            <button className="ghost-button" onClick={() => setShowCreateRoomModal(true)}>
              New Room
            </button>
            <button className="ghost-button" onClick={() => setShowPeopleModal(true)}>
              People
            </button>
            <button
              className="ghost-button"
              onClick={() => {
                setShowSessionsModal(true);
                void loadSessions();
              }}
            >
              Sessions
            </button>
            <div className="profile-card">
              <div>
                <strong>{profile.username}</strong>
                <span>{profile.email}</span>
              </div>
              <button className="ghost-button" onClick={handleLogout}>
                Log Out
              </button>
            </div>
          </div>
        </header>

        <section className="workspace">
          <aside className="sidebar">
            <div className="sidebar-header">
              <button
                className={sidebarTab === "rooms" ? "is-active" : ""}
                onClick={() => setSidebarTab("rooms")}
              >
                Rooms
                {unreadRooms ? <span className="badge">{compactCount(unreadRooms)}</span> : null}
              </button>
              <button
                className={sidebarTab === "people" ? "is-active" : ""}
                onClick={() => setSidebarTab("people")}
              >
                Contacts
                {unreadDialogs || notificationSummary.incoming_friend_requests ? (
                  <span className="badge">
                    {compactCount(unreadDialogs + notificationSummary.incoming_friend_requests)}
                  </span>
                ) : null}
              </button>
            </div>

            {sidebarTab === "rooms" ? (
              <>
                <section className="sidebar-section">
                  <div className="section-title">Joined Rooms</div>
                  {joinedRooms.length ? (
                    joinedRooms.map((room) => (
                      <button
                        className={`list-item ${activeChat?.kind === "room" && activeChat.id === room.id ? "is-selected" : ""}`}
                        key={room.id}
                        onClick={() => void handleSelectChat({ kind: "room", id: room.id })}
                      >
                        <div>
                          <strong>{room.name}</strong>
                          <span>{room.visibility === "private" ? "Private room" : "Public room"}</span>
                        </div>
                        {(room.unread_count ?? 0) > 0 ? <span className="badge">{compactCount(room.unread_count ?? 0)}</span> : null}
                      </button>
                    ))
                  ) : (
                    <p className="empty-copy">No rooms joined yet.</p>
                  )}
                </section>

                <section className="sidebar-section">
                  <div className="section-title">Public Search</div>
                  <input
                    className="search-input"
                    onChange={(event) => setPublicSearch(event.target.value)}
                    placeholder="Search public rooms"
                    value={publicSearch}
                  />
                  {publicRooms.map((room) => {
                    const isJoined = joinedRooms.some((joined) => joined.id === room.id);
                    return (
                      <div className="list-card" key={room.id}>
                        <div>
                          <strong>{room.name}</strong>
                          <span>{room.member_count} members</span>
                        </div>
                        <button className="mini-button positive" disabled={isJoined} onClick={() => void handleJoinRoom(room.id)}>
                          {isJoined ? "Joined" : "Join"}
                        </button>
                      </div>
                    );
                  })}
                </section>

                {pendingInvitations.length ? (
                  <section className="sidebar-section">
                    <div className="section-title">Pending Invitations</div>
                    {pendingInvitations.map((invitation) => (
                      <div className="list-card" key={invitation.id}>
                        <div>
                          <strong>{invitation.room_name ?? invitation.room_id}</strong>
                          <span>{formatRelative(invitation.created_at)}</span>
                        </div>
                        <div className="inline-actions">
                          <button className="mini-button positive" onClick={() => void handleAcceptInvitation(invitation.id)}>
                            Accept
                          </button>
                          <button className="mini-button danger" onClick={() => void handleRejectInvitation(invitation.id)}>
                            Reject
                          </button>
                        </div>
                      </div>
                    ))}
                  </section>
                ) : null}
              </>
            ) : (
              <>
                <section className="sidebar-section">
                  <div className="section-title">Direct Dialogs</div>
                  {dialogs.length ? (
                    dialogs.map((dialog) => (
                      <button
                        className={`list-item ${activeChat?.kind === "dialog" && activeChat.id === dialog.id ? "is-selected" : ""}`}
                        key={dialog.id}
                        onClick={() => void handleSelectChat({ kind: "dialog", id: dialog.id })}
                      >
                        <div>
                          <strong>{dialog.other_user.username}</strong>
                          <span>
                            {dialog.other_user.presence ?? "offline"}
                            {dialog.is_frozen ? " · frozen" : ""}
                          </span>
                        </div>
                        {dialog.unread_count > 0 ? <span className="badge">{compactCount(dialog.unread_count)}</span> : null}
                      </button>
                    ))
                  ) : (
                    <p className="empty-copy">No dialogs yet.</p>
                  )}
                </section>

                <section className="sidebar-section">
                  <div className="section-title">Friends</div>
                  {friends.length ? (
                    friends.map((friend) => (
                      <div className="list-card" key={friend.user.id}>
                        <div>
                          <strong>{friend.user.username}</strong>
                          <span>{friend.user.presence ?? "offline"}</span>
                        </div>
                        <button className="mini-button positive" onClick={() => void handleOpenDialog(friend)}>
                          Open
                        </button>
                      </div>
                    ))
                  ) : (
                    <p className="empty-copy">No contacts yet.</p>
                  )}
                </section>

                <section className="sidebar-section">
                  <div className="section-title">Incoming Requests</div>
                  {incomingRequests.length ? (
                    incomingRequests.map((request) => (
                      <div className="list-card" key={request.id}>
                        <div>
                          <strong>{request.from_user.username}</strong>
                          <span>{request.message || "No message"}</span>
                        </div>
                        <div className="inline-actions">
                          <button
                            className="mini-button positive"
                            onClick={() => void runAction(() => acceptFriendRequest(request.id), refreshCurrentShellSilently)}
                          >
                            Accept
                          </button>
                          <button
                            className="mini-button danger"
                            onClick={() => void runAction(() => rejectFriendRequest(request.id), refreshCurrentShellSilently)}
                          >
                            Reject
                          </button>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="empty-copy">No incoming requests.</p>
                  )}
                </section>
              </>
            )}
          </aside>

          <section className="conversation">
            {activeChat ? (
              <>
                <header className="conversation-header">
                  <div>
                    <div className="eyebrow">{activeChat.kind === "room" ? activeRoom?.visibility ?? "room" : "dialog"}</div>
                    <h2>{activeChat.kind === "room" ? activeRoom?.name ?? "Room" : currentDialog?.other_user.username ?? "Dialog"}</h2>
                  </div>
                  <div className="conversation-actions">
                    {activeChat.kind === "room" ? (
                      <IconButton icon="leave" label="Leave room" onClick={() => void handleLeaveRoom(activeChat.id)} />
                    ) : null}
                    {activeChat.kind === "dialog" && currentDialog?.is_frozen ? <span className="warning-chip">Messaging frozen</span> : null}
                  </div>
                </header>

                <div
                  className="message-history"
                  onScroll={(event) => {
                    const target = event.currentTarget;
                    stickToBottomRef.current =
                      target.scrollHeight - target.scrollTop - target.clientHeight < 80;
                    if (target.scrollTop < 80) {
                      void handleLoadOlder();
                    }
                  }}
                  ref={messageViewportRef}
                >
                  {loadingOlder ? <div className="history-banner">Loading older messages…</div> : null}
                  {messageCursor ? <div className="history-banner">Scroll upward to load more history.</div> : null}
                  {messagesLoading ? <div className="history-banner">Loading conversation…</div> : null}
                  {!messagesLoading && !messages.length ? (
                    <div className="empty-history">
                      <h3>Start the conversation</h3>
                      <p>History loads from REST, and new messages arrive through the session socket.</p>
                    </div>
                  ) : null}

                  {messages.map((message) => {
                    const isOwn = message.sender.id === profile.id;
                    const canDelete =
                      isOwn ||
                      (activeChat.kind === "room" &&
                        ["owner", "admin"].includes(activeRoom?.current_user_role ?? "member"));
                    return (
                      <article className={`message-card ${isOwn ? "is-own" : ""}`} key={message.id}>
                        <header>
                          <strong>{message.sender.username}</strong>
                          <span>{formatTimestamp(message.created_at)}</span>
                        </header>
                        {message.reply_to ? (
                          <div className="reply-chip">
                            Replying to {message.reply_to.sender.username}: {message.reply_to.text || "Attachment"}
                          </div>
                        ) : null}
                        {editingMessageId === message.id ? (
                          <div className="edit-box">
                            <textarea value={editingText} onChange={(event) => setEditingText(event.target.value)} rows={3} />
                            <div className="inline-actions">
                              <IconButton icon="save" label="Save edit" onClick={() => void handleSaveEdit(message.id)} variant="positive" />
                              <IconButton
                                icon="cancel"
                                label="Cancel edit"
                                onClick={() => {
                                  setEditingMessageId(null);
                                  setEditingText("");
                                }}
                                variant="danger"
                              />
                            </div>
                          </div>
                        ) : (
                          <p>{message.text || "Attachment-only message"}</p>
                        )}
                        {message.attachments.length ? (
                          <div className="attachment-list">
                            {message.attachments.map((attachment) => {
                              const attachmentUrl = toPublicUrl(attachment.download_url);
                              const showImage = isImageAttachment(attachment.content_type);
                              const showVideo = isVideoAttachment(attachment.content_type);

                              return (
                                <div className="attachment-card" key={attachment.id}>
                                  {showImage ? (
                                    <a
                                      className="attachment-media-link"
                                      href={attachmentUrl}
                                      rel="noreferrer"
                                      target="_blank"
                                    >
                                      <img
                                        alt={attachment.filename}
                                        className="attachment-media attachment-image"
                                        loading="lazy"
                                        src={attachmentUrl}
                                      />
                                    </a>
                                  ) : null}
                                  {showVideo ? (
                                    <video className="attachment-media attachment-video" controls preload="metadata">
                                      <source src={attachmentUrl} type={attachment.content_type} />
                                      <a href={attachmentUrl} rel="noreferrer" target="_blank">
                                        {attachment.filename}
                                      </a>
                                    </video>
                                  ) : null}
                                  <a className="attachment-link" href={attachmentUrl} rel="noreferrer" target="_blank">
                                    {attachment.filename}
                                  </a>
                                </div>
                              );
                            })}
                          </div>
                        ) : null}
                        <footer>
                          <span>{message.is_edited ? "edited" : "posted"}</span>
                          <div className="inline-actions">
                            <IconButton icon="reply" label="Reply" onClick={() => setReplyTarget(message)} variant="positive" />
                            {isOwn ? (
                              <IconButton
                                icon="edit"
                                label="Edit message"
                                onClick={() => {
                                  setEditingMessageId(message.id);
                                  setEditingText(message.text);
                                }}
                                variant="positive"
                              />
                            ) : null}
                            {canDelete ? (
                              <IconButton icon="delete" label="Delete message" onClick={() => void handleDeleteMessage(message.id)} variant="danger" />
                            ) : null}
                          </div>
                        </footer>
                      </article>
                    );
                  })}
                </div>

                <form className="composer" onSubmit={handleComposerSubmit}>
                  {replyTarget ? (
                    <div className="composer-banner">
                      Replying to {replyTarget.sender.username}: {replyTarget.text || "Attachment"}
                      <IconButton icon="clear" label="Clear reply target" onClick={() => setReplyTarget(null)} variant="danger" />
                    </div>
                  ) : null}
                  {queuedAttachments.length ? (
                    <div className="composer-banner">
                      {queuedAttachments.map((attachment) => (
                        <span className="queued-chip" key={attachment.id}>
                          {attachment.filename}
                          <button onClick={() => void handleRemoveQueuedAttachment(attachment.id)} type="button">
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <textarea
                    onChange={(event) => setComposerText(event.target.value)}
                    placeholder={
                      activeChat.kind === "dialog" && currentDialog?.is_frozen
                        ? "This dialog is frozen by friendship or peer-ban rules."
                        : "Write a message"
                    }
                    rows={4}
                    value={composerText}
                  />
                  <div className="composer-tools">
                    <label aria-label="Attach files" className="file-label icon-button" title="Attach files">
                      <Icon name="attach" />
                      <span className="sr-only">Attach files</span>
                      <input multiple onChange={handleFileSelection} type="file" />
                    </label>
                    <input
                      onChange={(event) => setAttachmentComment(event.target.value)}
                      placeholder="Attachment comment"
                      value={attachmentComment}
                    />
                    <IconButton
                      disabled={busy || (activeChat.kind === "dialog" && currentDialog?.is_frozen)}
                      icon="send"
                      label="Send message"
                      type="submit"
                      variant="positive"
                    />
                  </div>
                </form>
              </>
            ) : (
              <div className="empty-history">
                <h2>Select a room or dialog</h2>
                <p>The left navigation shows joined rooms, searchable public rooms, contacts, and pending invites.</p>
              </div>
            )}
          </section>

          <aside className="context-panel">
            {activeChat?.kind === "room" && activeRoom ? (
              <>
                <section className="panel-card">
                  <div className="section-title">Room Details</div>
                  <div className="detail-grid">
                    <span>Owner</span>
                    <strong>{activeRoom.owner.username}</strong>
                    <span>Visibility</span>
                    <strong>{activeRoom.visibility}</strong>
                    <span>Members</span>
                    <strong>{activeRoom.member_count}</strong>
                    <span>Your role</span>
                    <strong>{activeRoom.current_user_role}</strong>
                  </div>
                </section>

                <section className="panel-card">
                  <div className="section-title">Members</div>
                  {activeRoomMembers.map((member) => (
                    <div className="list-card" key={member.user.id}>
                      <div className="list-card-content">
                        <strong>{member.user.username}</strong>
                        <span>
                          {member.role} · {member.user.presence ?? "offline"}
                        </span>
                      </div>
                      <div className="list-card-actions">
                        {activeRoom.current_user_role === "owner" && member.role === "member" ? (
                          <IconButton
                            icon="promote"
                            label={`Promote ${member.user.username} to admin`}
                            onClick={() =>
                              void runAction(
                                () => promoteRoomAdmin(activeRoom.id, member.user.id),
                                () => refreshActiveRoomSilently(activeRoom.id),
                              )
                            }
                            variant="positive"
                          />
                        ) : null}
                        {activeRoom.current_user_role === "owner" && member.role === "admin" ? (
                          <IconButton
                            icon="demote"
                            label={`Demote ${member.user.username} from admin`}
                            onClick={() =>
                              void runAction(
                                () => demoteRoomAdmin(activeRoom.id, member.user.id),
                                () => refreshActiveRoomSilently(activeRoom.id),
                              )
                            }
                            variant="danger"
                          />
                        ) : null}
                        {["owner", "admin"].includes(activeRoom.current_user_role) && member.role !== "owner" ? (
                          <>
                            <IconButton
                              icon="remove"
                              label={`Remove ${member.user.username} from room`}
                              onClick={() =>
                                void runAction(
                                  () => removeRoomMember(activeRoom.id, member.user.id),
                                  () => refreshActiveRoomSilently(activeRoom.id),
                                )
                              }
                              variant="danger"
                            />
                            <IconButton
                              icon="ban"
                              label={`Ban ${member.user.username} from room`}
                              onClick={() =>
                                void runAction(
                                  () => banRoomUser(activeRoom.id, member.user.id),
                                  () => refreshActiveRoomSilently(activeRoom.id),
                                )
                              }
                              variant="danger"
                            />
                          </>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </section>

                {["owner", "admin"].includes(activeRoom.current_user_role) ? (
                  <>
                    <section className="panel-card">
                      <div className="section-title">Invite User</div>
                      <form className="stack-form" onSubmit={handleInviteUser}>
                        <input value={inviteUsername} onChange={(event) => setInviteUsername(event.target.value)} placeholder="username" />
                        <IconButton icon="invite" label="Send room invite" type="submit" variant="positive" />
                      </form>
                    </section>

                    <section className="panel-card">
                      <div className="section-title">Bans</div>
                      {activeRoomBans.length ? (
                        activeRoomBans.map((ban) => (
                          <div className="list-card" key={ban.user.id}>
                            <div className="list-card-content">
                              <strong>{ban.user.username}</strong>
                              <span>by {ban.banned_by.username}</span>
                            </div>
                            <div className="list-card-actions">
                              <IconButton
                                icon="unban"
                                label={`Unban ${ban.user.username}`}
                                onClick={() =>
                                  void runAction(
                                    () => unbanRoomUser(activeRoom.id, ban.user.id),
                                    () => refreshActiveRoomSilently(activeRoom.id),
                                  )
                                }
                                variant="positive"
                              />
                            </div>
                          </div>
                        ))
                      ) : (
                        <p className="empty-copy">No active bans.</p>
                      )}
                    </section>

                    <section className="panel-card">
                      <div className="section-title">Pending Invites</div>
                      {activeRoomInvitations.length ? (
                        activeRoomInvitations.map((invitation) => (
                          <div className="list-card" key={invitation.id}>
                            <div className="list-card-content">
                              <strong>{invitation.user?.username ?? "Pending user"}</strong>
                              <span>{formatRelative(invitation.created_at)}</span>
                            </div>
                          </div>
                        ))
                      ) : (
                        <p className="empty-copy">No pending room invitations.</p>
                      )}
                    </section>
                  </>
                ) : null}

                {activeRoom.current_user_role === "owner" ? (
                  <section className="panel-card danger-card">
                    <div className="section-title">Owner Controls</div>
                    <form className="stack-form" onSubmit={handleSaveRoom}>
                      <input value={roomEditName} onChange={(event) => setRoomEditName(event.target.value)} />
                      <textarea rows={3} value={roomEditDescription} onChange={(event) => setRoomEditDescription(event.target.value)} />
                      <select value={roomEditVisibility} onChange={(event) => setRoomEditVisibility(event.target.value as RoomDetail["visibility"])}>
                        <option value="public">Public</option>
                        <option value="private">Private</option>
                      </select>
                      <button className="primary-button" type="submit">
                        Save Room
                      </button>
                    </form>
                    <button className="danger-button" onClick={() => void handleDeleteRoom()}>
                      Delete Room
                    </button>
                  </section>
                ) : null}
              </>
            ) : currentDialog ? (
              <>
                <section className="panel-card">
                  <div className="section-title">Contact</div>
                  <div className="detail-grid">
                    <span>User</span>
                    <strong>{currentDialog.other_user.username}</strong>
                    <span>Presence</span>
                    <strong>{currentDialog.other_user.presence ?? "offline"}</strong>
                    <span>Status</span>
                    <strong>{currentDialog.is_frozen ? "Frozen" : "Active"}</strong>
                  </div>
                </section>

                <section className="panel-card">
                  <div className="section-title">Relationship</div>
                  {activeFriend ? <p className="empty-copy">Friends since {formatTimestamp(activeFriend.friend_since)}</p> : <p className="empty-copy">Not in friends list.</p>}
                  <div className="inline-actions wrap">
                    {activeFriend ? (
                      <IconButton
                        icon="friend-remove"
                        label={`Remove ${currentDialog.other_user.username} from friends`}
                        onClick={() => void runAction(() => removeFriend(activeFriend.user.id), refreshCurrentShellSilently)}
                        variant="danger"
                      />
                    ) : null}
                    {activePeerBan ? (
                      <IconButton
                        icon="peer-unban"
                        label={`Remove peer ban for ${currentDialog.other_user.username}`}
                        onClick={() => void runAction(() => removePeerBan(activePeerBan.user.id), refreshCurrentShellSilently)}
                        variant="positive"
                      />
                    ) : (
                      <IconButton
                        icon="peer-ban"
                        label={`Create peer ban for ${currentDialog.other_user.username}`}
                        onClick={() => void runAction(() => createPeerBan(currentDialog.other_user.id), refreshCurrentShellSilently)}
                        variant="danger"
                      />
                    )}
                  </div>
                </section>
              </>
            ) : (
              <section className="panel-card">
                <div className="section-title">Context</div>
                <p className="empty-copy">Member lists, moderation tools, and contact details appear here for the selected chat.</p>
              </section>
            )}
          </aside>
        </section>
      </main>

      {showCreateRoomModal ? (
        <Modal title="Create Room" onClose={() => setShowCreateRoomModal(false)}>
          <form className="stack-form" onSubmit={handleCreateRoom}>
            <label>
              Name
              <input value={newRoomName} onChange={(event) => setNewRoomName(event.target.value)} required />
            </label>
            <label>
              Description
              <textarea rows={3} value={newRoomDescription} onChange={(event) => setNewRoomDescription(event.target.value)} />
            </label>
            <label>
              Visibility
              <select value={newRoomVisibility} onChange={(event) => setNewRoomVisibility(event.target.value as RoomDetail["visibility"])}>
                <option value="public">Public</option>
                <option value="private">Private</option>
              </select>
            </label>
            <button className="primary-button" type="submit">
              Create
            </button>
          </form>
        </Modal>
      ) : null}

      {showPeopleModal ? (
        <Modal title="People Actions" onClose={() => setShowPeopleModal(false)}>
          <form className="stack-form" onSubmit={handleSendFriendRequest}>
            <label>
              Username
              <input value={friendRequestUsername} onChange={(event) => setFriendRequestUsername(event.target.value)} required />
            </label>
            <label>
              Message
              <textarea rows={3} value={friendRequestMessage} onChange={(event) => setFriendRequestMessage(event.target.value)} />
            </label>
            <button className="primary-button" type="submit">
              Send Friend Request
            </button>
          </form>
          {outgoingRequests.length ? (
            <section className="panel-card">
              <div className="section-title">Outgoing Requests</div>
              {outgoingRequests.map((request) => (
                <div className="list-card" key={request.id}>
                  <div>
                    <strong>{request.to_user.username}</strong>
                    <span>{request.message || "No message"}</span>
                  </div>
                </div>
              ))}
            </section>
          ) : null}
          {peerBans.length ? (
            <section className="panel-card">
              <div className="section-title">Peer Bans</div>
              {peerBans.map((ban) => (
                <div className="list-card" key={ban.user.id}>
                  <div>
                    <strong>{ban.user.username}</strong>
                    <span>{formatRelative(ban.created_at)}</span>
                  </div>
                  <button
                    className="mini-button positive"
                    onClick={() => void runAction(() => removePeerBan(ban.user.id), refreshCurrentShellSilently)}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </section>
          ) : null}
        </Modal>
      ) : null}

      {showSessionsModal ? (
        <Modal title="Active Sessions" onClose={() => setShowSessionsModal(false)}>
          {sessionsLoading ? <p className="empty-copy">Loading sessions…</p> : null}
          {sessions.map((session) => (
            <div className="list-card" key={session.id}>
              <div>
                <strong>{session.is_current ? "Current session" : "Active session"}</strong>
                <span>{session.user_agent || "Unknown agent"}</span>
                <span>{session.ip_address || "Unknown IP"}</span>
              </div>
              {!session.is_current ? (
                <button className="mini-button danger" onClick={() => void runAction(() => revokeSession(session.id), loadSessions)}>
                  Revoke
                </button>
              ) : (
                <span className="warning-chip">Current</span>
              )}
            </div>
          ))}
        </Modal>
      ) : null}

      {toast ? <Toast tone={toast.tone} message={toast.message} /> : null}
    </>
  );
}

function Modal(props: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-card" role="dialog" aria-modal="true" aria-label={props.title}>
        <header className="modal-header">
          <h2>{props.title}</h2>
          <button className="ghost-button" onClick={props.onClose}>
            Close
          </button>
        </header>
        {props.children}
      </section>
    </div>
  );
}

function Toast(props: { tone: ToastTone; message: string }) {
  return <div className={`toast toast-${props.tone}`}>{props.message}</div>;
}
