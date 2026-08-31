"""
ElevenLabs integration views for Kennedy Moon Grill.

GET /api/elevenlabs/signed-url/
  - If user is logged in (JWT provided) → returns signed_url + full user context
    so the React frontend passes it as dynamicVariables to ElevenLabs.
    The AI then greets the user by name and links orders to their real account.
  - If no valid JWT → returns signed_url + is_guest: true
    The AI will ask them to login or collect info manually.
"""
import requests
from decouple import config as env
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


ELEVENLABS_API_KEY = env("ELEVENLABS_API_KEY", default="")
ELEVENLABS_AGENT_ID = env("ELEVENLABS_AGENT_ID", default="")


def _get_signed_url():
    """Calls ElevenLabs API and returns a short-lived signed WebRTC URL."""
    resp = requests.get(
        f"https://api.elevenlabs.io/v1/convai/conversation/get_signed_url"
        f"?agent_id={ELEVENLABS_AGENT_ID}",
        headers={"xi-api-key": ELEVENLABS_API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("signed_url", "")


class ElevenLabsSignedUrlView(APIView):
    """
    GET /api/elevenlabs/signed-url/
    Works for BOTH logged-in users and guests.

    Logged-in user (sends JWT in Authorization header):
      Returns: { signed_url, is_guest: false, user: { id, username, full_name, phone, area } }
      Frontend passes user data as dynamicVariables → AI greets by name, links order to real account.

    Guest (no JWT):
      Returns: { signed_url, is_guest: true }
      AI asks for name, phone, address manually during the call.
    """

    # Public — no auth required. We manually try to decode JWT if present.
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        if not ELEVENLABS_API_KEY or not ELEVENLABS_AGENT_ID:
            return Response(
                {"detail": "ElevenLabs API key or Agent ID not configured in .env"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # ── Try to identify logged-in user from JWT (optional) ─────────────────
        user_context = None
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if auth_header.startswith("Bearer "):
            try:
                jwt_auth = JWTAuthentication()
                validated_token = jwt_auth.get_validated_token(
                    auth_header.split(" ")[1]
                )
                user = jwt_auth.get_user(validated_token)

                profile = getattr(user, "profile", None)
                default_address = user.addresses.filter(is_default=True).first()

                user_context = {
                    "user_id": str(user.id),
                    "username": user.username,
                    "full_name": profile.full_name if profile else user.get_full_name() or user.username,
                    "phone": profile.phone if profile else "",
                    "delivery_area": default_address.area if default_address else "",
                    "delivery_address": (
                        f"{default_address.street}, {default_address.area}"
                        if default_address else ""
                    ),
                }
            except (InvalidToken, TokenError, Exception):
                # JWT invalid or expired — treat as guest
                user_context = None

        # ── Get signed URL from ElevenLabs ─────────────────────────────────────
        try:
            signed_url = _get_signed_url()
        except requests.RequestException as e:
            return Response(
                {"detail": f"ElevenLabs API error: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if user_context:
            return Response({
                "signed_url": signed_url,
                "is_guest": False,
                "user": user_context,
            })
        else:
            return Response({
                "signed_url": signed_url,
                "is_guest": True,
                "user": None,
            })
