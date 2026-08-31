from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.contrib import messages

from .models import Profile, Address, Role, RiderProfile, RejectedApplication


# ─── Inlines ──────────────────────────────────────────────────────────────────

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = "Caddy Profile Details"
    fields = ("role", "full_name", "phone", "avatar_url")


class RiderProfileInline(admin.StackedInline):
    model = RiderProfile
    can_delete = False
    verbose_name_plural = "🛵 Rider Fleet Details"
    fields = ("cnic", "vehicle", "zone", "duty_status", "verified", "lat", "lng", "notes")
    extra = 0

    def has_add_permission(self, request, obj=None):
        # Only show inline if user is a rider
        if obj is None:
            return False
        try:
            return obj.profile.role == Role.RIDER
        except Profile.DoesNotExist:
            return False


# ─── CustomUserAdmin ───────────────────────────────────────────────────────────

admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    inlines = (ProfileInline, RiderProfileInline)
    list_display = (
        "username",
        "email",
        "role_badge",
        "full_name_display",
        "phone_display",
        "approval_state_badge",
        "is_staff",
        "date_joined",
    )
    list_filter = ("profile__role", "is_active", "is_staff", "date_joined")
    search_fields = ("username", "email", "profile__full_name", "profile__phone")
    actions = [
        "approve_and_activate",
        "fleet_verify_riders",
        "reject_and_delete",
        "deactivate_accounts",
    ]

    # ── Display helpers ────────────────────────────────────────────────────────

    @admin.display(description="Role")
    def role_badge(self, obj):
        role = getattr(getattr(obj, "profile", None), "role", "customer")
        color_map = {
            Role.CUSTOMER: "caddy-role-customer",
            Role.RIDER:    "caddy-role-rider",
            Role.KITCHEN:  "caddy-role-kitchen",
            Role.ADMIN:    "caddy-role-admin",
        }
        icons = {
            Role.CUSTOMER: "👤",
            Role.RIDER:    "🛵",
            Role.KITCHEN:  "👨‍🍳",
            Role.ADMIN:    "👑",
        }
        return format_html(
            '<span class="{}">{} {}</span>',
            color_map.get(role, "caddy-role-customer"),
            icons.get(role, "👤"),
            role.capitalize(),
        )

    @admin.display(description="Full Name")
    def full_name_display(self, obj):
        return getattr(getattr(obj, "profile", None), "full_name", "") or "—"

    @admin.display(description="Phone")
    def phone_display(self, obj):
        return getattr(getattr(obj, "profile", None), "phone", "") or "—"

    @admin.display(description="Approval State")
    def approval_state_badge(self, obj):
        try:
            role = obj.profile.role
        except Profile.DoesNotExist:
            role = Role.CUSTOMER

        # Tier 1 — account pending (is_active=False)
        if not obj.is_active:
            return mark_safe(
                '<span class="caddy-pill caddy-pill-pending" title="Tier 1 — Account not yet activated">'
                '⏳ Account Pending</span>'
            )

        # Tier 2 — rider fleet verification (is_active=True, RiderProfile.verified=False)
        if role == Role.RIDER:
            try:
                rp = obj.rider_profile
            except RiderProfile.DoesNotExist:
                return mark_safe(
                    '<span class="caddy-pill caddy-pill-kitchen" title="No rider profile yet">'
                    '🔍 No Fleet Profile</span>'
                )
            if not rp.verified:
                return mark_safe(
                    '<span class="caddy-pill caddy-pill-kitchen" title="Tier 2 — Account active, awaiting fleet verification">'
                    '🔍 Fleet Pending</span>'
                )
            return mark_safe('<span class="caddy-pill caddy-pill-onway">🛵 Fleet Verified</span>')

        # Active non-rider
        return mark_safe('<span class="caddy-pill caddy-pill-confirmed">✓ Active</span>')

    # ── Actions ───────────────────────────────────────────────────────────────

    @admin.action(description="✅ Approve & Activate Selected (Tier 1)")
    def approve_and_activate(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} account(s) approved and activated (Tier 1).", messages.SUCCESS)

    @admin.action(description="🔍 Mark Fleet Verified (Tier 2 — Riders Only)")
    def fleet_verify_riders(self, request, queryset):
        verified_count = 0
        skipped = 0
        for user in queryset:
            role = getattr(getattr(user, "profile", None), "role", "")
            if role == Role.RIDER and user.is_active:
                rp, _ = RiderProfile.objects.get_or_create(user=user)
                rp.verified = True
                rp.save()
                verified_count += 1
            else:
                skipped += 1
        msg = f"{verified_count} rider(s) fleet-verified."
        if skipped:
            msg += f" {skipped} skipped (not an active rider)."
        self.message_user(request, msg, messages.SUCCESS)

    @admin.action(description="❌ Reject & Delete Selected Applications")
    def reject_and_delete(self, request, queryset):
        deleted_count = 0
        for user in queryset:
            # Do not allow deleting superusers or the request user
            if user.is_superuser or user == request.user:
                self.message_user(
                    request,
                    f"Cannot reject superuser or yourself: {user.username}",
                    messages.WARNING,
                )
                continue

            try:
                profile = user.profile
            except Profile.DoesNotExist:
                profile = None
            try:
                rp = user.rider_profile
            except RiderProfile.DoesNotExist:
                rp = None

            # Log audit record BEFORE deleting
            RejectedApplication.objects.create(
                username=user.username,
                email=user.email,
                full_name=getattr(profile, "full_name", "") or "",
                phone=getattr(profile, "phone", "") or "",
                role=getattr(profile, "role", "") or "",
                cnic=getattr(rp, "cnic", "") or "",
                vehicle=getattr(rp, "vehicle", "") or "",
                reason="Rejected via admin action",
                rejected_by=request.user,
            )
            user.delete()
            deleted_count += 1

        self.message_user(
            request,
            f"{deleted_count} application(s) rejected, audit log saved, and accounts deleted.",
            messages.SUCCESS,
        )

    @admin.action(description="⏸️ Deactivate Selected Accounts")
    def deactivate_accounts(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} account(s) deactivated.", messages.SUCCESS)


# ─── ProfileAdmin ──────────────────────────────────────────────────────────────

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user_link", "role_badge", "full_name", "phone", "avatar_preview", "addresses_count", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("user__username", "user__email", "full_name", "phone")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="User")
    def user_link(self, obj):
        return obj.user.username

    @admin.display(description="Role")
    def role_badge(self, obj):
        color_map = {
            Role.CUSTOMER: "caddy-role-customer",
            Role.RIDER:    "caddy-role-rider",
            Role.KITCHEN:  "caddy-role-kitchen",
            Role.ADMIN:    "caddy-role-admin",
        }
        icons = {
            Role.CUSTOMER: "👤",
            Role.RIDER:    "🛵",
            Role.KITCHEN:  "👨‍🍳",
            Role.ADMIN:    "👑",
        }
        return format_html(
            '<span class="{}">{} {}</span>',
            color_map.get(obj.role, "caddy-role-customer"),
            icons.get(obj.role, "👤"),
            obj.role.capitalize(),
        )

    @admin.display(description="Avatar")
    def avatar_preview(self, obj):
        if obj.avatar_url:
            return format_html('<img src="{}" class="caddy-thumb" alt="Avatar" />', obj.avatar_url)
        return "—"

    @admin.display(description="Saved Addresses")
    def addresses_count(self, obj):
        return obj.user.addresses.count()


# ─── RiderProfileAdmin ────────────────────────────────────────────────────────

@admin.register(RiderProfile)
class RiderProfileAdmin(admin.ModelAdmin):
    list_display = (
        "rider_name",
        "username_display",
        "cnic",
        "vehicle",
        "zone",
        "duty_status",
        "verified_badge",
        "created_at",
    )
    list_filter = ("verified", "duty_status", "zone")
    search_fields = ("user__username", "user__profile__full_name", "cnic", "vehicle", "zone")
    readonly_fields = ("created_at", "updated_at")
    actions = ["mark_fleet_verified", "mark_fleet_unverified"]

    @admin.display(description="Rider Name")
    def rider_name(self, obj):
        return getattr(obj.user, "profile", None) and obj.user.profile.full_name or obj.user.username

    @admin.display(description="Username")
    def username_display(self, obj):
        return obj.user.username

    @admin.display(description="Fleet Status")
    def verified_badge(self, obj):
        if obj.verified:
            return mark_safe('<span class="caddy-pill caddy-pill-onway">🛵 Fleet Verified</span>')
        return mark_safe('<span class="caddy-pill caddy-pill-kitchen">🔍 Fleet Pending</span>')

    @admin.action(description="🛵 Mark Fleet Verified")
    def mark_fleet_verified(self, request, queryset):
        updated = queryset.update(verified=True)
        self.message_user(request, f"{updated} rider(s) fleet-verified.", messages.SUCCESS)

    @admin.action(description="🔒 Remove Fleet Verification")
    def mark_fleet_unverified(self, request, queryset):
        updated = queryset.update(verified=False)
        self.message_user(request, f"{updated} rider(s) fleet verification removed.", messages.SUCCESS)


# ─── RejectedApplicationAdmin ─────────────────────────────────────────────────

@admin.register(RejectedApplication)
class RejectedApplicationAdmin(admin.ModelAdmin):
    list_display  = ("username", "role_badge", "full_name", "phone", "cnic", "rejected_by", "rejected_at", "reason_short")
    list_filter   = ("role", "rejected_at")
    search_fields = ("username", "full_name", "phone", "cnic")
    readonly_fields = (
        "username", "email", "full_name", "phone", "role",
        "cnic", "vehicle", "reason", "rejected_by", "rejected_at",
    )

    def has_add_permission(self, request):
        return False  # Audit log — no manual creation

    def has_change_permission(self, request, obj=None):
        return False  # Read-only audit

    @admin.display(description="Role")
    def role_badge(self, obj):
        icons = {"rider": "🛵", "kitchen": "👨‍🍳", "customer": "👤", "admin": "👑"}
        return format_html('<span>{} {}</span>', icons.get(obj.role, "👤"), obj.role.capitalize())

    @admin.display(description="Reason (short)")
    def reason_short(self, obj):
        return (obj.reason[:60] + "…") if len(obj.reason) > 60 else obj.reason or "—"


# ─── AddressAdmin ──────────────────────────────────────────────────────────────

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("user", "label_badge", "name", "phone", "full_address", "coords_badge", "is_default_badge", "created_at")
    list_filter  = ("label", "city", "is_default")
    search_fields = ("user__username", "name", "phone", "street", "area", "city")

    @admin.display(description="Label")
    def label_badge(self, obj):
        icons = {"Home": "🏠", "Work": "🏢", "Other": "📍"}
        return format_html('<span>{} {}</span>', icons.get(obj.label, "📍"), obj.label)

    @admin.display(description="Full Address")
    def full_address(self, obj):
        return f"{obj.street}, {obj.area}, {obj.city}"

    @admin.display(description="Coordinates")
    def coords_badge(self, obj):
        return format_html(
            '<code style="background:#f1f3f5;padding:2px 6px;border-radius:4px;font-size:0.75rem;">{}, {}</code>',
            obj.lat, obj.lng
        )

    @admin.display(description="Default")
    def is_default_badge(self, obj):
        if obj.is_default:
            return mark_safe('<span class="caddy-pill caddy-pill-confirmed">★ Default</span>')
        return "—"