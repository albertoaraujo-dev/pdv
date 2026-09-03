from django.urls import path

from .views import BillingCatalogView, BillingInvoiceListView, BillingPlanRequestListCreateView, BillingStatusView


urlpatterns = [
    path("plans/", BillingCatalogView.as_view(), name="billing-plans"),
    path("status/", BillingStatusView.as_view(), name="billing-status"),
    path("invoices/", BillingInvoiceListView.as_view(), name="billing-invoices"),
    path("requests/", BillingPlanRequestListCreateView.as_view(), name="billing-requests"),
]
