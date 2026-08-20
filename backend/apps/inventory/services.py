from decimal import Decimal

from django.db import transaction

from .models import Stock, StockMovement


class InsufficientStockError(Exception):
    pass


@transaction.atomic
def record_inbound_stock(store, product, quantity, reason, user):
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
    product_ids = {item.product_id for item in items}
    balances = {
        balance.product_id: balance
        for balance in Stock.objects.select_for_update().filter(store=sale.store, product_id__in=product_ids)
    }

    for item in items:
        balance = balances.get(item.product_id)
        if balance is None:
            raise InsufficientStockError(f"Produto sem estoque cadastrado: {item.product_name}.")
        if balance.quantity < item.quantity:
            raise InsufficientStockError(
                f"Estoque insuficiente para {item.product_name}. Disponível: {balance.quantity}."
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
