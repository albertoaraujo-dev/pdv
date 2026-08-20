from django.contrib import admin
from django import forms
from unfold.admin import ModelAdmin
from unfold.widgets import UnfoldAdminDecimalFieldWidget, UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget

from apps.accounts.policies import can_access_admin, get_allowed_stores, get_user_organization
from apps.catalog.models import Product
from apps.tenants.models import Store

from .models import Stock, StockMovement
from .services import record_inbound_stock


class StockInboundForm(forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = ["store", "product", "quantity", "reason"]

    quantity = forms.DecimalField(
        min_value=0.001,
        max_digits=12,
        decimal_places=3,
        label="Quantidade",
        widget=UnfoldAdminDecimalFieldWidget(attrs={"step": "0.001", "placeholder": "0,000"}),
    )
    reason = forms.CharField(
        max_length=255,
        label="Motivo",
        widget=UnfoldAdminTextInputWidget(attrs={"placeholder": "Ex.: compra inicial"}),
    )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.fields["store"].widget = UnfoldAdminSelectWidget()
        self.fields["product"].widget = UnfoldAdminSelectWidget()
        if request and request.user.is_superuser:
            self.fields["store"].queryset = Store.objects.all()
            self.fields["product"].queryset = Product.objects.all()
        elif request:
            organization = get_user_organization(request.user)
            self.fields["store"].queryset = get_allowed_stores(request.user)
            self.fields["product"].queryset = Product.objects.filter(organization=organization, is_active=True) if organization else Product.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        store = cleaned_data.get("store")
        product = cleaned_data.get("product")
        if store and product and store.organization_id != product.organization_id:
            raise forms.ValidationError("A loja e o produto precisam pertencer à mesma organização.")
        return cleaned_data


@admin.register(Stock)
class StockAdmin(ModelAdmin):
    list_display = ["store", "product", "quantity", "updated_at"]
    list_filter = ["store", "updated_at"]
    search_fields = ["store__name", "product__name", "product__sku"]
    readonly_fields = ["organization", "store", "product", "quantity", "updated_at"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("organization", "store", "product")
        if request.user.is_superuser:
            return queryset
        organization = get_user_organization(request.user)
        if not organization:
            return queryset.none()
        return queryset.filter(organization=organization, store__in=get_allowed_stores(request.user))

    def has_module_permission(self, request):
        return can_access_admin(request.user)

    def has_view_permission(self, request, obj=None):
        if not can_access_admin(request.user):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return self.get_queryset(request).filter(pk=obj.pk).exists()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockMovement)
class StockMovementAdmin(ModelAdmin):
    list_display = ["created_at", "store", "product", "movement_type", "quantity", "balance_after", "reason", "sale"]
    list_filter = ["movement_type", "store", "created_at"]
    search_fields = ["product__name", "product__sku", "sale__id", "reason"]
    readonly_fields = [
        "organization", "store", "product", "movement_type", "quantity", "balance_after", "sale", "created_by", "reason", "created_at"
    ]

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            class RequestStockInboundForm(StockInboundForm):
                def __init__(self, *args, **form_kwargs):
                    form_kwargs["request"] = request
                    super().__init__(*args, **form_kwargs)

            return RequestStockInboundForm
        return super().get_form(request, obj, change, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return [(None, {"fields": ("store", "product", "quantity", "reason")})]
        return super().get_fieldsets(request, obj)

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        return super().get_readonly_fields(request, obj)

    def save_model(self, request, obj, form, change):
        if not change:
            movement = record_inbound_stock(
                store=form.cleaned_data["store"],
                product=form.cleaned_data["product"],
                quantity=form.cleaned_data["quantity"],
                reason=form.cleaned_data["reason"],
                user=request.user,
            )
            obj.pk = movement.pk
            obj._state.adding = False
            return
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("organization", "store", "product", "sale")
        if request.user.is_superuser:
            return queryset
        organization = get_user_organization(request.user)
        if not organization:
            return queryset.none()
        return queryset.filter(organization=organization, store__in=get_allowed_stores(request.user))

    def has_module_permission(self, request):
        return can_access_admin(request.user)

    def has_view_permission(self, request, obj=None):
        if not can_access_admin(request.user):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return self.get_queryset(request).filter(pk=obj.pk).exists()

    def has_add_permission(self, request):
        return can_access_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
