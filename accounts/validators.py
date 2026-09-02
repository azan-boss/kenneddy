"""
Custom password validators for Kennedy Moon Grill.
All validators follow Django's PASSWORD_VALIDATORS interface.
"""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class LetterAndNumberValidator:
    """
    Reject passwords that are all numbers or have no digits.
    Frontend enforces: min 8 chars with ≥1 letter AND ≥1 number.
    This ensures the backend always agrees, even on direct API calls.
    """

    def validate(self, password, user=None):
        has_letter = any(c.isalpha() for c in password)
        has_digit = any(c.isdigit() for c in password)

        if not has_letter:
            raise ValidationError(
                _("Password mein kam az kam ek harf (a-z) hona chahiye."),
                code="password_no_letter",
            )
        if not has_digit:
            raise ValidationError(
                _("Password mein kam az kam ek number hona chahiye."),
                code="password_no_number",
            )

    def get_help_text(self):
        return _(
            "Password mein kam az kam ek harf (a-z) aur ek number (0-9) hona chahiye."
        )
