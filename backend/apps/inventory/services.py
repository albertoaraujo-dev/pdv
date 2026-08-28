from decimal import Decimal

from django.db import transaction

from .models import Stock, StockMovement
from apps.billing.services import require_module


class InsufficientStockError(Exception):
    pass


@transaction.atomic
def reverse_stock_for_sale(sale, user):
    from apps.sales.models import Sale

    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status == Sale.Status.CANCELLED:
        return sale

    if sale.status == Sale.Status.PENDING_PAYMENT:
        return release_reserved_stock_for_sale(sale, user)

    for item in sale.items.select_related("product"):
        balance, _created = Stock.objects.select_for_update().get_or_create(
            organization=sale.organization,
            store=sale.store,
            product=item.product,
            defaults={"quantity": 0},
        )
        balance.quantity += item.quantity
        balance.save(update_fields=["quantity", "updated_at"])
        StockMovement.objects.create(
            organization=sale.organization,
            store=sale.store,
            product=item.product,
            movement_type=StockMovement.MovementType.SALE_REVERSAL,
            quantity=item.quantity,
            balance_after=balance.quantity,
            sale=sale,
            created_by=user,
            reason=f"Estorno da venda #{sale.pk}",
        )

    sale.status = Sale.Status.CANCELLED
    sale.save(update_fields=["status", "updated_at"])
    return sale


@transaction.atomic
def record_inbound_stock(store, product, quantity, reason, user):
    require_module(store.organization, "inventory")
    quantity = Decimal(quantity)
    balance, _created = Stock.objects.select_for_update().get_or_create(
        organization=store.organization,
        store=store,
        product=product,
        defaults={"quantity": 0},
    )
    balance.quantity += quantity
    balance.save(update_fields=["quantity", "updated_at"])
    return StockMovement.objects.create(
        organization=store.organization,
        store=store,
        product=product,
        movement_type=StockMovement.MovementType.INBOUND,
        quantity=quantity,
        balance_after=balance.quantity,
        created_by=user,
        reason=reason,
    )


@transaction.atomic
def deduct_stock_for_sale(sale, items, user):
    items = list(items)
    required = {}
    for item in items:
        required[item.product_id] = required.get(item.product_id, Decimal("0")) + item.quantity
    product_ids = {item.product_id for item in items}
    balances = {
        balance.product_id: balance
        for balance in Stock.objects.select_for_update().filter(store=sale.store, product_id__in=product_ids)
    }

    for product_id, quantity in required.items():
        balance = balances.get(product_id)
        if balance is None:
            item = next(item for item in items if item.product_id == product_id)
            raise InsufficientStockError(f"Produto sem estoque cadastrado: {item.product_name}.")
        if balance.quantity - balance.reserved_quantity < quantity:
            item = next(item for item in items if item.product_id == product_id)
            raise InsufficientStockError(
                f"Estoque insuficiente para {item.product_name}. Disponível: {balance.quantity - balance.reserved_quantity}."
            )

    for item in items:
        balance = balances[item.product_id]
        balance.quantity -= item.quantity
        balance.save(update_fields=["quantity", "updated_at"])
        StockMovement.objects.create(
            organization=sale.organization,
            store=sale.store,
            product=item.product,
            movement_type=StockMovement.MovementType.SALE,
            quantity=item.quantity,
            balance_after=balance.quantity,
            sale=sale,
            created_by=user,
            reason=f"Baixa da venda #{sale.pk}",
        )


@transaction.atomic
def reserve_stock_for_sale(sale, items, user):
    items = list(items)
    required = {}
    for item in items:
        required[item.product_id] = required.get(item.product_id, Decimal("0")) + item.quantity
    product_ids = sorted({item.product_id for item in items})
    balances = {
        balance.product_id: balance
        for balance in Stock.objects.select_for_update().filter(
            organization=sale.organization, store=sale.store, product_id__in=product_ids,
        ).order_by("product_id")
    }
    for product_id, quantity in required.items():
        balance = balances.get(product_id)
        available = balance.quantity - balance.reserved_quantity if balance else Decimal("0")
        if balance is None:
            item = next(item for item in items if item.product_id == product_id)
            raise InsufficientStockError(f"Produto sem estoque cadastrado: {item.product_name}.")
        if available < quantity:
            item = next(item for item in items if item.product_id == product_id)
            raise InsufficientStockError(f"Estoque insuficiente para {item.product_name}. Disponível: {available}.")
    for item in items:
        balance = balances[item.product_id]
        balance.reserved_quantity += item.quantity
        balance.save(update_fields=["reserved_quantity", "updated_at"])
        StockMovement.objects.create(
            organization=sale.organization, store=sale.store, product=item.product,
            movement_type=StockMovement.MovementType.RESERVATION, quantity=item.quantity,
            balance_after=balance.quantity, sale=sale, created_by=user,
            reason=f"Reserva da venda #{sale.pk}",
        )


@transaction.atomic
def release_reserved_stock_for_sale(sale, user):
    from apps.sales.models import Sale

    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status != Sale.Status.PENDING_PAYMENT:
        return sale
    for item in sale.items.select_related("product"):
        balance = Stock.objects.select_for_update().get(
            organization=sale.organization, store=sale.store, product=item.product,
        )
        balance.reserved_quantity -= item.quantity
        balance.save(update_fields=["reserved_quantity", "updated_at"])
        StockMovement.objects.create(
            organization=sale.organization, store=sale.store, product=item.product,
            movement_type=StockMovement.MovementType.RELEASE, quantity=item.quantity,
            balance_after=balance.quantity, sale=sale, created_by=user,
            reason=f"Liberação da reserva da venda #{sale.pk}",
        )
    sale.status = Sale.Status.CANCELLED
    sale.save(update_fields=["status", "updated_at"])
    return sale
