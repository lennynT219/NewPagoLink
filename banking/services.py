from typing import Any, Dict, Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .models import PaymentMethod, Bank, DisbursementRequest
from accounts.models import CustomUser

def get_vendedor_payment_method(seller: CustomUser) -> Optional[PaymentMethod]:
  """Obtiene el método de pago configurado del vendedor."""
  return PaymentMethod.objects.filter(seller=seller).first()

@transaction.atomic
def save_payment_method(seller: CustomUser, data: Dict[str, Any]) -> PaymentMethod:
  """Crea o actualiza el método de pago de un vendedor."""
  payment_method, created = PaymentMethod.objects.update_or_create(
    seller=seller,
    defaults={
      'bank': data['bank'],
      'fullname': data['fullname'],
      'account_type': data['account_type'],
      'account_number': data['account_number'],
      'cci': data.get('cci'),
    }
  )
  return payment_method

@transaction.atomic
def create_disbursement_request(seller: CustomUser, amount: Decimal, method_id: int) -> DisbursementRequest:
  """Crea una solicitud de desembolso validando el saldo disponible."""
  if amount <= 0:
    raise ValueError("El monto debe ser mayor a cero.")
  
  if amount > seller.available_balance:
    raise ValueError(f"Saldo insuficiente. Saldo disponible: ${seller.available_balance}")

  method = PaymentMethod.objects.get(id=method_id, seller=seller)
  
  return DisbursementRequest.objects.create(
    vendor=seller,
    method=method,
    amount=amount,
    status=DisbursementRequest.Status.PENDING
  )

@transaction.atomic
def process_disbursement(request_id: int, status: str, admin_user: Any, rejection_reason: str = None) -> DisbursementRequest:
  """Procesa una solicitud de desembolso (Aprueba/Rechaza) y actualiza el saldo si aplica."""
  disbursement = DisbursementRequest.objects.select_for_update().get(id=request_id)
  
  if disbursement.status != DisbursementRequest.Status.PENDING:
    raise ValueError("Esta solicitud ya ha sido procesada.")

  seller = CustomUser.objects.select_for_update().get(id=disbursement.vendor.id)

  if status == DisbursementRequest.Status.APPROVED:
    if disbursement.amount > seller.available_balance:
      disbursement.status = DisbursementRequest.Status.REJECTED
      disbursement.rejection_reason = "Saldo insuficiente al momento de procesar."
    else:
      seller.available_balance -= disbursement.amount
      seller.save()
      disbursement.status = DisbursementRequest.Status.APPROVED
  
  elif status == DisbursementRequest.Status.REJECTED:
    disbursement.status = DisbursementRequest.Status.REJECTED
    disbursement.rejection_reason = rejection_reason

  disbursement.processed_at = timezone.now()
  disbursement.save()
  
  return disbursement
