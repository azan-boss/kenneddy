from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Profile, Address, Role, RiderProfile, phone_validator


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds user profile summary to JWT login response, checks active approval status, and supports email-based login."""

    def validate(self, attrs):
        username_or_email = attrs.get(self.username_field)
        user_candidate = None

        if username_or_email:
            val = username_or_email.strip()
            if "@" in val:
                try:
                    user_candidate = User.objects.get(email__iexact=val)
                    attrs[self.username_field] = user_candidate.username
                except (User.DoesNotExist, User.MultipleObjectsReturned):
                    pass
            else:
                try:
                    user_candidate = User.objects.get(username__iexact=val)
                except (User.DoesNotExist, User.MultipleObjectsReturned):
                    pass

        # Check if user exists and password is correct before super().validate to provide clear approval-pending error
        if user_candidate and user_candidate.check_password(attrs.get("password", "")):
            if not user_candidate.is_active:
                profile = getattr(user_candidate, "profile", None)
                role = profile.role if profile else Role.CUSTOMER
                if role == Role.RIDER:
                    raise serializers.ValidationError({
                        "detail": "Aapki rider application abhi admin approval ke intezar mein hai. Admin review ke baad aap login kar sakenge.",
                        "status": "pending_approval",
                        "role": "rider",
                    })
                elif role == Role.KITCHEN:
                    raise serializers.ValidationError({
                        "detail": "Aapka staff account abhi admin approval ke intezar mein hai.",
                        "status": "pending_approval",
                        "role": "kitchen",
                    })
                else:
                    raise serializers.ValidationError({
                        "detail": "Aapka account abhi active nahi hai. Admin se rabta karein.",
                        "status": "inactive",
                    })

        data = super().validate(attrs)
        profile = getattr(self.user, "profile", None)
        user_role = profile.role if profile else Role.CUSTOMER
        if self.user.is_superuser:
            user_role = Role.ADMIN
        elif self.user.is_staff and user_role != Role.KITCHEN:
            user_role = Role.ADMIN

        data["user"] = {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "role": user_role,
            "is_staff": self.user.is_staff,
            "is_superuser": self.user.is_superuser,
            "full_name": profile.full_name if profile else "",
        }
        return data


class SignupSerializer(serializers.Serializer):
    """
    Validates signup payload — username, email, password, optional full_name, phone, and requested_role.
    Safe role selection: 'customer', 'rider', and 'kitchen' (staff) allowed.
    'admin' accounts cannot be self-registered and return 400.
    """

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    full_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    requested_role = serializers.CharField(max_length=20, required=False, default="customer")

    def validate_username(self, value):
        val = value.strip()
        if User.objects.filter(username__iexact=val).exists():
            raise serializers.ValidationError("Yeh username pehle se le liya gaya hai.")
        return val

    def validate_email(self, value):
        val = value.strip().lower()
        if User.objects.filter(email__iexact=val).exists():
            raise serializers.ValidationError("Is email se account pehle se exist karta hai.")
        return val

    def validate_requested_role(self, value):
        allowed_roles = [Role.CUSTOMER, Role.RIDER, Role.KITCHEN]
        if value not in allowed_roles:
            raise serializers.ValidationError("Admin/Owner role cannot be self-registered. Please contact the administrator.")
        return value

    def create(self, validated_data):
        requested_role = validated_data.get("requested_role", Role.CUSTOMER)
        full_name = validated_data.get("full_name", "").strip()
        phone = validated_data.get("phone", "").strip()

        # Rider and Staff accounts require admin approval before login
        is_active = (requested_role not in [Role.RIDER, Role.KITCHEN])

        with transaction.atomic():
            user = User.objects.create_user(
                username=validated_data["username"],
                email=validated_data["email"],
                password=validated_data["password"],
                is_active=is_active,
            )

            # Update the profile created by post_save signal with the requested role
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = requested_role
            if full_name:
                profile.full_name = full_name
            if phone:
                profile.phone = phone
            profile.save(update_fields=["role", "full_name", "phone"])

        return user



class ProfileSerializer(serializers.ModelSerializer):
    """Read/update the authenticated user's own Profile."""

    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Profile
        fields = [
            "username",
            "email",
            "role",
            "full_name",
            "phone",
            "avatar_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["role", "created_at", "updated_at"]


class AddressSerializer(serializers.ModelSerializer):
    """CRUD operations for user delivery addresses with Pakistan coordinate validation."""

    class Meta:
        model = Address
        fields = [
            "id",
            "label",
            "name",
            "phone",
            "street",
            "area",
            "city",
            "notes",
            "lat",
            "lng",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_phone(self, value):
        phone_validator(value)
        return value

    def validate(self, attrs):
        lat = attrs.get("lat", getattr(self.instance, "lat", None))
        lng = attrs.get("lng", getattr(self.instance, "lng", None))

        if lat is None or lng is None:
            raise serializers.ValidationError("lat and lng are required coordinates.")

        try:
            lat = float(lat)
            lng = float(lng)
        except (TypeError, ValueError):
            raise serializers.ValidationError("lat and lng must be numbers.")

        if not (24.0 <= lat <= 37.5 and 60.0 <= lng <= 77.5):
            raise serializers.ValidationError(
                f"Coordinates ({lat}, {lng}) are outside the expected Pakistan bounding box."
            )

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        is_default = validated_data.get("is_default", False)

        with transaction.atomic():
            if is_default:
                Address.objects.filter(user=user).update(is_default=False)
            elif not Address.objects.filter(user=user).exists():
                # Make the very first address default automatically
                validated_data["is_default"] = True

            address = Address.objects.create(user=user, **validated_data)
        return address

    def update(self, instance, validated_data):
        user = self.context["request"].user
        is_default = validated_data.get("is_default", instance.is_default)

        with transaction.atomic():
            if is_default and not instance.is_default:
                Address.objects.filter(user=user).exclude(pk=instance.pk).update(is_default=False)
            
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
        return instance


class RiderProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    name = serializers.CharField(source="user.profile.full_name", required=False, allow_blank=True)
    phone = serializers.CharField(source="user.profile.phone", required=False, allow_blank=True)

    class Meta:
        model = RiderProfile
        fields = [
            "username",
            "email",
            "name",
            "phone",
            "cnic",
            "vehicle",
            "zone",
            "verified",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "verified"]

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        profile_data = user_data.get("profile", {})
        
        profile = getattr(instance.user, "profile", None)
        if profile and profile_data:
            if "full_name" in profile_data:
                profile.full_name = profile_data["full_name"]
            if "phone" in profile_data:
                profile.phone = profile_data["phone"]
            profile.save(update_fields=["full_name", "phone"])

        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        return instance

