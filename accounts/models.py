import random
import string
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.core.validators import RegexValidator
from django.utils import timezone


class Role(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    KITCHEN  = "kitchen", "Kitchen staff"
    RIDER    = "rider", "Rider"
    ADMIN    = "admin", "Admin"


phone_validator = RegexValidator(
    regex=r'^[0-9+\-\s]{10,}$',
    message="Phone number format ghalat hai."
)


class Profile(models.Model):
    user = models.OneToOneField(User, primary_key=True, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    full_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=20, blank=True, validators=[phone_validator])
    avatar_url = models.URLField(blank=True)
    is_email_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class AddressLabel(models.TextChoices):
    HOME  = "Home", "Home"
    WORK  = "Work", "Work"
    OTHER = "Other", "Other"


class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=20, choices=AddressLabel.choices, default=AddressLabel.HOME)
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, validators=[phone_validator])
    street = models.CharField(max_length=200)
    area = models.CharField(max_length=100)
    city = models.CharField(max_length=80)
    notes = models.CharField(max_length=255, blank=True)
    lat = models.FloatField()
    lng = models.FloatField()
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]
        verbose_name_plural = "Addresses"

    def __str__(self):
        return f"{self.user.username} - {self.label}: {self.street}, {self.city}"


# ─── Rider Fleet Profile (Tier-2 verification) ────────────────────────────────

class RiderProfile(models.Model):
    """
    Extended profile for riders only.
    Two-tier approval:
      Tier 1 — user.is_active=False  → account pending (approve/reject decision)
      Tier 2 — is_active=True but RiderProfile.verified=False → fleet verification pending
    """

    class DutyStatus(models.TextChoices):
        ONLINE  = "online", "Online"
        OFFLINE = "offline", "Offline"
        BUSY    = "busy", "Busy"

    user     = models.OneToOneField(User, primary_key=True, on_delete=models.CASCADE, related_name="rider_profile")
    cnic     = models.CharField(max_length=20, blank=True, help_text="CNIC number (e.g. 35202-1234567-1)")
    vehicle  = models.CharField(max_length=100, blank=True, help_text="Vehicle type + plate, e.g. Honda 125 LHR-123")
    zone     = models.CharField(max_length=80, blank=True, help_text="Delivery zone, e.g. Gulberg")
    verified = models.BooleanField(default=False, help_text="Fleet verification complete (Tier 2)")
    duty_status = models.CharField(
        max_length=10, choices=DutyStatus.choices, default=DutyStatus.OFFLINE,
        help_text="Rider's current duty status (online/offline/busy)",
    )
    lat      = models.FloatField(null=True, blank=True, help_text="Ambient GPS latitude (shared while idle/online)")
    lng      = models.FloatField(null=True, blank=True, help_text="Ambient GPS longitude (shared while idle/online)")
    notes    = models.TextField(blank=True, help_text="Internal admin notes about this rider")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Rider Profile"
        verbose_name_plural = "Rider Profiles"

    def __str__(self):
        return f"{self.user.username} — {'✓ Verified' if self.verified else '⏳ Unverified'}"


# ─── Rejected Application Audit Log ───────────────────────────────────────────

class RejectedApplication(models.Model):
    """
    Lightweight audit record created BEFORE a rider/staff account is deleted on rejection.
    The actual User + Profile + RiderProfile rows are deleted after this record is saved.
    """
    username       = models.CharField(max_length=150)
    email          = models.CharField(max_length=254, blank=True)
    full_name      = models.CharField(max_length=120, blank=True)
    phone          = models.CharField(max_length=20, blank=True)
    role           = models.CharField(max_length=20)
    cnic           = models.CharField(max_length=20, blank=True)
    vehicle        = models.CharField(max_length=100, blank=True)
    reason         = models.TextField(blank=True)
    rejected_by    = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="rejections_made"
    )
    rejected_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-rejected_at"]
        verbose_name = "Rejected Application"
        verbose_name_plural = "Rejected Applications"

    def __str__(self):
        return f"{self.username} ({self.role}) rejected at {self.rejected_at:%Y-%m-%d %H:%M}"


# ─── Email OTP Verification ────────────────────────────────────────────────────

OTP_EXPIRY_MINUTES = 10


def _generate_otp():
    return "".join(random.choices(string.digits, k=6))


class EmailOTP(models.Model):
    """
    Stores a 6-digit one-time password tied to a user + purpose.
    Expires in OTP_EXPIRY_MINUTES. Old codes for the same user+purpose
    are deleted when a new one is generated.
    """

    class Purpose(models.TextChoices):
        EMAIL_VERIFY = "email_verify", "Email Verification"
        PASSWORD_RESET = "password_reset", "Password Reset"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="email_otps"
    )
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    code = models.CharField(max_length=6, default=_generate_otp)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = "Email OTP"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @classmethod
    def create_for(cls, user, purpose):
        """Delete old codes then create a fresh one. Returns the new EmailOTP."""
        cls.objects.filter(user=user, purpose=purpose).delete()
        return cls.objects.create(user=user, purpose=purpose, expires_at=timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES))

    def __str__(self):
        return f"{self.user.username} [{self.purpose}] {self.code} (expires {self.expires_at:%H:%M})"