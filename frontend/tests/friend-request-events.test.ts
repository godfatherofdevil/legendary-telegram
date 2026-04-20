import { describe, expect, it } from "vitest";
import { applyFriendRequestUpdate } from "../src/lib/friendRequestEvents";
import type { FriendItem, IncomingFriendRequest, NotificationSummary, OutgoingFriendRequest, User } from "../src/types";

function buildUser(overrides: Partial<User> = {}): User {
  return {
    id: "usr_01",
    username: "alice",
    ...overrides,
  };
}

function buildIncomingRequest(overrides: Partial<IncomingFriendRequest> = {}): IncomingFriendRequest {
  return {
    id: "fr_01",
    from_user: buildUser(),
    message: "Hi",
    created_at: "2026-04-20T10:00:00Z",
    ...overrides,
  };
}

function buildOutgoingRequest(overrides: Partial<OutgoingFriendRequest> = {}): OutgoingFriendRequest {
  return {
    id: "fr_01",
    to_user: buildUser({ id: "usr_02", username: "bob" }),
    message: "Hi",
    created_at: "2026-04-20T10:00:00Z",
    ...overrides,
  };
}

function buildFriend(overrides: Partial<FriendItem> = {}): FriendItem {
  return {
    user: buildUser({ id: "usr_02", username: "bob" }),
    friend_since: "2026-04-20T10:05:00Z",
    ...overrides,
  };
}

function buildSummary(overrides: Partial<NotificationSummary> = {}): NotificationSummary {
  return {
    rooms: [],
    dialogs: [],
    incoming_friend_requests: 0,
    ...overrides,
  };
}

describe("applyFriendRequestUpdate", () => {
  it("moves an accepted incoming request into friends and clears the badge count", () => {
    const nextState = applyFriendRequestUpdate(
      {
        friends: [],
        incomingRequests: [buildIncomingRequest()],
        outgoingRequests: [],
        notificationSummary: buildSummary({ incoming_friend_requests: 1 }),
      },
      {
        id: "fr_01",
        status: "accepted",
        other_user: buildUser(),
        responded_at: "2026-04-20T10:06:00Z",
      },
    );

    expect(nextState.incomingRequests).toEqual([]);
    expect(nextState.notificationSummary.incoming_friend_requests).toBe(0);
    expect(nextState.friends).toEqual([
      {
        user: buildUser(),
        friend_since: "2026-04-20T10:06:00Z",
      },
    ]);
  });

  it("removes an accepted outgoing request and prepends the new friend", () => {
    const nextState = applyFriendRequestUpdate(
      {
        friends: [buildFriend({ user: buildUser({ id: "usr_03", username: "carol" }) })],
        incomingRequests: [],
        outgoingRequests: [buildOutgoingRequest()],
        notificationSummary: buildSummary(),
      },
      {
        id: "fr_01",
        status: "accepted",
        other_user: buildUser({ id: "usr_02", username: "bob" }),
        responded_at: "2026-04-20T10:06:00Z",
      },
    );

    expect(nextState.outgoingRequests).toEqual([]);
    expect(nextState.friends.map((friend) => friend.user.username)).toEqual(["bob", "carol"]);
  });

  it("drops a rejected request without creating a friendship", () => {
    const nextState = applyFriendRequestUpdate(
      {
        friends: [],
        incomingRequests: [buildIncomingRequest()],
        outgoingRequests: [buildOutgoingRequest()],
        notificationSummary: buildSummary({ incoming_friend_requests: 1 }),
      },
      {
        id: "fr_01",
        status: "rejected",
        other_user: buildUser({ id: "usr_02", username: "bob" }),
      },
    );

    expect(nextState.friends).toEqual([]);
    expect(nextState.incomingRequests).toEqual([]);
    expect(nextState.outgoingRequests).toEqual([]);
    expect(nextState.notificationSummary.incoming_friend_requests).toBe(0);
  });
});
