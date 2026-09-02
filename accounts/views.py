from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .email_service import send_otp_email, send_password_reset_email
from .models import Address, EmailOTP, EmailVerification, Profile, Role, RiderProfile, RejectedApplication
from .serializers import AddressSerializer, ProfileSerializer, SignupSerializer, RiderProfileSerializer


class IsAdminUserOrRole(IsAuthenticated):
    """Allows access to staff, superusers, or users with Profile.role == 'admin'."""
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.user.is_superuser or request.user.is_staff:
            return True
        try:
            return request.user.profile.role == Role.ADMIN
        except Exception:
            return False


# ─── Auth / Signup ─────────────────────────────────────────────────────────────

class SignupView(APIView):
    """
    POST /api/auth/signup/
    Public endpoint — creates a User + Profile.
    If requested_role == 'rider' or 'kitchen', user is created with is_active=False
    pending admin approval.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            if not user.is_active:
                role = getattr(user.profile, "role", Role.RIDER)
                role_label = "rider" if role == Role.RIDER else "staff"
                return Response(
                    {
                        "detail": (
                            f"Aapka {role_label} account register ho gaya hai "
                            f"aur admin approval ke intezar mein hai."
                        ),
                        "username": user.username,
                        "role": role,
                        "status": "pending_approval",
                    },
                    status=status.HTTP_201_CREATED,
                )
            return Response(
                {
                    "detail": "Account ban gaya! Ab login karein.",
                    "username": user.username,
                    "role": getattr(user.profile, "role", Role.CUSTOMER),
                    "status": "active",
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Profile ───────────────────────────────────────────────────────────────────

class ProfileView(APIView):
    """
    GET  /api/profile/  — returns the authenticated user's own profile.
    PATCH /api/profile/ — partial-updates the authenticated user's own profile.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = ProfileSerializer(request.user.profile)
        return Response(serializer.data)

    def patch(self, request):
        serializer = ProfileSerializer(
            request.user.profile,
            data=request.data,
            partial=True,
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Addresses ─────────────────────────────────────────────────────────────────

class AddressListCreateView(APIView):
    """
    GET  /api/addresses/ — returns the authenticated user's saved addresses.
    POST /api/addresses/ — creates a new delivery address for the user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        addresses = Address.objects.filter(user=request.user)
        serializer = AddressSerializer(addresses, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = AddressSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            address = serializer.save()
            return Response(AddressSerializer(address).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AddressDetailView(APIView):
    """
    GET    /api/addresses/{id}/ — get a single address.
    PATCH  /api/addresses/{id}/ — partial update of user's own address.
    DELETE /api/addresses/{id}/ — delete user's own address.
    """
    permission_classes = [IsAuthenticated]

    def _get_address(self, user, pk):
        try:
            return Address.objects.get(pk=pk, user=user)
        except Address.DoesNotExist:
            return None

    def get(self, request, pk):
        address = self._get_address(request.user, pk)
        if address is None:
            return Response({"detail": "Address nahi mila."}, status=status.HTTP_404_NOT_FOUND)
        return Response(AddressSerializer(address).data)

    def patch(self, request, pk):
        address = self._get_address(request.user, pk)
        if address is None:
            return Response({"detail": "Address nahi mila."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AddressSerializer(address, data=request.data, partial=True, context={"request": request})
        if serializer.is_valid():
            updated = serializer.save()
            return Response(AddressSerializer(updated).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        address = self._get_address(request.user, pk)
        if address is None:
            return Response({"detail": "Address nahi mila."}, status=status.HTTP_404_NOT_FOUND)
        was_default = address.is_default
        address.delete()
        if was_default:
            first = Address.objects.filter(user=request.user).first()
            if first:
                first.is_default = True
                first.save(update_fields=["is_default"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AddressSetDefaultView(APIView):
    """
    POST /api/addresses/{id}/set-default/
    Makes the given address the user's default delivery address.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            target = Address.objects.get(pk=pk, user=request.user)
        except Address.DoesNotExist:
            return Response({"detail": "Address nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            Address.objects.filter(user=request.user).update(is_default=False)
            target.is_default = True
            target.save(update_fields=["is_default"])

        return Response(AddressSerializer(target).data)


# ─── Admin: Rider / Staff Approval Workflow ────────────────────────────────────

class PendingApprovalsView(APIView):
    """
    GET /api/admin/pending-approvals/
    Returns two distinctly-typed lists (admin-only):
      - tier1: is_active=False accounts awaiting initial approve/reject decision
      - tier2: is_active=True riders with RiderProfile.verified=False awaiting fleet check
    """
    permission_classes = [IsAdminUserOrRole]

    def get(self, request):
        # Tier 1 — account pending (is_active=False, any role)
        tier1_qs = (
            User.objects
            .select_related("profile")
            .filter(is_active=False)
            .exclude(is_superuser=True)
        )
        tier1 = [
            {
                "user_id":   u.id,
                "username":  u.username,
                "email":     u.email,
                "full_name": getattr(getattr(u, "profile", None), "full_name", ""),
                "phone":     getattr(getattr(u, "profile", None), "phone", ""),
                "role":      getattr(getattr(u, "profile", None), "role", ""),
                "tier":      1,
                "joined_at": u.date_joined.isoformat(),
            }
            for u in tier1_qs
        ]

        # Tier 2 — fleet verification pending (active riders with verified=False)
        tier2_qs = (
            RiderProfile.objects
            .select_related("user", "user__profile")
            .filter(verified=False, user__is_active=True)
        )
        tier2 = [
            {
                "user_id":   rp.user.id,
                "username":  rp.user.username,
                "email":     rp.user.email,
                "full_name": getattr(getattr(rp.user, "profile", None), "full_name", ""),
                "phone":     getattr(getattr(rp.user, "profile", None), "phone", ""),
                "role":      "rider",
                "cnic":      rp.cnic,
                "vehicle":   rp.vehicle,
                "zone":      rp.zone,
                "tier":      2,
                "joined_at": rp.user.date_joined.isoformat(),
            }
            for rp in tier2_qs
        ]

        return Response({"tier1": tier1, "tier2": tier2})


class ApproveRiderView(APIView):
    """
    POST /api/admin/riders/{user_id}/approve/
    Tier 1 — activates an account pending initial approval.
    Works for riders AND kitchen staff.
    """
    permission_classes = [IsAdminUserOrRole]

    def post(self, request, user_id):
        try:
            target = User.objects.select_related("profile").get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        target.is_active = True
        target.save(update_fields=["is_active"])

        return Response({
            "detail": f"'{target.username}' approved and activated.",
            "user_id": target.id,
            "username": target.username,
            "is_active": True,
        })


class RejectRiderView(APIView):
    """
    POST /api/admin/riders/{user_id}/reject/
    Logs a RejectedApplication audit record then FULLY DELETES
    the User + Profile + RiderProfile rows.
    Body (optional JSON): { "reason": "..." }
    """
    permission_classes = [IsAdminUserOrRole]

    def post(self, request, user_id):
        try:
            target = User.objects.select_related("profile").get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        if target.is_superuser or target == request.user:
            return Response(
                {"detail": "Cannot reject a superuser or yourself."},
                status=status.HTTP_403_FORBIDDEN,
            )

        profile = getattr(target, "profile", None)
        rp      = getattr(target, "rider_profile", None)
        reason  = request.data.get("reason", "Rejected via API")

        with transaction.atomic():
            RejectedApplication.objects.create(
                username=target.username,
                email=target.email,
                full_name=getattr(profile, "full_name", ""),
                phone=getattr(profile, "phone", ""),
                role=getattr(profile, "role", ""),
                cnic=getattr(rp, "cnic", ""),
                vehicle=getattr(rp, "vehicle", ""),
                reason=reason,
                rejected_by=request.user,
            )
            username_snapshot = target.username
            target.delete()

        return Response({
            "detail": (
                f"Application for '{username_snapshot}' rejected. "
                f"Audit log saved. Account permanently deleted."
            ),
            "username": username_snapshot,
        }, status=status.HTTP_200_OK)


class FleetVerifyRiderView(APIView):
    """
    POST /api/admin/riders/{user_id}/fleet-verify/
    Tier 2 — marks RiderProfile.verified=True for an already-active rider.
    """
    permission_classes = [IsAdminUserOrRole]

    def post(self, request, user_id):
        try:
            target = User.objects.select_related("profile").get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        role = getattr(getattr(target, "profile", None), "role", "")
        if role != Role.RIDER:
            return Response(
                {"detail": f"'{target.username}' is not a rider."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not target.is_active:
            return Response(
                {"detail": "Rider account is still Tier 1 pending. Approve account activation first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rp, _ = RiderProfile.objects.get_or_create(user=target)
        rp.verified = True
        rp.save(update_fields=["verified"])

        return Response({
            "detail": f"Rider '{target.username}' fleet-verified (Tier 2 complete).",
            "user_id": target.id,
            "username": target.username,
            "verified": True,
        })


class RiderProfileView(APIView):
    """
    GET   /api/rider/profile/ — returns the authenticated rider's own full profile.
    PATCH /api/rider/profile/ — updates CNIC, vehicle/bike, zone, name, phone in database.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rp, _ = RiderProfile.objects.get_or_create(user=request.user)
        serializer = RiderProfileSerializer(rp)
        return Response(serializer.data)

    def patch(self, request):
        rp, _ = RiderProfile.objects.get_or_create(user=request.user)
        serializer = RiderProfileSerializer(rp, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RiderDutyStatusView(APIView):
    """
    POST /api/rider/duty-status/
    Rider-only. Updates the rider's own duty_status on their RiderProfile.
    Body: {"duty_status": "online" | "offline" | "busy"}
    Only for the currently logged-in rider — not for admin changing someone else's status.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        duty_status = request.data.get("duty_status")
        valid = [c[0] for c in RiderProfile.DutyStatus.choices]
        if duty_status not in valid:
            return Response(
                {"detail": f"duty_status must be one of: {', '.join(valid)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rp, _ = RiderProfile.objects.get_or_create(user=request.user)
        rp.duty_status = duty_status
        rp.save(update_fields=["duty_status", "updated_at"])

        return Response({
            "detail": f"Duty status updated to {duty_status}.",
            "duty_status": duty_status,
        })


class RiderLocationShareView(APIView):
    """
    POST /api/rider/location-share/
    Rider-only. Updates the ambient GPS location on the rider's RiderProfile.
    This is for "ready and sharing location while idle/online" — NOT for mid-delivery
    GPS pushes (those go to POST /api/orders/{id}/rider-location/).
    Body: {"lat": float, "lng": float}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        lat = request.data.get("lat")
        lng = request.data.get("lng")
        if lat is None or lng is None:
            return Response(
                {"detail": "lat aur lng dono required hain."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            lat = float(lat)
            lng = float(lng)
        except (TypeError, ValueError):
            return Response(
                {"detail": "lat aur lng numbers hone chahiye."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rp, _ = RiderProfile.objects.get_or_create(user=request.user)
        rp.lat = lat
        rp.lng = lng
        rp.save(update_fields=["lat", "lng", "updated_at"])

        # Push to active assigned orders and broadcast Channels update to customers/admin
        try:
            from orders.models import Order
            from orders.views import _broadcast_order_update
            active_orders = Order.objects.filter(
                rider_user=request.user,
                status__in=[Order.STATUS_CONFIRMED, Order.STATUS_KITCHEN, Order.STATUS_PACKED, Order.STATUS_ONWAY]
            )
            for order in active_orders:
                order.rider_lat = lat
                order.rider_lng = lng
                order.save(update_fields=["rider_lat", "rider_lng", "updated_at"])
                try:
                    _broadcast_order_update(order)
                except Exception:
                    pass
        except Exception:
            pass

        return Response({
            "detail": "Location share ho gai.",
            "lat": rp.lat,
            "lng": rp.lng,
        })


class AdminRidersView(APIView):
    """
    GET  /api/admin/riders/ — returns all active/verified riders from database with workload stats.
    POST /api/admin/riders/ — creates or updates a rider user + profile + rider_profile in DB.
    """
    permission_classes = [IsAdminUserOrRole]

    def get(self, request):
        from orders.models import Order
        riders = User.objects.filter(
            profile__role=Role.RIDER, is_active=True
        ).select_related("profile", "rider_profile")

        result = []
        for u in riders:
            rp = getattr(u, "rider_profile", None)
            prof = getattr(u, "profile", None)
            
            # Compute live workload
            active_count = Order.objects.filter(
                rider_user=u,
                status__in=[Order.STATUS_PACKED, Order.STATUS_ONWAY]
            ).count()
            delivered_count = Order.objects.filter(
                rider_user=u,
                status=Order.STATUS_DELIVERED
            ).count()
            revenue = sum(
                o.total for o in Order.objects.filter(rider_user=u, status=Order.STATUS_DELIVERED)
            )

            result.append({
                "id": str(u.id),
                "name": prof.full_name if prof and prof.full_name else u.username,
                "phone": prof.phone if prof and prof.phone else "",
                "email": u.email or "",
                "bike": rp.vehicle if rp and rp.vehicle else "Honda CD-70",
                "plate": "",
                "cnic": rp.cnic if rp else "",
                "zone": rp.zone if rp and rp.zone else "Lahore",
                "status": rp.duty_status if rp and rp.duty_status else ("online" if active_count > 0 else "offline"),
                "verified": rp.verified if rp else False,
                "rating": 5,
                "deliveries": delivered_count,
                "active": active_count,
                "revenue": float(revenue),
                "joinedAt": int(u.date_joined.timestamp() * 1000),
                "location": {
                    "lat": rp.lat,
                    "lng": rp.lng,
                    "sharing": rp.lat is not None and rp.lng is not None,
                } if rp else None,
            })

        return Response(result)

    def post(self, request):
        name = request.data.get("name", "").strip()
        phone = request.data.get("phone", "").strip()
        email = request.data.get("email", "").strip()
        bike = request.data.get("bike", "").strip()
        plate = request.data.get("plate", "").strip()
        cnic = request.data.get("cnic", "").strip()
        zone = request.data.get("zone", "Lahore").strip()
        rider_id = request.data.get("id")

        if rider_id:
            try:
                user = User.objects.select_related("profile", "rider_profile").get(pk=rider_id)
                prof = getattr(user, "profile", None)
                if prof:
                    if name: prof.full_name = name
                    if phone: prof.phone = phone
                    prof.save(update_fields=["full_name", "phone"])
                rp, _ = RiderProfile.objects.get_or_create(user=user)
                if cnic: rp.cnic = cnic
                if bike or plate: rp.vehicle = f"{bike} {plate}".strip()
                if zone: rp.zone = zone
                rp.save()
                return Response({"detail": "Rider updated", "id": str(user.id)})
            except User.DoesNotExist:
                return Response({"detail": "Rider not found"}, status=status.HTTP_404_NOT_FOUND)

        # Create new rider
        import re, random
        from django.utils import timezone
        clean = re.sub(r"[^a-z0-9_]", "", name.lower().replace(" ", "_")) if name else f"rider_{int(timezone.now().timestamp())}"
        random_suffix = random.randint(100, 999)
        username = f"{clean}_{random_suffix}" if User.objects.filter(username=clean).exists() else clean

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email or f"{username}@kmg.pk",
                password="Rider@1234",
                is_active=True,
            )
            prof, _ = Profile.objects.get_or_create(user=user)
            prof.role = Role.RIDER
            prof.full_name = name
            prof.phone = phone
            prof.save()

            RiderProfile.objects.create(
                user=user,
                cnic=cnic,
                vehicle=f"{bike} {plate}".strip(),
                zone=zone or "Lahore",
                verified=True,
            )

        return Response({"detail": "Rider created", "id": str(user.id)}, status=status.HTTP_201_CREATED)


# ─── JWT Logout (blacklist refresh token) ─────────────────────────────────────

class LogoutView(APIView):
    """
    POST /api/auth/logout/
    Blacklists the submitted refresh token (requires token_blacklist in INSTALLED_APPS).
    Frontend sends: {"refresh": "<refresh_token>"}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "refresh token required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from rest_framework_simplejwt.tokens import RefreshToken
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"detail": "Logged out."}, status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            # Token already expired/invalid — still treat as logged out
            return Response({"detail": "Logged out."}, status=status.HTTP_205_RESET_CONTENT)


# ─── Email OTP — Send & Verify ─────────────────────────────────────────────────

class SendEmailOTPView(APIView):
    """
    POST /api/auth/send-otp/
    Sends a 6-digit OTP to the authenticated user's email for email verification.
    Also used after signup to trigger the first verification code.
    """
    permission_classes = [IsAuthenticated]
    throttle_scope = "otp"

    def post(self, request):
        user = request.user
        otp = EmailOTP.create_for(user, EmailOTP.Purpose.EMAIL_VERIFY)
        print(f"\n[EMAIL OTP VERIFICATION] Generated OTP for '{user.username}' ({user.email}): {otp.code}")
        sent = send_otp_email(
            to_email=user.email,
            otp_code=otp.code,
            username=user.username,
        )
        return Response({
            "detail": f"OTP bheja gaya: {user.email}",
            "email_sent": sent,
        })


class VerifyEmailOTPView(APIView):
    """
    POST /api/auth/verify-otp/
    Verifies the 6-digit OTP and marks the user's email as verified.
    Body: {"code": "123456"}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = str(request.data.get("code", "")).strip()
        if not code:
            return Response({"detail": "OTP code required."}, status=status.HTTP_400_BAD_REQUEST)

        otp = (
            EmailOTP.objects
            .filter(user=request.user, purpose=EmailOTP.Purpose.EMAIL_VERIFY)
            .order_by("-created_at")
            .first()
        )

        if not otp or otp.is_expired:
            return Response(
                {"detail": "OTP expire ho gaya ya exist nahi karta. Dobara bhejein."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp.code != code:
            return Response({"detail": "Ghalat OTP code."}, status=status.HTTP_400_BAD_REQUEST)

        # Mark email verified in separate EmailVerification model + delete OTP
        try:
            ev, _ = EmailVerification.objects.get_or_create(user=request.user)
            ev.is_verified = True
            ev.verified_at = timezone.now()
            ev.save(update_fields=["is_verified", "verified_at", "updated_at"])
        except Exception:
            pass

        otp.delete()

        return Response({"detail": "Email verify ho gaya!", "is_email_verified": True})


# ─── Password Reset (forgot password — public) ─────────────────────────────────

class PasswordResetRequestView(APIView):
    """
    POST /api/auth/password-reset/
    Public. Sends a 6-digit OTP to the email if it exists.
    Always returns 204 — never leaks whether an email exists.
    Body: {"email": "user@example.com"}
    """
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        # Always return 204 (don't reveal if email exists)
        try:
            user = User.objects.get(email__iexact=email, is_active=True)
            otp = EmailOTP.create_for(user, EmailOTP.Purpose.PASSWORD_RESET)
            print(f"\n[PASSWORD RESET] Generated OTP for user '{user.username}' ({user.email}): {otp.code}")
            send_password_reset_email(
                to_email=user.email,
                reset_link=f"{settings.FRONTEND_URL}/reset-password?email={user.email}&code={otp.code}",
                otp_code=otp.code,
                username=user.username,
            )
        except User.DoesNotExist:
            print(f"\n[PASSWORD RESET] Email '{email}' is NOT registered in database. (Returning 204 for security privacy)")

        return Response(
            {"detail": "Agar yeh email registered hai, aapko ek OTP mila hoga."},
            status=status.HTTP_204_NO_CONTENT,
        )


class PasswordResetConfirmView(APIView):
    """
    POST /api/auth/password-reset-confirm/
    Public. Verifies OTP and resets the password.
    Body: {"email": "...", "otp": "123456", "new_password": "..."}
    """
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        otp_code = str(request.data.get("code") or request.data.get("otp") or "").strip()
        new_password = request.data.get("new_password", "")

        if not all([email, otp_code, new_password]):
            return Response(
                {"detail": "email, code/otp, aur new_password required hain."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist:
            return Response({"detail": "Ghalat email ya OTP."}, status=status.HTTP_400_BAD_REQUEST)

        otp = (
            EmailOTP.objects
            .filter(user=user, purpose=EmailOTP.Purpose.PASSWORD_RESET)
            .order_by("-created_at")
            .first()
        )

        if not otp or otp.is_expired or otp.code != otp_code:
            return Response(
                {"detail": "OTP ghalat ya expire ho gaya hai."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate new password against all validators
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()
        otp.delete()

        return Response({"detail": "Password reset ho gaya! Ab login karein."})


# ─── Change Password (signed-in user) ─────────────────────────────────────────

class ChangePasswordView(APIView):
    """
    POST /api/profile/change-password/
    Requires authentication.
    Body: {"current_password": "...", "new_password": "..."}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current = request.data.get("current_password", "")
        new_pass = request.data.get("new_password", "")

        if not current or not new_pass:
            return Response(
                {"detail": "current_password aur new_password dono required hain."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.check_password(current):
            return Response(
                {"detail": "Purana password ghalat hai."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(new_pass, user=request.user)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(new_pass)
        request.user.save()

        return Response({"detail": "Password successfully change ho gaya!"})
