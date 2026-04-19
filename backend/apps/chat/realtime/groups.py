PRESENCE_GROUP = "presence.all"


def user_group(user_id) -> str:
    return f"user.{user_id}"


def room_group(room_id) -> str:
    return f"room.{room_id}"


def dialog_group(dialog_id) -> str:
    return f"dialog.{dialog_id}"
