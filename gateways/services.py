import logging
import re
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class DatafastClient:
  """
  Cliente técnico para la integración con Datafast (Ecuador) - Fase 2.
  Implementa el desglose de impuestos y parámetros de seguridad obligatorios.
  """

  def __init__(self):
    self.base_url = settings.DATAFAST_BASE_URL
    self.auth_token = settings.DATAFAST_AUTH_TOKEN
    self.entity_id = settings.DATAFAST_ENTITY_ID
    self.mid = settings.DATAFAST_MID
    self.tid = settings.DATAFAST_TID
    self.test_mode = settings.DATAFAST_TEST_MODE

  def _get_headers(self) -> dict[str, str]:
    return {'Authorization': self.auth_token, 'Content-Type': 'application/x-www-form-urlencoded'}

  def prepare_checkout(
    self,
    amount: Decimal,
    subtotal: Decimal,
    igv: Decimal,
    include_igv: bool,
    transaction_id: str,
    customer_data: dict[str, Any],
    client_ip: str,
  ) -> str | None:
    """
    Inicia una sesión de checkout (Fase 2) con desglose de impuestos.
    """
    url = f'{self.base_url}checkouts'

    # Lógica de Impuestos según Datafast Ecuador
    # SHOPPER_VAL_BASEIMP: Base que grava IVA
    # SHOPPER_VAL_BASE0: Base que NO grava IVA
    # SHOPPER_VAL_IVA: Valor del IVA calculado

    if igv > 0:
      base_imp = subtotal
      base_0 = Decimal('0.00')
      val_iva = igv
    else:
      base_imp = Decimal('0.00')
      base_0 = subtotal
      val_iva = Decimal('0.00')

    payload = {
      'entityId': self.entity_id,
      'amount': f'{amount:.2f}',
      'currency': 'USD',
      'paymentType': 'DB',
      'merchantTransactionId': transaction_id,
      # Datos del Cliente (Obligatorios Fase 2)
      'customer.givenName': customer_data.get('first_name', 'Cliente'),
      'customer.surname': customer_data.get('last_name', 'PagoLink'),
      'customer.email': customer_data.get('email', ''),
      'customer.ip': client_ip,
      'customer.identificationDocType': 'IDCARD',
      'customer.identificationDocId': str(customer_data.get('identify', ''))[:10],  # Max 10 caracteres
      'customer.phone': customer_data.get('phone', ''),
      # Direcciones (Obligatorios)
      'billing.street1': 'Ecuador Main Street',
      'billing.country': 'EC',
      'shipping.street1': 'Ecuador Delivery Street',
      'shipping.country': 'EC',
      # Parámetros Personalizados Datafast
      'customParameters[SHOPPER_MID]': self.mid,
      'customParameters[SHOPPER_TID]': self.tid,
      'customParameters[SHOPPER_VERSIONDF]': '2',
      # Parámetros de Riesgo
      'risk.parameters[USER_DATA2]': 'PagoLinkExpress',
    }

    # Modo de Prueba (Comentado si causa conflicto con este MID)
    # if self.test_mode:
    #   payload['testMode'] = self.test_mode

    try:
      response = requests.post(url, data=payload, headers=self._get_headers(), timeout=15)
      response.raise_for_status()
      data = response.json()

      checkout_id = data.get('id') if isinstance(data, dict) else None
      if isinstance(checkout_id, str) and re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,254}', checkout_id):
        return checkout_id
      logger.warning('Datafast checkout response unavailable or malformed')
      return None
    except Exception:
      logger.warning('Datafast checkout request unavailable')
      return None

  def get_payment_status(self, resource_path: str) -> dict[str, Any]:
    """Fetch a canonical path; the caller must additionally bind it to a payment."""
    if not isinstance(resource_path, str) or not re.fullmatch(
      r'/v1/checkouts/[A-Za-z0-9_-][A-Za-z0-9_.-]{0,254}/payment', resource_path
    ):
      raise ValueError('Invalid checkout result path')
    base = urlsplit(self.base_url)
    url = f'{base.scheme}://{base.netloc}{resource_path}'
    params = {'entityId': self.entity_id}
    try:
      response = requests.get(url, params=params, headers=self._get_headers(), timeout=10, allow_redirects=False)
      response.raise_for_status()
      if response.status_code != 200:
        return {'outcome': 'UNKNOWN'}
      data = response.json()
      return data if isinstance(data, dict) else {'outcome': 'UNKNOWN'}
    except Exception:
      logger.warning('Datafast result request unavailable')
      return {'outcome': 'UNKNOWN'}

  @staticmethod
  def _refund_id_is_safe(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,254}', value) is not None

  @staticmethod
  def _refund_amount_is_valid(value: Any) -> bool:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
      return False
    # Inspect digits, not quantize/multiply: Decimal context must not round
    # away a sub-cent difference, even beyond its configured precision.
    _, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
      return False
    excess = max(0, -exponent - 2)
    return excess == 0 or not any(digits[-excess:])

  def refund_payment(self, transaction_id: str, amount: Decimal) -> dict[str, Any]:
    """Send one RF request; UNKNOWN requires reconciliation, never blind retry.

    Invalid local parameters raise ValueError before I/O. This adapter has no
    accounting side effects; the caller owns reservation and finalization.
    """
    if not self._refund_id_is_safe(transaction_id):
      raise ValueError('Invalid refund transaction ID')
    if not self._refund_amount_is_valid(amount):
      raise ValueError('Refund amount must be a positive whole-cent Decimal')
    base = urlsplit(self.base_url)
    if (
      base.scheme != 'https'
      or not base.hostname
      or base.username is not None
      or base.password is not None
      or base.query
      or base.fragment
      or base.path not in ('', '/', '/v1', '/v1/')
    ):
      raise ValueError('Invalid refund endpoint configuration')
    url = f'https://{base.netloc}/v1/payments/{transaction_id}'
    sandbox = base.netloc == 'eu-test.oppwa.com' and self.test_mode == 'EXTERNAL'
    payload = {
      'entityId': self.entity_id,
      'amount': format(amount, '.2f'),
      'currency': 'USD',
      'paymentType': 'RF',
    }
    if sandbox:
      payload['testMode'] = 'EXTERNAL'
    headers = self._get_headers()
    token = self.auth_token.strip()
    headers['Authorization'] = token if token.startswith('Bearer ') else f'Bearer {token}'
    unknown = {'outcome': 'UNKNOWN'}
    try:
      # requests' default adapter does not retry; redirects are also disabled.
      response = requests.post(url, data=payload, headers=headers, timeout=10, allow_redirects=False, verify=True)
      response.raise_for_status()
      if response.status_code != 200:
        return unknown
      data = response.json(parse_float=Decimal)
      if not isinstance(data, dict):
        return unknown
      refund_id = data.get('id')
      original_id = data.get('referencedId', data.get('referencedid'))
      if 'referencedId' in data and 'referencedid' in data and data['referencedId'] != data['referencedid']:
        return unknown
      raw_amount = data.get('amount')
      # Reject binary floats even if a custom decoder supplies them.
      if isinstance(raw_amount, bool) or not isinstance(raw_amount, (str, int, Decimal)):
        return unknown
      returned_amount = Decimal(raw_amount)
      result = data.get('result')
      code = result.get('code') if isinstance(result, dict) else None
      if (
        not self._refund_id_is_safe(refund_id)
        or original_id != transaction_id
        or data.get('paymentType') != 'RF'
        or data.get('currency') != 'USD'
        or not self._refund_amount_is_valid(returned_amount)
        or returned_amount != amount
        or not isinstance(code, str)
        or not re.fullmatch(r'\d{3}\.\d{3}\.\d{3}', code)
      ):
        return unknown
      outcome = 'UNKNOWN'
      if code == '000.000.000' or (sandbox and code == '000.100.112'):
        outcome = 'CONFIRMED'
      elif code == '800.100.174':
        # Documented definitive invalid-amount decline; no broad code families.
        outcome = 'DECLINED'
      return {
        'outcome': outcome,
        'refund_id': refund_id,
        'original_id': original_id,
        'amount': returned_amount,
        'currency': 'USD',
        'code': code,
      }
    except (requests.RequestException, ValueError, TypeError, ArithmeticError):
      logger.warning('Datafast refund outcome unavailable; reconciliation required')
      return unknown
