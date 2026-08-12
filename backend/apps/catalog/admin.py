from django.contrib import admin
from django.contrib import messages
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.utils.formats import number_format
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import BooleanRadioFilter, DropdownFilter

from apps.tenants.admin import TenantScopedAdminMixin, get_user_organization

from .models import Category, Product, Unit


class TenantCategoryFilter(DropdownFilter):
    title = "categoria"
    parameter_name = "categoria"

    def lookups(self, request, model_admin):
        queryset = Category.objects.all()
        organization = get_user_organization(request.user)
        if organization and not request.user.is_superuser:
            queryset = queryset.filter(organization=organization)
        return [(category.pk, category.name) for category in queryset.order_by("name")]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(category_id=self.value())
        return queryset


class TenantUnitFilter(DropdownFilter):
    title = "unidade"
    parameter_name = "unidade"

    def lookups(self, request, model_admin):
        queryset = Unit.objects.all()
        organization = get_user_organization(request.user)
        if organization and not request.user.is_superuser:
            queryset = queryset.filter(organization=organization)
        return [(unit.pk, unit.symbol) for unit in queryset.order_by("symbol")]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(unit_id=self.value())
        return queryset


class SimpleCatalogSaveActionsMixin:
    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if not request.user.is_superuser:
            context["show_save_and_continue"] = False
            context["show_save_and_add_another"] = False
        return super().render_change_form(request, context, add, change, form_url, obj)

    def get_action_choices(self, request, default_choices=None):
        choices = super().get_action_choices(request, default_choices)
        if choices:
            choices[0] = ("", "Selecionar ação")
        return choices

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            actions.pop("delete_selected", None)
        return actions


def is_product_relation_autocomplete(request, field_name):
    return (
        request.path.endswith("/autocomplete/")
        and request.GET.get("app_label") == "catalog"
        and request.GET.get("model_name") == "product"
        and request.GET.get("field_name") == field_name
    )


def product_count_message(count, singular, plural):
    if count == 1:
        return f"1 produto {singular}"
    return f"{count} produtos {plural}"


class CatalogStatusActionsMixin:
    status_noun_singular = "registro"
    status_noun_plural = "registros"
    status_noun_gender = "masculine"
    status_activated_singular = "ativado"
    status_activated_plural = "ativados"
    status_inactivated_singular = "inativado"
    status_inactivated_plural = "inativados"
    status_already_active_singular = "já estava ativo"
    status_already_active_plural = "já estavam ativos"
    status_already_inactive_singular = "já estava inativo"
    status_already_inactive_plural = "já estavam inativos"
    status_blocked_inactive_singular = "não pôde ser inativado por produtos ativos vinculados"
    status_blocked_inactive_plural = "não puderam ser inativados por produtos ativos vinculados"

    actions = ["activate_selected", "deactivate_selected"]

    def status_count_message(self, count, singular, plural):
        noun = self.status_noun_singular if count == 1 else self.status_noun_plural
        status = singular if count == 1 else plural
        return f"{count} {noun} {status}"

    def no_selected_message(self, status):
        if self.status_noun_gender == "feminine":
            return f"Nenhuma {self.status_noun_singular} {status} foi selecionada."
        return f"Nenhum {self.status_noun_singular} {status} foi selecionado."

    def no_blocked_deactivation_message(self):
        if self.status_noun_gender == "feminine":
            return f"Nenhuma {self.status_noun_singular} pôde ser inativada. Verifique produtos ativos vinculados."
        return f"Nenhum {self.status_noun_singular} pôde ser inativado. Verifique produtos ativos vinculados."

    @admin.action(description="Ativar selecionados")
    def activate_selected(self, request, queryset):
        inactive_queryset = queryset.filter(is_active=False)
        already_active_count = queryset.filter(is_active=True).count()
        updated = 0
        for obj in inactive_queryset:
            obj.is_active = True
            obj.save()
            updated += 1
        if updated == 0:
            self.message_user(request, self.no_selected_message("inativo"), level=messages.ERROR)
            return
        if already_active_count:
            self.message_user(
                request,
                f"{self.status_count_message(updated, self.status_activated_singular, self.status_activated_plural)}. {self.status_count_message(already_active_count, self.status_already_active_singular, self.status_already_active_plural)}.",
                level=messages.WARNING,
            )
            return
        self.message_user(request, f"{self.status_count_message(updated, self.status_activated_singular, self.status_activated_plural)} com sucesso.")

    @admin.action(description="Inativar selecionados")
    def deactivate_selected(self, request, queryset):
        active_queryset = queryset.filter(is_active=True)
        already_inactive_count = queryset.filter(is_active=False).count()
        updated = 0
        blocked = 0
        for obj in active_queryset:
            obj.is_active = False
            try:
                obj.save()
            except ValidationError:
                blocked += 1
            else:
                updated += 1
        if updated == 0:
            if blocked:
                self.message_user(request, self.no_blocked_deactivation_message(), level=messages.ERROR)
                return
            self.message_user(request, self.no_selected_message("ativo"), level=messages.ERROR)
            return
        details = []
        if blocked:
            details.append(self.status_count_message(blocked, self.status_blocked_inactive_singular, self.status_blocked_inactive_plural))
        if already_inactive_count:
            details.append(self.status_count_message(already_inactive_count, self.status_already_inactive_singular, self.status_already_inactive_plural))
        if details:
            self.message_user(request, f"{self.status_count_message(updated, self.status_inactivated_singular, self.status_inactivated_plural)}. {'; '.join(details)}.", level=messages.WARNING)
            return
        self.message_user(request, f"{self.status_count_message(updated, self.status_inactivated_singular, self.status_inactivated_plural)} com sucesso.")


@admin.register(Category)
class CategoryAdmin(CatalogStatusActionsMixin, SimpleCatalogSaveActionsMixin, TenantScopedAdminMixin, ModelAdmin):
    status_noun_singular = "categoria"
    status_noun_plural = "categorias"
    status_noun_gender = "feminine"
    status_activated_singular = "ativada"
    status_activated_plural = "ativadas"
    status_inactivated_singular = "inativada"
    status_inactivated_plural = "inativadas"
    status_already_active_singular = "já estava ativa"
    status_already_active_plural = "já estavam ativas"
    status_already_inactive_singular = "já estava inativa"
    status_already_inactive_plural = "já estavam inativas"
    status_blocked_inactive_singular = "não pôde ser inativada por produtos ativos vinculados"
    status_blocked_inactive_plural = "não puderam ser inativadas por produtos ativos vinculados"
    list_display = ["name", "organization", "active_products_count", "is_active"]
    list_display_links = ["name"]
    list_editable = ["is_active"]
    list_filter = ["organization", "is_active"]
    list_per_page = 25
    readonly_fields = ["created_at", "updated_at"]
    search_fields = ["name", "organization__name"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if is_product_relation_autocomplete(request, "category"):
            queryset = queryset.filter(is_active=True)
        return queryset.annotate(active_products_count=Count("products", filter=Q(products__is_active=True)))

    @admin.display(ordering="active_products_count", description="produtos ativos")
    def active_products_count(self, obj):
        return obj.active_products_count

    def get_fieldsets(self, request, obj=None):
        main_fields = ["name", "is_active"]
        if request.user.is_superuser or obj is not None:
            main_fields.insert(1, "organization")
        fieldsets = [("Dados da categoria", {"fields": main_fields})]
        if obj is not None:
            fieldsets.append(("Controle", {"fields": ["created_at", "updated_at"]}))
        return fieldsets


@admin.register(Unit)
class UnitAdmin(CatalogStatusActionsMixin, SimpleCatalogSaveActionsMixin, TenantScopedAdminMixin, ModelAdmin):
    status_noun_singular = "unidade"
    status_noun_plural = "unidades"
    status_noun_gender = "feminine"
    status_activated_singular = "ativada"
    status_activated_plural = "ativadas"
    status_inactivated_singular = "inativada"
    status_inactivated_plural = "inativadas"
    status_already_active_singular = "já estava ativa"
    status_already_active_plural = "já estavam ativas"
    status_already_inactive_singular = "já estava inativa"
    status_already_inactive_plural = "já estavam inativas"
    status_blocked_inactive_singular = "não pôde ser inativada por produtos ativos vinculados"
    status_blocked_inactive_plural = "não puderam ser inativadas por produtos ativos vinculados"
    list_display = ["symbol", "name", "organization", "active_products_count", "is_active"]
    list_display_links = ["symbol", "name"]
    list_editable = ["is_active"]
    list_filter = ["organization", "is_active"]
    list_per_page = 25
    readonly_fields = ["created_at", "updated_at"]
    search_fields = ["symbol", "name", "organization__name"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if is_product_relation_autocomplete(request, "unit"):
            queryset = queryset.filter(is_active=True)
        return queryset.annotate(active_products_count=Count("products", filter=Q(products__is_active=True)))

    @admin.display(ordering="active_products_count", description="produtos ativos")
    def active_products_count(self, obj):
        return obj.active_products_count

    def get_fieldsets(self, request, obj=None):
        main_fields = ["symbol", "name", "is_active"]
        if request.user.is_superuser or obj is not None:
            main_fields.insert(2, "organization")
        fieldsets = [("Dados da unidade", {"fields": main_fields})]
        if obj is not None:
            fieldsets.append(("Controle", {"fields": ["created_at", "updated_at"]}))
        return fieldsets


@admin.register(Product)
class ProductAdmin(SimpleCatalogSaveActionsMixin, TenantScopedAdminMixin, ModelAdmin):
    actions = ["activate_products", "deactivate_products"]
    autocomplete_fields = ["category", "unit"]
    list_display = ["name", "sku", "organization", "category", "unit", "formatted_price", "is_active"]
    list_display_links = ["name", "sku"]
    list_editable = ["is_active"]
    list_filter = ["organization", TenantCategoryFilter, TenantUnitFilter, ("is_active", BooleanRadioFilter)]
    list_filter_submit = True
    list_per_page = 25
    readonly_fields = ["created_at", "updated_at"]
    search_fields = ["name", "sku", "barcode", "organization__name"]
    tenant_list_filter = [TenantCategoryFilter, TenantUnitFilter, ("is_active", BooleanRadioFilter)]

    def get_fieldsets(self, request, obj=None):
        identity_fields = ["name", "sku", "barcode"]
        if request.user.is_superuser or obj is not None:
            identity_fields.insert(0, "organization")
        fieldsets = [
            ("Identificação", {"fields": identity_fields}),
            ("Classificação", {"fields": ["category", "unit"]}),
            ("Venda", {"fields": ["price", "is_active"]}),
        ]
        if obj is not None:
            fieldsets.append(("Controle", {"fields": ["created_at", "updated_at"]}))
        return fieldsets

    @admin.display(ordering="price", description="preço")
    def formatted_price(self, obj):
        return f"R$ {number_format(obj.price, decimal_pos=2, force_grouping=True)}"

    @admin.action(description="Inativar produtos selecionados")
    def deactivate_products(self, request, queryset):
        active_queryset = queryset.filter(is_active=True)
        inactive_count = queryset.filter(is_active=False).count()
        updated = active_queryset.update(is_active=False)
        if updated == 0:
            self.message_user(request, "Nenhum produto ativo foi selecionado para inativar.", level=messages.ERROR)
            return
        if inactive_count:
            self.message_user(
                request,
                f"{product_count_message(updated, 'inativado', 'inativados')}. {product_count_message(inactive_count, 'já estava inativo', 'já estavam inativos')}.",
                level=messages.WARNING,
            )
            return
        self.message_user(request, f"{product_count_message(updated, 'inativado', 'inativados')} com sucesso.")

    @admin.action(description="Ativar produtos selecionados")
    def activate_products(self, request, queryset):
        inactive_queryset = queryset.filter(is_active=False)
        already_active_count = queryset.filter(is_active=True).count()
        invalid_count = inactive_queryset.filter(Q(category__is_active=False) | Q(unit__is_active=False)).count()
        updated = inactive_queryset.filter(category__is_active=True, unit__is_active=True).update(is_active=True)
        if updated == 0:
            if invalid_count:
                self.message_user(request, "Nenhum produto pôde ser ativado. Verifique categoria e unidade ativas.", level=messages.ERROR)
                return
            self.message_user(request, "Nenhum produto inativo foi selecionado para ativar.", level=messages.ERROR)
            return
        if invalid_count or already_active_count:
            details = []
            if invalid_count:
                details.append(product_count_message(invalid_count, "não pôde ser ativado por categoria ou unidade inativa", "não puderam ser ativados por categoria ou unidade inativa"))
            if already_active_count:
                details.append(product_count_message(already_active_count, "já estava ativo", "já estavam ativos"))
            self.message_user(request, f"{product_count_message(updated, 'ativado', 'ativados')}. {'; '.join(details)}.", level=messages.WARNING)
            return
        self.message_user(request, f"{product_count_message(updated, 'ativado', 'ativados')} com sucesso.")

    def get_form(self, request, obj=None, change=False, **kwargs):
        form_class = super().get_form(request, obj, change, **kwargs)
        organization = get_user_organization(request.user)
        should_set_organization = not request.user.is_superuser and obj is None and organization

        class TenantProductForm(form_class):
            def __init__(self, *args, **form_kwargs):
                super().__init__(*args, **form_kwargs)
                if "price" in self.fields:
                    self.fields["price"].widget = forms.TextInput(
                        attrs={
                            "inputmode": "decimal",
                            "placeholder": "0,00",
                        }
                    )
                if organization and "category" in self.fields:
                    category_filter = Q(is_active=True)
                    if self.instance and self.instance.category_id:
                        category_filter |= Q(pk=self.instance.category_id)
                    self.fields["category"].queryset = Category.objects.filter(category_filter, organization=organization)
                if organization and "unit" in self.fields:
                    unit_filter = Q(is_active=True)
                    if self.instance and self.instance.unit_id:
                        unit_filter |= Q(pk=self.instance.unit_id)
                    self.fields["unit"].queryset = Unit.objects.filter(unit_filter, organization=organization)

            def _post_clean(self):
                if should_set_organization:
                    self.instance.organization = organization
                super()._post_clean()

        return TenantProductForm

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        organization = get_user_organization(request.user)
        if organization and db_field.name == "category":
            kwargs["queryset"] = Category.objects.filter(organization=organization, is_active=True)
        if organization and db_field.name == "unit":
            kwargs["queryset"] = Unit.objects.filter(organization=organization, is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
