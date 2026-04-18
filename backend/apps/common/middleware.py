from django.conf import settings
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.utils.cache import patch_vary_headers


class CorsMiddleware:
    """Add CORS headers for configured browser origins and answer valid preflight requests."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._is_preflight(request):
            response = HttpResponse(status=200)
        else:
            response = self.get_response(request)
        return self._apply_headers(request, response)

    def _is_preflight(self, request) -> bool:
        return (
            request.method == "OPTIONS"
            and bool(request.headers.get("Origin"))
            and bool(request.headers.get("Access-Control-Request-Method"))
        )

    def _apply_headers(self, request, response):
        origin = request.headers.get("Origin")
        if origin not in set(getattr(settings, "CORS_ALLOWED_ORIGINS", [])):
            return response

        response["Access-Control-Allow-Origin"] = origin
        patch_vary_headers(response, ("Origin",))

        if getattr(settings, "CORS_ALLOW_CREDENTIALS", False):
            response["Access-Control-Allow-Credentials"] = "true"

        if self._is_preflight(request):
            response["Access-Control-Allow-Methods"] = ", ".join(settings.CORS_ALLOW_METHODS)
            requested_headers = request.headers.get("Access-Control-Request-Headers", "")
            allow_headers = requested_headers or ", ".join(settings.CORS_ALLOW_HEADERS)
            response["Access-Control-Allow-Headers"] = allow_headers

        return response


class EnsureCsrfCookieMiddleware:
    """Force CSRF token issuance so browser clients can authenticate via session cookies."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        get_token(request)
        return self.get_response(request)
