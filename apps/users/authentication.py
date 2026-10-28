from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class SuspensionAwareJWTAuthentication(JWTAuthentication):
    """Reject access tokens for suspended accounts immediately."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if user is not None and getattr(user, 'is_suspended', False):
            raise AuthenticationFailed('This account has been suspended.')
        return user
