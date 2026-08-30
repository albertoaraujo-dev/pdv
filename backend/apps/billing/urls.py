from django.urls import path

from .views import BillingStatusView


urlpatterns = [
    path("status/", BillingStatusView.as_view(), name="billing-status"),
]
