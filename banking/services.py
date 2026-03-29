from typing import Any, Dict, Optional
from django.db import transaction
from .models import PaymentMethod, Bank
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
