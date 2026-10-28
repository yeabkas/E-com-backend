from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import authenticate
from .models import User, Address


class RegisterSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['id', 'email', 'password', 'first_name', 'last_name', 'role']
        read_only_fields = ['id']

    def validate_role(self, value):
        if value not in (User.Role.CUSTOMER, User.Role.SELLER):
            raise serializers.ValidationError('Role must be CUSTOMER or SELLER.')
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_email(self, value):
        return value.lower()

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    """Serializer for user login."""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        raw_email = (data.get('email') or '').strip()
        email = raw_email.lower()
        password = data.get('password', '')

        user = authenticate(username=raw_email, password=password)
        if user is None:
            user = authenticate(username=email, password=password)
        if user is None:
            from apps.users.models import User
            matched = User.objects.filter(email__iexact=raw_email).first()
            if matched and matched.check_password(password):
                user = matched

        if user is None:
            raise serializers.ValidationError('Invalid email or password.')

        if not user.is_active:
            raise serializers.ValidationError('This account is not active.')

        data['user'] = user
        return data


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user profile data."""
    full_name = serializers.ReadOnlyField()
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'phone', 'profile_picture', 'is_verified', 'created_at',
        ]
        read_only_fields = ['id', 'email', 'role', 'is_verified', 'created_at']

    def get_profile_picture(self, obj):
        if getattr(obj, 'profile_picture_data', None):
            return obj.profile_picture_data
        if obj.profile_picture:
            try:
                url = obj.profile_picture.url
                request = self.context.get('request')
                if request and not url.startswith('http'):
                    return request.build_absolute_uri(url)
                return url
            except Exception:
                return str(obj.profile_picture)
        return None


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone', 'profile_picture', 'profile_picture_data']


class AddressSerializer(serializers.ModelSerializer):
    """Serializer for user addresses."""

    class Meta:
        model = Address
        fields = [
            'id', 'label', 'street_line_1', 'street_line_2',
            'city', 'state_province', 'postal_code', 'country_code',
            'is_default', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, data):
        user = self.context['request'].user
        # Enforce max 5 addresses per user (only on create)
        if not self.instance:
            if Address.objects.filter(user=user).count() >= 5:
                raise serializers.ValidationError('Maximum of 5 addresses allowed.')
        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class AdminUserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name', 'role',
            'is_verified', 'is_suspended', 'is_active', 'is_staff',
            'last_login_at', 'created_at',
        ]
        read_only_fields = ['id', 'email', 'full_name', 'last_login_at', 'created_at']
