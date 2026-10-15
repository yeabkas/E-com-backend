from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='auth-register'),
    path('login/', views.LoginView.as_view(), name='auth-login'),
    path('logout/', views.LogoutView.as_view(), name='auth-logout'),
    path('token/refresh/', views.CookieTokenRefreshView.as_view(), name='auth-token-refresh'),
    path('me/', views.MeView.as_view(), name='auth-me'),
    path('me/profile-picture/', views.ProfilePictureView.as_view(), name='auth-profile-picture'),
    path('addresses/', views.AddressListCreateView.as_view(), name='address-list'),
    path('addresses/<uuid:pk>/', views.AddressDetailView.as_view(), name='address-detail'),
    path('password-reset/', views.PasswordResetRequestView.as_view(), name='password-reset'),
    path('password-reset-confirm/', views.PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('verify-email/', views.VerifyEmailView.as_view(), name='verify-email'),
    path('resend-verification/', views.ResendVerificationView.as_view(), name='resend-verification'),
]
