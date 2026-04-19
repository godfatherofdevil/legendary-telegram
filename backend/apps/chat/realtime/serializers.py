def build_broadcast_event(*, event_type: str, payload: dict) -> dict:
    return {
        "type": "broadcast.event",
        "event_type": event_type,
        "payload": payload,
    }


def build_control_event(*, control_type: str, payload: dict) -> dict:
    return {
        "type": control_type,
        "payload": payload,
    }
