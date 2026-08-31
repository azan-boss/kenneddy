"""
JWT-over-query-string authentication middleware for Django Channels.

The WebSocket handshake is an HTTP GET, so the browser can't attach an
Authorization header (WebSocket API doesn't support custom headers in the
browser). The standard workaround is to pass the JWT as a query param:

    ws://localhost:8000/ws/orders/5/?token=<access_token>

This middleware wraps the Channels ASGI application, reads the token from
the query string, validates it with simplejwt, and populates scope["user"]
before the consumer sees the connection — exactly like
AuthMiddlewareStack does for session auth.

If the token is missing or invalid, scope["user"] is set to AnonymousUser
(the consumer then rejects the connection).
"""
from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError


@database_sync_to_async
def _get_user_from_token(token_str):
    """Validate JWT and return the corresponding User, or AnonymousUser."""
    from django.contrib.auth.models import User
    try:
        token = AccessToken(token_str)
        user_id = token["user_id"]
        return User.objects.get(pk=user_id)
    except (TokenError, User.DoesNotExist, KeyError):
        return AnonymousUser()


class JwtAuthMiddleware:
    """ASGI middleware that reads ?token=<jwt> and populates scope['user']."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            qs     = parse_qs(scope.get("query_string", b"").decode())
            tokens = qs.get("token", [])
            if tokens:
                scope["user"] = await _get_user_from_token(tokens[0])
            else:
                scope["user"] = AnonymousUser()
        return await self.inner(scope, receive, send)


def JwtAuthMiddlewareStack(inner):
    """Drop-in replacement for AuthMiddlewareStack that uses JWT instead of sessions."""
    return JwtAuthMiddleware(inner)
