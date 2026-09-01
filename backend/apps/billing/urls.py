from django.urls import path

from .views import BillingInvoiceListView, BillingStatusView


urlpatterns = [
    path("status/", BillingStatusView.as_view(), name="billing-status"),
    path("invoices/", BillingInvoiceListView.as_view(), name="billing-invoices"),
]
