from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.utils import timezone
from django.conf import settings as django_settings
from .models import User, Address
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserSerializer,
    UserUpdateSerializer,
    AddressSerializer,
)


def _set_refresh_cookie(response, refresh_token: str):
    response.set_cookie(
        django_settings.AUTH_REFRESH_COOKIE_NAME,
        refresh_token,
        httponly=True,
        secure=django_settings.AUTH_COOKIE_SECURE,
        samesite=django_settings.AUTH_COOKIE_SAMESITE,
        path='/api/v1/auth/',
    )


def _clear_refresh_cookie(response):
    response.delete_cookie(
        django_settings.AUTH_REFRESH_COOKIE_NAME,
        path='/api/v1/auth/',
        samesite=django_settings.AUTH_COOKIE_SAMESITE,
    )


class RegisterView(generics.CreateAPIView):
    """POST /api/v1/auth/register/ - Create a new user account."""
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        try:
            from .tokens import send_verification_email
            send_verification_email(user)
        except Exception:
            pass
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED
        )


class LoginView(APIView):
    """POST /api/v1/auth/login/ - Authenticate and return JWT tokens."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        # Update last login timestamp
        user.last_login_at = timezone.now()
        user.save(update_fields=['last_login_at'])

        # Generate tokens
        refresh = RefreshToken.for_user(user)

        response = Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'expires_in': 3600,
            'user': UserSerializer(user).data,
        })
        _set_refresh_cookie(response, str(refresh))
        return response


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ - Blacklist the refresh token."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh') or request.COOKIES.get(
                django_settings.AUTH_REFRESH_COOKIE_NAME
            )
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except Exception:
            pass
        response = Response({'detail': 'Logged out successfully.'}, status=status.HTTP_200_OK)
        _clear_refresh_cookie(response)
        return response


class PasswordResetRequestView(APIView):
    """POST /auth/password-reset/ {email} — always returns 200 for privacy."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if email:
            try:
                user = User.objects.get(email__iexact=email)
                from .tokens import send_password_reset_email
                send_password_reset_email(user)
            except (User.DoesNotExist, Exception):
                pass
        return Response({'detail': 'If that email exists, a reset link has been sent.'}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """POST /auth/password-reset-confirm/ {token, new_password}"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get('token')
        new_password = request.data.get('new_password')
        if not token or not new_password or len(new_password) < 8:
            return Response({'error': 'token and a new_password (min 8 chars) are required'}, status=status.HTTP_400_BAD_REQUEST)
        from .tokens import verify_reset_token
        from django.core import signing
        try:
            email = verify_reset_token(token)
        except (signing.BadSignature, signing.SignatureExpired):
            return Response({'error': 'Invalid or expired token'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new_password)
        user.save()
        return Response({'detail': 'Password updated successfully.'})


class VerifyEmailView(APIView):
    """POST /auth/verify-email/ {token}"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get('token')
        if not token:
            return Response({'error': 'token is required'}, status=status.HTTP_400_BAD_REQUEST)
        from .tokens import verify_email_token
        from django.core import signing
        try:
            email = verify_email_token(token)
        except (signing.BadSignature, signing.SignatureExpired):
            return Response({'error': 'Invalid or expired token'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)
        user.is_verified = True
        user.save(update_fields=['is_verified', 'updated_at'])
        return Response({'detail': 'Email verified successfully.'})


class ResendVerificationView(APIView):
    """POST /auth/resend-verification/ — requires auth."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .tokens import send_verification_email
        try:
            send_verification_email(request.user)
        except Exception:
            pass
        return Response({'detail': 'Verification email sent if sending is configured.'})


class CookieTokenRefreshView(TokenRefreshView):
    """Refresh access token using the httpOnly refresh cookie (or request body)."""

    def post(self, request, *args, **kwargs):
        if 'refresh' not in request.data:
            cookie = request.COOKIES.get(django_settings.AUTH_REFRESH_COOKIE_NAME)
            if cookie:
                request.data = {**request.data, 'refresh': cookie}
        try:
            response = super().post(request, *args, **kwargs)
        except (InvalidToken, TokenError) as e:
            resp = Response({'detail': str(e)}, status=status.HTTP_401_UNAUTHORIZED)
            _clear_refresh_cookie(resp)
            return resp

        if response.status_code == 200 and 'refresh' in response.data:
            _set_refresh_cookie(response, response.data['refresh'])
        return response


class MeView(generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/auth/me/ - Get current user profile.
    PATCH /api/v1/auth/me/ - Update current user profile.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return UserUpdateSerializer
        return UserSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', True)
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(self.get_object()).data)


class AddressListCreateView(generics.ListCreateAPIView):
    """
    GET /api/v1/auth/addresses/ - List current user's addresses.
    POST /api/v1/auth/addresses/ - Create a new address.
    """
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)


class AddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/v1/auth/addresses/{id}/ - Get address detail.
    PATCH /api/v1/auth/addresses/{id}/ - Update address.
    DELETE /api/v1/auth/addresses/{id}/ - Delete address.
    """
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)
