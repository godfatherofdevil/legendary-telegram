import type { FriendItem, IncomingFriendRequest, NotificationSummary, OutgoingFriendRequest, User } from "../types";

export interface FriendRequestUpdatePayload {
  id: string;
  status: "accepted" | "rejected" | "cancelled";
  other_user: User;
  responded_at?: string;
}

export interface FriendRequestUiState {
  friends: FriendItem[];
  incomingRequests: IncomingFriendRequest[];
  outgoingRequests: OutgoingFriendRequest[];
  notificationSummary: NotificationSummary;
}

export function applyFriendRequestUpdate(
  state: FriendRequestUiState,
  request: FriendRequestUpdatePayload,
): FriendRequestUiState {
  const hadIncomingRequest = state.incomingRequests.some((item) => item.id === request.id);
  const nextIncomingRequests = state.incomingRequests.filter((item) => item.id !== request.id);
  const nextOutgoingRequests = state.outgoingRequests.filter((item) => item.id !== request.id);

  const nextFriends =
    request.status === "accepted"
      ? upsertFriend(state.friends, {
          user: request.other_user,
          friend_since: request.responded_at ?? new Date().toISOString(),
        })
      : state.friends;

  return {
    friends: nextFriends,
    incomingRequests: nextIncomingRequests,
    outgoingRequests: nextOutgoingRequests,
    notificationSummary: {
      ...state.notificationSummary,
      incoming_friend_requests: hadIncomingRequest
        ? Math.max(0, state.notificationSummary.incoming_friend_requests - 1)
        : state.notificationSummary.incoming_friend_requests,
    },
  };
}

function upsertFriend(friends: FriendItem[], nextFriend: FriendItem): FriendItem[] {
  return [nextFriend, ...friends.filter((friend) => friend.user.id !== nextFriend.user.id)];
}
