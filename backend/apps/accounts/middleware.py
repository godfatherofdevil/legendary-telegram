from .services import sync_session_record


class SessionTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            getattr(request, "user", None)
            and request.user.is_authenticated
            and request.session.session_key
        ):
            sync_session_record(request)
        return response
