from typing import Any, Dict, Optional
from django.db.models import Sum
from decimal import Decimal
from django.db import transaction
from payments.models import Link, Payment, Refund
from accounts.models import CustomUser

def calculate_tax(amount: Decimal, include_tax: bool) -> Decimal:
  """Calcula el IVA (12%) si no está incluido."""
  if not include_tax:
    return (amount * Decimal('0.12')).quantize(Decimal('0.01'))
  return Decimal('0.00')

@transaction.atomic
def create_payment_link(seller: CustomUser, data: Dict[str, Any]) -> Link:
  """
  Servicio para crear un Link de pago.
  Realiza cálculos financieros y persiste el objeto.
  """
  subtotal = Decimal(str(data['subtotal']))
  include_igv = data.get('include_igv', False)
  
  # Si include_igv es True, el subtotal ya lo tiene. 
  # Si es False, debemos sumárselo (lógica del sistema legacy invertida para claridad)
  # En el legado: if include_igv (checkbox) -> link.include_igv = False (??)
  # Vamos a hacerlo más intuitivo aquí.
  
  igv = Decimal('0.00')
  amount = subtotal
  
  if not include_igv:
    igv = calculate_tax(subtotal, False)
    amount = subtotal + igv

  link = Link.objects.create(
    seller=seller,
    description=data['description'],
    subtotal=subtotal,
    igv=igv,
    amount=amount,
    include_igv=include_igv,
    unique=data.get('unique', False)
  )
  
  return link

def get_seller_stats(seller: CustomUser) -> Dict[str, Any]:
  """Calcula las estadísticas financieras de un vendedor."""
  links_count = Link.objects.filter(seller=seller).count()
  sales_agg = Payment.objects.filter(seller=seller, state=True).aggregate(total=Sum('amount'))
  total_sales = sales_agg['total'] or 0.0
  refunds_agg = Refund.objects.filter(seller=seller).aggregate(total=Sum('amount'))
  total_refunds = refunds_agg['total'] or 0.0

  return {
    'links_count': links_count,
    'total_sales': total_sales,
    'total_refunds': total_refunds,
    'active': seller.state,
    'email_active': seller.email_active,
    'seller_name': seller.user.first_name,
  }
