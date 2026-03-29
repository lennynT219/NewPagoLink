from typing import Any, Dict, Optional
import csv
import io
import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from django.db.models import Sum
from decimal import Decimal
from django.db import transaction
from django.http import HttpResponse
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from payments.models import Link, Payment, Refund
from accounts.models import CustomUser

def calculate_tax(amount: Decimal, include_tax: bool) -> Decimal:
  """Calcula el IVA (12%) si no está incluido."""
  if not include_tax:
    return (amount * Decimal('0.12')).quantize(Decimal('0.01'))
  return Decimal('0.00')

def send_payment_invite(payment: Payment, req: Any) -> None:
  """Envía un correo al cliente invitándolo a pagar el link generado."""
  if not payment.email: return
  
  subject = f"Invitación de pago de {payment.seller.user.get_full_name()}"
  context = {
    'payment': payment,
    'pay_url': f"{req.scheme}://{req.get_host()}/payments/pay/{payment.link.id}/"
  }
  html_content = render_to_string('payments/emails/invite_email.html', context)
  text_content = strip_tags(html_content)
  
  email = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [payment.email])
  email.attach_alternative(html_content, "text/html")
  email.send()

def send_payment_confirmation(payment: Payment) -> None:
  """Envía el comprobante de pago exitoso al cliente."""
  if not payment.email: return
  
  subject = f"Comprobante de Pago Exitoso - {payment.description}"
  html_content = render_to_string('payments/emails/confirmation_email.html', {'payment': payment})
  text_content = strip_tags(html_content)
  
  email = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [payment.email])
  email.attach_alternative(html_content, "text/html")
  email.send()

@transaction.atomic
def create_payment_link(seller: CustomUser, data: Dict[str, Any]) -> Link:
  """Servicio para crear un Link de pago con lógica financiera."""
  subtotal = Decimal(str(data['subtotal']))
  include_igv = data.get('include_igv', False)
  
  igv = Decimal('0.00')
  amount = subtotal
  
  if not include_igv:
    igv = calculate_tax(subtotal, False)
    amount = subtotal + igv

  return Link.objects.create(
    seller=seller,
    description=data['description'],
    subtotal=subtotal,
    igv=igv,
    amount=amount,
    include_igv=include_igv,
    unique=data.get('unique', False)
  )

@transaction.atomic
def process_payment_result(payment_id: int, result_data: Dict[str, Any]) -> Payment:
  """Actualiza el estado del pago y gestiona links únicos."""
  payment = Payment.objects.select_for_update().get(id=payment_id)
  result_code = result_data.get('result', {}).get('code', '')
  SUCCESS_CODES = ['000.000.000', '000.100.110', '000.100.112', '000.400.010', '000.400.020']
  
  if any(code in result_code for code in SUCCESS_CODES):
    payment.status = Payment.PaymentStatus.PAID
    payment.state = True
    payment.transaction_id = result_data.get('id')
    if payment.link and payment.link.unique:
      payment.link.active = False
      payment.link.save()
    
    # Notificar al cliente
    try:
      send_payment_confirmation(payment)
    except Exception as e:
      print(f"Error enviando confirmación: {e}")
  else:
    payment.status = Payment.PaymentStatus.FAILED
    payment.state = False
  
  payment.save()
  return payment

def generate_payments_csv(seller: CustomUser) -> io.StringIO:
  """Genera reporte en CSV."""
  payments = Payment.objects.filter(seller=seller, state=True).order_by('-id')
  output = io.StringIO()
  writer = csv.writer(output)
  writer.writerow(['FECHA', 'CLIENTE', 'IDENTIFICACIÓN', 'CORREO', 'TOTAL', 'ID TRANSACCIÓN'])
  for p in payments:
    writer.writerow([
        p.link.created_at.strftime('%Y-%m-%d') if p.link else '',
        f"{p.first_name} {p.last_name}", p.identify, p.email, p.amount, p.transaction_id
    ])
  return output

def generate_payments_excel(seller: CustomUser) -> io.BytesIO:
  """Genera reporte en Excel (.xlsx) con estilos."""
  payments = Payment.objects.filter(seller=seller, state=True).order_by('-id')
  wb = Workbook()
  ws = wb.active
  ws.title = "Ventas"
  headers = ['FECHA', 'CLIENTE', 'IDENTIFICACIÓN', 'CORREO', 'TOTAL', 'ID TRANSACCIÓN']
  ws.append(headers)
  
  for cell in ws[1]:
    cell.font = Font(bold=True, color="FFFFFF")
    cell.fill = PatternFill(start_color="007bff", end_color="007bff", fill_type="solid")

  for p in payments:
    ws.append([
        p.link.created_at.strftime('%Y-%m-%d') if p.link else '',
        f"{p.first_name} {p.last_name}", p.identify, p.email, float(p.amount), p.transaction_id
    ])

  output = io.BytesIO()
  wb.save(output)
  output.seek(0)
  return output

@transaction.atomic
def request_refund(seller: CustomUser, payment: Payment, description: str) -> Refund:
  """Crea una solicitud de reembolso para un pago específico."""
  if payment.seller != seller: raise ValueError("No tiene permisos sobre este pago.")
  if payment.status != Payment.PaymentStatus.PAID: raise ValueError("Solo se pueden reembolsar pagos confirmados.")
  if hasattr(payment, 'refund'): raise ValueError("Este pago ya tiene una solicitud de reembolso.")

  return Refund.objects.create(
    seller=seller, payment=payment, description=description,
    amount=payment.amount, state=False
  )

def get_seller_stats(seller: CustomUser) -> Dict[str, Any]:
  """Estadísticas del Dashboard."""
  links_count = Link.objects.filter(seller=seller).count()
  sales_agg = Payment.objects.filter(seller=seller, state=True).aggregate(total=Sum('amount'))
  total_sales = sales_agg['total'] or 0.0
  refunds_agg = Refund.objects.filter(seller=seller).aggregate(total=Sum('amount'))
  total_refunds = refunds_agg['total'] or 0.0
  return {
    'links_count': links_count, 'total_sales': total_sales, 'total_refunds': total_refunds,
    'active': seller.state, 'email_active': seller.email_active, 'seller_name': seller.user.first_name,
  }
