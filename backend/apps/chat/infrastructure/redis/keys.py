def presence_user_key(user_id) -> str:
    return f"presence:user:{user_id}"


def user_connections_key(user_id) -> str:
    return f"conn:user:{user_id}"


def presence_connection_key(connection_key: str) -> str:
    return f"presence:connection:{connection_key}"


def typing_key(*, chat_type: str, chat_id, user_id) -> str:
    return f"typing:{chat_type}:{chat_id}:{user_id}"

