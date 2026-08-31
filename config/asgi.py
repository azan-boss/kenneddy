"""
ASGI config for Kennedy Moon Grill backend.

Routes:
  HTTP  → Django's standard ASGI application (DRF, admin, everything else)
  WS    → Channels consumer via JwtAuthMiddlewareStack

WebSocket auth: JWT passed as ?token=<access_token> query param (browsers
can't set Authorization headers during WebSocket upgrade).

To run with WebSocket support:
    daphne -p 8000 config.asgi:application
    # or
    uvicorn config.asgi:application --port 8000

Plain `python manage.py runserver` still works fine for HTTP endpoints
(Django 4.2+ uses ASGI internally), but it does NOT route WebSocket
connections — use daphne/uvicorn for WS testing.
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application
from django.conf import settings
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

django_asgi_app = get_asgi_application()
if settings.DEBUG:
    django_asgi_app = ASGIStaticFilesHandler(django_asgi_app)

from channels.routing import ProtocolTypeRouter, URLRouter
from tracking.routing import websocket_urlpatterns
from tracking.auth import JwtAuthMiddlewareStack

application = ProtocolTypeRouter({
    # All HTTP goes to Django's normal handler (DRF, admin, etc.)
    "http": django_asgi_app,

    # WebSocket connections: JWT-authenticated, then routed to consumers
    "websocket": JwtAuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
