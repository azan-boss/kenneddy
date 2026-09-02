"""
Kennedy Moon Grill — Email service powered by Resend.
All outbound emails go through this module.
"""

import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_resend():
    """Lazy import resend so startup doesn't crash if package is missing."""
    try:
        import resend as _resend
        api_key = getattr(settings, "RESEND_API_KEY", "")
        if not api_key:
            logger.warning("RESEND_API_KEY not set — emails will be skipped.")
            return None
        _resend.api_key = api_key
        return _resend
    except ImportError:
        logger.error("resend package not installed. Run: pip install resend")
        return None


FROM_ADDRESS = "Kennedy Moon Grill <onboarding@resend.dev>"


def send_password_reset_email(to_email: str, reset_link: str, username: str) -> bool:
    """
    Send a password reset email via Resend.
    Returns True on success, False on failure (never raises).
    """
    resend = _get_resend()
    if resend is None:
        logger.info(f"[EMAIL SKIP] Password reset for {to_email}: {reset_link}")
        return False

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto">
      <h2 style="color:#d97706">🌙 Kennedy Moon Grill</h2>
      <p>Assalamu Alaikum <strong>{username}</strong>,</p>
      <p>Aapne password reset request ki hai. Neeche diye link par click karein:</p>
      <a href="{reset_link}"
         style="display:inline-block;background:#d97706;color:#fff;padding:12px 24px;
                border-radius:8px;text-decoration:none;font-weight:bold;margin:16px 0">
        Reset Password
      </a>
      <p style="color:#888;font-size:13px">
        Yeh link 1 ghante mein expire ho jaata hai.<br>
        Agar aapne yeh request nahi ki, toh is email ko ignore kar dein.
      </p>
      <hr style="border:none;border-top:1px solid #eee">
      <p style="color:#aaa;font-size:12px">Kennedy Moon Grill &mdash; Karachi, Pakistan</p>
    </div>
    """

    try:
        r = resend.Emails.send({
            "from": FROM_ADDRESS,
            "to": to_email,
            "subject": "Password Reset — Kennedy Moon Grill",
            "html": html,
        })
        logger.info(f"Password reset email sent to {to_email}: {r}")
        return True
    except Exception as exc:
        logger.error(f"Resend failed for {to_email}: {exc}")
        return False


def send_otp_email(to_email: str, otp_code: str, username: str) -> bool:
    """
    Send a 6-digit OTP verification email via Resend.
    Returns True on success, False on failure (never raises).
    """
    resend = _get_resend()
    if resend is None:
        logger.info(f"[EMAIL SKIP] OTP for {to_email}: {otp_code}")
        return False

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto">
      <h2 style="color:#d97706">🌙 Kennedy Moon Grill</h2>
      <p>Assalamu Alaikum <strong>{username}</strong>,</p>
      <p>Aapka email verification code hai:</p>
      <div style="font-size:48px;font-weight:bold;letter-spacing:12px;
                  color:#d97706;text-align:center;padding:24px 0">
        {otp_code}
      </div>
      <p style="color:#888;font-size:13px;text-align:center">
        Yeh code 10 minute mein expire ho jaata hai.
      </p>
      <hr style="border:none;border-top:1px solid #eee">
      <p style="color:#aaa;font-size:12px">Kennedy Moon Grill &mdash; Karachi, Pakistan</p>
    </div>
    """

    try:
        r = resend.Emails.send({
            "from": FROM_ADDRESS,
            "to": to_email,
            "subject": "Email Verification — Kennedy Moon Grill",
            "html": html,
        })
        logger.info(f"OTP email sent to {to_email}: {r}")
        return True
    except Exception as exc:
        logger.error(f"Resend OTP failed for {to_email}: {exc}")
        return False
