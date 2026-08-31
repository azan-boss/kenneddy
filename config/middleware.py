"""
Custom middleware for the Kennedy Django app.
"""
from django.http import HttpResponseRedirect


class APIPathMiddleware:
    """
    Frontend clients sometimes forget to prefix API calls with `/api`,
    which results in 404s (e.g. calling `/orders/` instead of
    `/api/orders/`). This middleware catches requests that look like
    they were meant for the API but are missing the `/api` prefix, and
    redirects them to the correct path.

    Paths that are known to be non-API (admin, static files, schema/docs,
    health checks, etc.) are left untouched.
    """

    # Path prefixes that should never be rewritten — they are either
    # already correctly namespaced or belong to non-API routes.
    EXCLUDED_PREFIXES = (
        "/api/",
        "/admin/",
        "/static/",
        "/media/",
        "/schema/",
        "/docs/",
        "/favicon.ico",
        "/ws/",
    )

    # Known API resource roots. If a request path starts with one of
    # these (and isn't already excluded above), it's almost certainly a
    # frontend call that forgot the `/api` prefix.
    API_LIKE_PREFIXES = (
        "/auth/",
        "/orders/",
        "/menu/",
        "/favourites/",
        "/tracking/",
        "/profile/",
        "/addresses/",
        "/elevenlabs/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        if not path.startswith(self.EXCLUDED_PREFIXES) and path.startswith(
            self.API_LIKE_PREFIXES
        ):
            new_path = f"/api{path}"

            if request.META.get("QUERY_STRING"):
                new_path = f"{new_path}?{request.META['QUERY_STRING']}"

            return HttpResponseRedirect(new_path)

        return self.get_response(request)
