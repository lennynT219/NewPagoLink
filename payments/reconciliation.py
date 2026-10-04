"""GET-only reconciliation. Recognized layouts are not provider certification.

Unbound, unavailable or ambiguous observations cause no accounting writes.
Existing atomic settlers revalidate state after the unlocked provider request.
"""

import re
from decimal import Decimal

from django.db import connection
from django.db.models import F

from gateways.services import DatafastClient
from payments.models import PaymentAttempt, Refund
from payments.services import process_payment_result, settle_refund

MAX_LIMIT = 200
MAX_QUERY_RECORDS = 100
ATTEMPT_STATES = ('CREATING', 'LIVE', 'UNKNOWN', 'EXPIRED')
# Unknown metadata (including pagination) is deliberately unsupported.
RECORD_FIELDS = {
  'id',
  'merchantTransactionId',
  'paymentType',
  'amount',
  'currency',
  'result',
  'referencedId',
  'referencedid',
  'resultDetails',
  'timestamp',
  'paymentBrand',
  'descriptor',
}


def _merchant_valid(value):
  return (
    isinstance(value, str)
    and value == value.strip()
    and 0 < len(value) <= 255
    and not any(ord(char) < 32 for char in value)
  )


def _complete_record(data):
  if not isinstance(data, dict) or not set(data) <= RECORD_FIELDS:
    return False
  if not DatafastClient._refund_id_is_safe(data.get('id')):
    return False
  if data.get('paymentType') not in ('DB', 'RF') or data.get('currency') != 'USD':
    return False
  raw_amount = data.get('amount')
  if isinstance(raw_amount, bool) or not isinstance(raw_amount, (str, int, Decimal)):
    return False
  try:
    if not DatafastClient._refund_amount_is_valid(Decimal(raw_amount)):
      return False
  except (ValueError, ArithmeticError):
    return False
  result = data.get('result')
  if not isinstance(result, dict):
    return False
  code = result.get('code')
  if (
    not isinstance(code, str)
    or not re.fullmatch(r'\d{3}\.\d{3}\.\d{3}', code)
    or not set(result) <= {'code', 'description'}
  ):
    return False
  if 'merchantTransactionId' in data and not _merchant_valid(data['merchantTransactionId']):
    return False
  if data['paymentType'] == 'DB':
    return _merchant_valid(data.get('merchantTransactionId')) and not ('referencedId' in data or 'referencedid' in data)
  reference = data.get('referencedId', data.get('referencedid'))
  return (
    DatafastClient._refund_id_is_safe(reference)
    and reference != data['id']
    and not ('referencedId' in data and 'referencedid' in data and data['referencedId'] != data['referencedid'])
  )


def _candidate(payload, payment_type):
  """Require one complete target-type record; never choose first or latest."""
  if not isinstance(payload, dict):
    return None
  if 'payments' in payload:
    if not set(payload) <= {'payments', 'result'}:
      return None
    if 'result' in payload:
      result = payload['result']
      if (
        not isinstance(result, dict)
        or result.get('code') != '000.000.000'
        or not set(result) <= {'code', 'description'}
      ):
        return None
    records = payload['payments']
    if not isinstance(records, list) or not 0 < len(records) <= MAX_QUERY_RECORDS:
      return None
  else:
    records = [payload]
  if not all(_complete_record(record) for record in records):
    return None
  if len({record['id'] for record in records}) != len(records):
    return None
  candidates = [record for record in records if record['paymentType'] == payment_type]
  return candidates[0] if len(candidates) == 1 else None


def _validate_scope(ids):
  if ids is not None and (
    len(ids) > MAX_LIMIT or any(isinstance(pk, bool) or not isinstance(pk, int) or pk < 1 for pk in ids)
  ):
    raise ValueError('Scopes require at most 200 positive internal IDs')


def select_eligible(limit=50, attempt_ids=None, refund_ids=None):
  """Stable, globally bounded selection; terminal/historical rows are excluded."""
  if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
    raise ValueError('Limit must be between 1 and 200')
  _validate_scope(attempt_ids)
  _validate_scope(refund_ids)
  attempts = PaymentAttempt.objects.filter(
    state__in=ATTEMPT_STATES, payment__status='PENDING', payment__state=False, payment__sale_record__isnull=True
  ).select_related('payment')
  refunds = Refund.objects.filter(
    status__in=('PROCESSING', 'UNKNOWN'),
    held_amount__gt=0,
    held_amount=F('amount'),
    amount=F('payment__amount'),
    payment__status='PAID',
  ).select_related('payment')
  scoped = attempt_ids is not None or refund_ids is not None
  if scoped:
    attempts = attempts.filter(pk__in=attempt_ids or [])
    refunds = refunds.filter(pk__in=refund_ids or [])
  chosen_attempts = list(attempts.order_by('pk')[:limit])
  chosen_refunds = list(refunds.order_by('pk')[: limit - len(chosen_attempts)])
  return [*chosen_attempts, *chosen_refunds]


def _identity(item):
  if isinstance(item, PaymentAttempt):
    if not item.checkout_id or not _merchant_valid(item.merchant_transaction_id):
      return None
    if item.provider_transaction_id is not None:
      return ('provider', item.provider_transaction_id, item.merchant_transaction_id)
    return ('merchant', item.merchant_transaction_id, item.merchant_transaction_id)
  payment = item.payment
  if (
    not DatafastClient._refund_id_is_safe(item.original_transaction_id)
    or item.original_transaction_id != payment.transaction_id
    or item.seller_id != payment.seller_id
    or item.seller_id is None
  ):
    return None
  if item.provider_refund_id is not None:
    return ('provider', item.provider_refund_id, None)
  # No merchant ID is stored on Refund. Only the exact successful DB attempt
  # can supply it. Legacy payments without that provenance stay unresolved.
  bound = list(
    PaymentAttempt.objects.filter(
      payment_id=item.payment_id,
      state='SUCCEEDED',
      provider_transaction_id=item.original_transaction_id,
      amount=item.amount,
      currency='USD',
      checkout_id__isnull=False,
    ).order_by('pk')[:2]
  )
  if len(bound) != 1 or not _merchant_valid(bound[0].merchant_transaction_id):
    return None
  merchant = bound[0].merchant_transaction_id
  return ('merchant', merchant, merchant)


def _observe(item, identity, gateway):
  mode, value, merchant = identity
  if mode == 'provider' and not DatafastClient._refund_id_is_safe(value):
    return None
  payload = gateway.query_by_provider_id(value) if mode == 'provider' else gateway.query_by_merchant_id(value)
  is_attempt = isinstance(item, PaymentAttempt)
  record = _candidate(payload, 'DB' if is_attempt else 'RF')
  if record is None or (mode == 'provider' and record['id'] != value):
    return None
  if merchant is not None and record.get('merchantTransactionId') != merchant:
    return None
  if Decimal(record['amount']) != item.amount:
    return None
  if is_attempt:
    if item.currency != 'USD' or item.amount != item.payment.amount:
      return None
    # Forward only validated binding fields, not customer/resultDetails data.
    observation = {key: record[key] for key in ('id', 'merchantTransactionId', 'amount', 'currency', 'paymentType')}
    observation['result'] = {'code': record['result']['code']}
    return observation
  normalized = gateway.normalize_refund_observation(record, item.original_transaction_id, item.amount)
  return normalized if isinstance(normalized, dict) and 'refund_id' in normalized else None


def reconcile(limit=50, apply=False, attempt_ids=None, refund_ids=None, gateway=None):
  """Default is read-only and does not even instantiate the provider client."""
  if apply and (connection.in_atomic_block or not connection.get_autocommit()):
    raise ValueError('Reconciliation requires an independent transaction')
  output = []
  for item in select_eligible(limit, attempt_ids, refund_ids):
    kind = 'attempt' if isinstance(item, PaymentAttempt) else 'refund'
    status = item.state if isinstance(item, PaymentAttempt) else item.status
    reason = 'eligible_dry_run'
    if apply:
      identity = _identity(item)
      reason = 'identity_unavailable'
      if identity is not None:
        try:
          if gateway is None:
            gateway = DatafastClient()
          observation = _observe(item, identity, gateway)
          reason = 'query_unresolved'
          if observation is not None:
            if isinstance(item, PaymentAttempt):
              process_payment_result(item.payment.pk, observation, attempt_id=item.pk)
              item.refresh_from_db()
              status = item.state
            else:
              settled = settle_refund(item.pk, observation)
              status = settled.status
            reason = 'settled' if status in ('SUCCEEDED', 'DECLINED', 'APPROVED', 'REJECTED') else 'non_final'
        except Exception:  # noqa: BLE001 - unknown I/O/settlement failures must retain holds
          # Exception text can contain provider/customer data. Never emit it.
          reason = 'observation_or_settlement_unavailable'
    output.append({'kind': kind, 'id': item.pk, 'status': status, 'reason': reason})
  return output
