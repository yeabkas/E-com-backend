from django.core.mail import send_mail
from django.core import signing
from django.conf import settings

RESET_SALT = 'password-reset'
VERIFY_SALT = 'email-verify'
TOKEN_MAX_AGE = 60 * 60 * 24  # 24 hours


def make_reset_token(email: str) -> str:
    return signing.TimestampSigner(salt=RESET_SALT).sign(email)


def verify_reset_token(token: str, max_age: int = TOKEN_MAX_AGE) -> str:
    """Returns the email address for a valid token, or raises signing.BadSignature."""
    return signing.TimestampSigner(salt=RESET_SALT).unsign(token, max_age=max_age)


def send_password_reset_email(user) -> None:
    token = make_reset_token(user.email)
    frontend_base = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    link = f"{frontend_base}/reset-password?token={token}"
    send_mail(
        subject='Reset your GASH E-COM password',
        message=f"Hi {user.first_name},\n\nReset your password using the link below (valid 24h):\n{link}\n\nIf you didn't request this, ignore this email.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def make_verify_token(email: str) -> str:
    return signing.TimestampSigner(salt=VERIFY_SALT).sign(email)


def verify_email_token(token: str, max_age: int = TOKEN_MAX_AGE) -> str:
    return signing.TimestampSigner(salt=VERIFY_SALT).unsign(token, max_age=max_age)


def send_verification_email(user) -> None:
    token = make_verify_token(user.email)
    frontend_base = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    link = f"{frontend_base}/verify-email?token={token}"
    send_mail(
        subject='Verify your GASH E-COM email',
        message=f"Hi {user.first_name},\n\nVerify your email address:\n{link}\n\nIf you didn't register, ignore this email.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
