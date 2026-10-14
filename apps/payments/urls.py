from django.urls import path

from . import views

urlpatterns = [
    path('chapa/init/', views.ChapaInitView.as_view(), name='chapa-init'),
    path('chapa/verify/', views.ChapaVerifyView.as_view(), name='chapa-verify'),
    path('webhooks/chapa/', views.ChapaWebhookView.as_view(), name='chapa-webhook'),
]
