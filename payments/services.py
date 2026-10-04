import csv
import io
import logging
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import Sum
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from accounts.models import CustomUser
from payments.models import Link, Payment, PaymentAttempt, Refund, Sale
from shared.email_service import send_html_email

logger = logging.getLogger(__name__)


def calculate_tax(amount: Decimal, include_tax: bool) -> Decimal:
  """Calcula el IVA (dinámico desde settings) si no está incluido."""
  if not include_tax:
    return (amount * settings.TAX_IVA).quantize(Decimal('0.01'))
  return Decimal('0.00')


def send_payment_invite(payment: Payment, req: Any) -> None:
  """Envía un correo al cliente invitándolo a pagar el link generado."""
  if not payment.email:
    return

  subject = f'Invitación de pago de {payment.seller.user.get_full_name()}'
  context = {
    'payment': payment,
    'pay_url': f'{req.scheme}://{req.get_host()}/payments/pay/{payment.link.id}/?p={payment.id}',
  }
  ok = send_html_email(subject, [payment.email], 'payments/emails/invite_email.html', context)
  if not ok:
    logger.error('Payment invite email failed for %s', payment.email)


def send_payment_confirmation(payment: Payment) -> None:
  """Envía el comprobante de pago exitoso al cliente."""
  if not payment.email:
    return

  subject = f'Comprobante de Pago Exitoso - {payment.description}'
  ok = send_html_email(subject, [payment.email], 'payments/emails/confirmation_email.html', {'payment': payment})
  if not ok:
    logger.error('Payment confirmation email failed for %s', payment.email)


@transaction.atomic
def create_payment_link(seller: CustomUser, data: dict[str, Any]) -> Link:
  """Servicio para crear un Link de pago con lógica financiera avanzada (IVA 15%/0%)."""
  input_amount = Decimal(str(data['subtotal']))
  tax_type = data.get('tax_type', Link.TaxType.VAT_15)
  include_igv = data.get('include_igv', True)

  # Determinar tasa de IVA
  if tax_type == Link.TaxType.VAT_15:
    vat_rate = Decimal('0.15')
  elif tax_type == Link.TaxType.VAT_0:
    vat_rate = Decimal('0.00')
  else:
    vat_rate = Decimal('0.00')

  if include_igv:
    # El monto ingresado ya tiene IVA. Desglosamos hacia atrás.
    # Total = Monto. Base = Total / (1 + tasa)
    total_amount = input_amount
    base_imponible = (total_amount / (Decimal('1.00') + vat_rate)).quantize(Decimal('0.01'))
    valor_iva = total_amount - base_imponible
  else:
    # El monto ingresado es la base. Sumamos IVA.
    base_imponible = input_amount
    valor_iva = (base_imponible * vat_rate).quantize(Decimal('0.01'))
    total_amount = base_imponible + valor_iva

  return Link.objects.create(
    seller=seller,
    description=data['description'],
    tax_type=tax_type,
    vat_rate=vat_rate,
    include_igv=include_igv,
    subtotal=base_imponible,
    igv=valor_iva,
    amount=total_amount,
    unique=data.get('unique', False),
  )


SELLER_FEE = Decimal('0.35')
OPEN_ATTEMPT_STATES = ['CREATING', 'LIVE', 'UNKNOWN']
# Only documented, definitive declines release an attempt for immediate retry.
DECLINE_CODES = {
  '800.100.151',
  '800.100.152',
  '800.100.155',
  '800.100.159',
  '800.100.165',
  '800.100.168',
  '800.100.170',
  '800.100.171',
  '800.100.174',
  '800.100.176',
  '800.100.179',
  '800.100.190',
  '800.100.197',
  '800.100.402',
}


def _record_attempt(attempt, state, reason, code=''):
  """Keep sanitized state history, never raw provider/customer payloads."""
  attempt.state = state
  attempt.result_code = code
  attempt.history = [
    *attempt.history,
    {'at': timezone.now().isoformat(), 'state': state, 'reason': reason, 'code': code},
  ]
  attempt.save()


def _settled(payment):
  # Sale history survives refunds, including the legacy FAILED refund convention.
  return (
    payment.status == Payment.PaymentStatus.PAID
    or payment.state
    or Sale.objects.filter(payment=payment).exists()
    or payment.status == 'REFUNDED'
  )


def prepare_payment_checkout(payment_id, gateway, customer_data, client_ip):
  """Persist reservation before I/O; concurrent retries reuse the open attempt."""
  with transaction.atomic():
    payment = Payment.objects.select_for_update().get(pk=payment_id)
    if _settled(payment):
      raise ValueError('Este pago ya ha sido procesado.')
    if not payment.seller or payment.amount < SELLER_FEE:
      raise ValueError('El monto del pago debe ser al menos USD 0.35.')
    link = Link.objects.select_for_update().get(pk=payment.link.pk) if payment.link else None
    if link is None:
      raise ValueError('Este pago no tiene un link activo.')
    if not link.active:
      raise ValueError('Este link no está activo.')
    current = PaymentAttempt.objects.select_for_update().filter(payment=payment, state__in=OPEN_ATTEMPT_STATES).first()
    if current:
      # Start no earlier than the response, not the pre-I/O reservation.
      # Later observations conservatively extend the local no-retry window.
      if current.updated_at > timezone.now() - timedelta(minutes=30):
        return current
      _record_attempt(current, 'EXPIRED', 'checkout_window_elapsed')
    for key in ('first_name', 'last_name', 'email', 'identify', 'phone'):
      if customer_data.get(key) is not None:
        setattr(payment, key, customer_data[key])
    payment.amount_client = payment.amount
    payment.status = Payment.PaymentStatus.PENDING
    payment.save()
    attempt = PaymentAttempt.objects.create(payment=payment, amount=payment.amount)
    _record_attempt(attempt, 'CREATING', 'checkout_reserved')
    customer = {key: getattr(payment, key) for key in ('first_name', 'last_name', 'email', 'identify', 'phone')}

  # A timeout may have created a remote checkout; do not blindly retry it.
  try:
    checkout_id = gateway.prepare_checkout(
      amount=attempt.amount,
      subtotal=payment.subtotal,
      igv=payment.igv,
      include_igv=link.include_igv,
      transaction_id=attempt.merchant_transaction_id,
      customer_data=customer,
      client_ip=client_ip,
    )
  except Exception:
    checkout_id = None
  with transaction.atomic():
    Payment.objects.select_for_update().get(pk=payment_id)
    attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
    if isinstance(checkout_id, str) and re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,254}', checkout_id):
      try:
        with transaction.atomic():
          attempt.checkout_id = checkout_id
          attempt.save()
      except IntegrityError:
        attempt.checkout_id = None
        state = 'UNKNOWN' if attempt.state == 'CREATING' else attempt.state
        _record_attempt(attempt, state, 'checkout_id_conflict')
      else:
        if attempt.state == 'CREATING':
          _record_attempt(attempt, 'LIVE', 'checkout_created')
    elif attempt.state == 'CREATING':
      _record_attempt(attempt, 'UNKNOWN', 'checkout_unavailable')
    return attempt


def _valid_result(payment, attempt, data):
  if not isinstance(data, dict) or not isinstance(data.get('result'), dict):
    return False
  provider_id = data.get('id')
  code = data['result'].get('code')
  if (
    not isinstance(provider_id, str)
    or not provider_id.strip()
    or provider_id != provider_id.strip()
    or len(provider_id) > 255
    or not isinstance(code, str)
    or not re.fullmatch(r'\d{3}\.\d{3}\.\d{3}', code)
  ):
    return False
  try:
    raw_amount = data.get('amount')
    # JSON floats may already have lost fractional precision; require exact input.
    if isinstance(raw_amount, bool) or not isinstance(raw_amount, (str, int, Decimal)):
      return False
    amount = Decimal(str(raw_amount))
    if not amount.is_finite() or amount != amount.quantize(Decimal('0.01')):
      return False
  except (InvalidOperation, ValueError):
    return False
  return (
    attempt.checkout_id is not None
    and data.get('merchantTransactionId') == attempt.merchant_transaction_id
    and amount == attempt.amount == payment.amount
    and amount >= SELLER_FEE
    and data.get('currency') == attempt.currency == 'USD'
    and data.get('paymentType') == 'DB'
    and not Payment.objects.exclude(pk=payment.pk).filter(transaction_id=provider_id).exists()
    and not PaymentAttempt.objects.exclude(pk=attempt.pk).filter(provider_transaction_id=provider_id).exists()
    and attempt.provider_transaction_id in (None, provider_id)
  )


def _confirmation_after_commit(payment):
  try:
    send_payment_confirmation(payment)
  except Exception:
    logger.warning('Payment confirmation unavailable for payment %s', payment.pk)


@transaction.atomic
def process_payment_result(payment_id: int, result_data: Any, attempt_id=None) -> Payment:
  """Credit a bound server-fetched debit exactly once; ambiguity is not decline."""
  payment = Payment.objects.select_for_update().get(pk=payment_id)
  if _settled(payment):
    return payment
  attempts = PaymentAttempt.objects.select_for_update().filter(payment=payment)
  if attempt_id is not None:
    attempt = attempts.filter(pk=attempt_id).first()
  else:
    merchant = result_data.get('merchantTransactionId') if isinstance(result_data, dict) else None
    attempt = attempts.filter(merchant_transaction_id=merchant).first() if isinstance(merchant, str) else None
  if attempt is None:
    return payment
  if not _valid_result(payment, attempt, result_data):
    if attempt.state in OPEN_ATTEMPT_STATES:
      _record_attempt(attempt, 'UNKNOWN', 'invalid_or_unavailable_result')
    return payment
  code = result_data['result']['code']
  success_codes = {'000.000.000'}
  # Test connector responses are never approvals on the production endpoint.
  if settings.DATAFAST_TEST_MODE and urlsplit(settings.DATAFAST_BASE_URL).hostname == 'eu-test.oppwa.com':
    success_codes.update({'000.100.110', '000.100.112'})
  try:
    # Constraints are the final race guard across different payment row locks.
    with transaction.atomic():
      attempt.provider_transaction_id = result_data['id']
      if code not in success_codes and code not in DECLINE_CODES:
        if attempt.state in OPEN_ATTEMPT_STATES:
          _record_attempt(attempt, 'UNKNOWN', 'non_final_result', code)
        else:
          attempt.save(update_fields=['provider_transaction_id'])
        return payment
      if code in DECLINE_CODES:
        _record_attempt(attempt, 'DECLINED', 'confirmed_decline', code)
        if not attempts.filter(state__in=OPEN_ATTEMPT_STATES).exists():
          payment.status = Payment.PaymentStatus.FAILED
          payment.state = False
          payment.save()
        return payment
      if not payment.seller:
        return payment
      seller = CustomUser.objects.select_for_update().get(pk=payment.seller.pk)
      payment.status = Payment.PaymentStatus.PAID
      payment.state = True
      payment.transaction_id = result_data['id']
      payment.commission = SELLER_FEE
      payment.amount_client = payment.amount
      payment.save()
      net_amount = attempt.amount - SELLER_FEE
      Sale.objects.create(
        vendor=seller, payment=payment, amount=attempt.amount, commission=SELLER_FEE, net_amount=net_amount
      )
      seller.available_balance += net_amount
      seller.save(update_fields=['available_balance'])
      _record_attempt(attempt, 'SUCCEEDED', 'confirmed_debit', code)
      for other in attempts.filter(state__in=OPEN_ATTEMPT_STATES).exclude(pk=attempt.pk):
        _record_attempt(other, 'SUPERSEDED', 'payment_credited_elsewhere')
      if payment.link:
        Link.objects.filter(pk=payment.link.pk, unique=True).update(active=False)
  except IntegrityError:
    payment.refresh_from_db()
    attempt.refresh_from_db()
    if attempt.state in OPEN_ATTEMPT_STATES:
      _record_attempt(attempt, 'UNKNOWN', 'provider_identity_conflict')
    return payment
  transaction.on_commit(lambda: _confirmation_after_commit(payment))
  return payment


def generate_payments_csv(seller: CustomUser) -> io.StringIO:
  """Genera reporte en CSV."""
  payments = Payment.objects.filter(seller=seller, state=True).order_by('-id')
  output = io.StringIO()
  writer = csv.writer(output)
  writer.writerow(['FECHA', 'CLIENTE', 'IDENTIFICACIÓN', 'CORREO', 'TOTAL', 'ID TRANSACCIÓN'])
  for p in payments:
    writer.writerow(
      [
        p.link.created_at.strftime('%Y-%m-%d') if p.link else '',
        f'{p.first_name} {p.last_name}',
        p.identify,
        p.email,
        p.amount,
        p.transaction_id,
      ]
    )
  return output


def generate_payments_excel(seller: CustomUser) -> io.BytesIO:
  """Genera reporte en Excel (.xlsx) con estilos."""
  payments = Payment.objects.filter(seller=seller, state=True).order_by('-id')
  wb = Workbook()
  ws = wb.active
  ws.title = 'Ventas'
  headers = ['FECHA', 'CLIENTE', 'IDENTIFICACIÓN', 'CORREO', 'TOTAL', 'ID TRANSACCIÓN']
  ws.append(headers)

  for cell in ws[1]:
    cell.font = Font(bold=True, color='FFFFFF')
    cell.fill = PatternFill(start_color='007bff', end_color='007bff', fill_type='solid')

  for p in payments:
    ws.append(
      [
        p.link.created_at.strftime('%Y-%m-%d') if p.link else '',
        f'{p.first_name} {p.last_name}',
        p.identify,
        p.email,
        float(p.amount),
        p.transaction_id,
      ]
    )

  output = io.BytesIO()
  wb.save(output)
  output.seek(0)
  return output


@transaction.atomic
def request_refund(seller: CustomUser, payment: Payment, description: str) -> Refund:
  """Crea una solicitud de reembolso para un pago específico."""
  payment = Payment.objects.select_for_update().get(pk=payment.pk)
  if payment.seller_id != seller.pk:
    raise ValueError('No tiene permisos sobre este pago.')
  if payment.status != Payment.PaymentStatus.PAID:
    raise ValueError('Solo se pueden reembolsar pagos confirmados.')
  if hasattr(payment, 'refund'):
    raise ValueError('Este pago ya tiene una solicitud de reembolso.')

  return Refund.objects.create(seller=seller, payment=payment, description=description, amount=payment.amount)


def _lock_refund(refund_id):
  # Payment first, then refund, then seller: compatible with payment credit.
  # Payout approval locks its own request then seller, never a payment/refund.
  payment_id = Refund.objects.values_list('payment_id', flat=True).get(pk=refund_id)
  payment = Payment.objects.select_for_update().get(pk=payment_id)
  refund = Refund.objects.select_for_update().get(pk=refund_id)
  return payment, refund


def _refund_binding_valid(payment, refund):
  from gateways.services import DatafastClient

  return (
    payment.status == Payment.PaymentStatus.PAID
    and payment.seller_id is not None
    and payment.seller_id == refund.seller_id
    and refund.amount == payment.amount
    and DatafastClient._refund_amount_is_valid(refund.amount)
    and DatafastClient._refund_id_is_safe(payment.transaction_id)
  )


def _record_refund(refund, state, outcome, reason, code=''):
  """Persist only bounded internal reasons and validated identifiers/codes."""
  refund.status = state
  refund.provider_outcome = outcome
  refund.result_code = code
  refund.history = [
    *refund.history,
    {'at': timezone.now().isoformat(), 'state': state, 'outcome': outcome, 'reason': reason, 'code': code},
  ]
  refund.save()


def _bound_refund_result(payment, refund, result):
  from gateways.services import DatafastClient

  if not isinstance(result, dict):
    return False
  refund_id = result.get('refund_id')
  code = result.get('code')
  return (
    DatafastClient._refund_id_is_safe(refund_id)
    and result.get('original_id') == refund.original_transaction_id == payment.transaction_id
    and refund_id != payment.transaction_id
    and refund.provider_refund_id in (None, refund_id)
    and not Refund.objects.exclude(pk=refund.pk).filter(provider_refund_id=refund_id).exists()
    and not Payment.objects.filter(transaction_id=refund_id).exists()
    and DatafastClient._refund_amount_is_valid(result.get('amount'))
    and result.get('amount') == refund.held_amount == refund.amount == payment.amount
    and result.get('currency') == 'USD'
    and isinstance(code, str)
    and re.fullmatch(r'\d{3}\.\d{3}\.\d{3}', code) is not None
    and result.get('outcome') in ('CONFIRMED', 'DECLINED', 'UNKNOWN')
  )


@transaction.atomic
def settle_refund(refund_id: int, result: Any) -> Refund:
  """Internal T4 settlement seam: trusted normalized observations, never RF I/O.

  Only a bound open reservation can move money. Terminal/legacy records are
  immutable here. UNKNOWN/PROCESSING are not permission to send another RF.
  """
  payment, refund = _lock_refund(refund_id)
  if refund.status not in ('PROCESSING', 'UNKNOWN'):
    return refund
  if not _refund_binding_valid(payment, refund) or refund.held_amount != refund.amount:
    _record_refund(refund, 'UNKNOWN', 'UNKNOWN', 'reservation_binding_invalid')
    return refund
  if not _bound_refund_result(payment, refund, result):
    _record_refund(refund, 'UNKNOWN', 'UNKNOWN', 'unavailable_or_unbound_result')
    return refund
  code = result['code']
  success_codes = {'000.000.000'}
  if urlsplit(settings.DATAFAST_BASE_URL).netloc == 'eu-test.oppwa.com' and settings.DATAFAST_TEST_MODE == 'EXTERNAL':
    success_codes.add('000.100.112')
  outcome = result['outcome']
  if not ((outcome == 'CONFIRMED' and code in success_codes) or (outcome == 'DECLINED' and code == '800.100.174')):
    refund.provider_refund_id = result['refund_id']
    _record_refund(refund, 'UNKNOWN', 'UNKNOWN', 'non_final_result', code)
    return refund
  seller = CustomUser.objects.select_for_update().get(pk=refund.seller_id)
  refund.provider_refund_id = result['refund_id']
  refund.processed_by = refund.initiated_by
  refund.processed_at = timezone.now()
  if outcome == 'CONFIRMED':
    # Reservation already debited gross. Preserve Sale and earned commission.
    payment.status = Payment.PaymentStatus.REFUNDED
    payment.state = False
    payment.save(update_fields=['status', 'state'])
    state = 'APPROVED'
  else:
    seller.available_balance += refund.held_amount
    seller.save(update_fields=['available_balance'])
    state = 'REJECTED'
  refund.held_amount = Decimal('0.00')
  _record_refund(refund, state, outcome, 'provider_settled', code)
  return refund


def approve_refund_logic(refund_id: int, admin_user: Any, gateway=None) -> Refund:
  """Commit gross reservation, send one RF outside locks, then settle separately."""
  from gateways.services import DatafastClient

  # An outer transaction would hide the hold from payouts during provider I/O.
  if connection.in_atomic_block or not connection.get_autocommit():
    raise ValueError('El reembolso requiere una transacción independiente.')
  with transaction.atomic():
    payment, refund = _lock_refund(refund_id)
    if refund.status != Refund.RefundStatus.PENDING or refund.held_amount:
      raise ValueError('Este reembolso ya está procesado o en revisión. No reenviar.')
    if not _refund_binding_valid(payment, refund):
      raise ValueError('El reembolso no corresponde a un pago confirmado válido.')
    seller = CustomUser.objects.select_for_update().get(pk=refund.seller_id)
    if seller.available_balance < refund.amount:
      raise ValueError('Saldo insuficiente: se requiere el monto total del pago para reembolsar.')
    seller.available_balance -= refund.amount
    seller.save(update_fields=['available_balance'])
    refund.held_amount = refund.amount
    refund.original_transaction_id = payment.transaction_id
    refund.initiated_by = admin_user
    refund.initiated_at = timezone.now()
    _record_refund(refund, 'PROCESSING', '', 'gross_reserved')

  try:
    result = (gateway or DatafastClient()).refund_payment(refund.original_transaction_id, refund.amount)
  except Exception:
    # Exception text/payloads may contain credentials. Never persist or show them.
    result = {'outcome': 'UNKNOWN'}
  try:
    return settle_refund(refund.pk, result)
  except Exception:
    # Even a DB failure after RF must leave the committed PROCESSING hold intact.
    # Never resend, release, or claim approval based on an in-memory response.
    logger.warning('Refund %s settlement unavailable; reconciliation required', refund.pk)
    return Refund.objects.get(pk=refund.pk)


def get_seller_stats(seller: CustomUser) -> dict[str, Any]:
  """Estadísticas del Dashboard incluyendo KPIs financieros."""
  today = timezone.now().date()

  links_count = Link.objects.filter(seller=seller).count()

  # Ventas totales históricas (Pagadas)
  sales_agg = Payment.objects.filter(seller=seller, state=True).aggregate(total=Sum('amount'))
  total_sales = sales_agg['total'] or Decimal('0.00')

  # Ventas del día
  daily_sales_agg = Payment.objects.filter(seller=seller, state=True, link__created_at__date=today).aggregate(
    total=Sum('amount')
  )
  daily_sales = daily_sales_agg['total'] or Decimal('0.00')

  # Reembolsos totales
  refunds_agg = Refund.objects.filter(seller=seller, status=Refund.RefundStatus.APPROVED).aggregate(total=Sum('amount'))
  total_refunds = refunds_agg['total'] or Decimal('0.00')

  return {
    'links_count': links_count,
    'total_sales': total_sales,
    'daily_sales': daily_sales,
    'total_refunds': total_refunds,
    'available_balance': seller.available_balance,
    'active': seller.state,
    'email_active': seller.email_active,
    'seller_name': seller.user.first_name,
  }
