from django.db import transaction

from apps.inventory.models import Stock, StockMovement
from apps.inventory.services import InsufficientStockError, release_reserved_stock_for_sale

from .models import Sale, SalePayment


@transaction.atomic
def apply_payment_status(payment, provider_status, provider_response=None, user=None):
    payment = SalePayment.objects.select_for_update().select_related("sale").get(pk=payment.pk)
    sale = Sale.objects.select_for_update().get(pk=payment.sale_id)
    normalized = str(provider_status or "").lower()
    if sale.status == Sale.Status.CANCELLED and normalized in {"paid", "completed"}:
        normalized = SalePayment.Status.CANCELLED
    if normalized in {"paid", "completed"} and sale.status == Sale.Status.PENDING_PAYMENT:
        balances = {
            balance.product_id: balance
            for balance in Stock.objects.select_for_update().filter(
                organization=sale.organization, store=sale.store,
                product_id__in=sale.items.values("product_id"),
            ).order_by("product_id")
        }
        for item in sale.items.all():
            balance = balances.get(item.product_id)
            if balance is None or balance.reserved_quantity < item.quantity or balance.quantity < item.quantity:
                raise InsufficientStockError(f"Reserva inválida para {item.product_name}.")
        for item in sale.items.all():
            balance = balances[item.product_id]
            balance.quantity -= item.quantity
            balance.reserved_quantity -= item.quantity
            balance.save(update_fields=["quantity", "reserved_quantity", "updated_at"])
            StockMovement.objects.create(
                organization=sale.organization, store=sale.store, product=item.product,
                movement_type=StockMovement.MovementType.RELEASE, quantity=item.quantity,
                balance_after=balance.quantity, sale=sale, created_by=user or sale.cashier,
                reason=f"Conversão da reserva da venda #{sale.pk}",
            )
            StockMovement.objects.create(
                organization=sale.organization, store=sale.store, product=item.product,
                movement_type=StockMovement.MovementType.SALE, quantity=item.quantity,
                balance_after=balance.quantity, sale=sale, created_by=user or sale.cashier,
                reason=f"Baixa da venda #{sale.pk}",
            )
        sale.status = Sale.Status.COMPLETED
        sale.save(update_fields=["status", "updated_at"])
    elif normalized in {"expired", "cancelled", "failed"} and sale.status == Sale.Status.PENDING_PAYMENT:
        sale = release_reserved_stock_for_sale(sale, user or sale.cashier)
    payment.status = SalePayment.Status.PAID if normalized in {"paid", "completed"} else normalized or payment.status
    if provider_response is not None:
        payment.provider_response = provider_response
    payment.save(update_fields=["status", "provider_response", "updated_at"])
    return payment
