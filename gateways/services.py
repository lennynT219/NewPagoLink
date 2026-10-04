import ipaddress
import logging
import re
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Shared by the public form and the service/SDK boundaries. Never log values.
PAYER_LIMITS = {
  'first_name': (3, 48),
  'buyer_middle_name': (2, 50),
  'last_name': (3, 48),
  'email': (6, 128),
  'identify': (1, 13),
  'phone': (7, 15),
  'billing_street': (1, 100),
  'shipping_street': (1, 100),
  'billing_country': (2, 2),
  'shipping_country': (2, 2),
}
PLACEHOLDERS = {
  'sn',
  's/n',
  'na',
  'n/a',
  'cliente',
  'pagolink',
  'ecuador main street',
  'ecuador delivery street',
  '0999999999',
  '0000000000',
}
# ISO 3166-1 alpha-2 codes, not a default country inferred from the merchant.
COUNTRY_CODES = {
  'AD',
  'AE',
  'AF',
  'AG',
  'AI',
  'AL',
  'AM',
  'AO',
  'AQ',
  'AR',
  'AS',
  'AT',
  'AU',
  'AW',
  'AX',
  'AZ',
  'BA',
  'BB',
  'BD',
  'BE',
  'BF',
  'BG',
  'BH',
  'BI',
  'BJ',
  'BL',
  'BM',
  'BN',
  'BO',
  'BQ',
  'BR',
  'BS',
  'BT',
  'BV',
  'BW',
  'BY',
  'BZ',
  'CA',
  'CC',
  'CD',
  'CF',
  'CG',
  'CH',
  'CI',
  'CK',
  'CL',
  'CM',
  'CN',
  'CO',
  'CR',
  'CU',
  'CV',
  'CW',
  'CX',
  'CY',
  'CZ',
  'DE',
  'DJ',
  'DK',
  'DM',
  'DO',
  'DZ',
  'EC',
  'EE',
  'EG',
  'EH',
  'ER',
  'ES',
  'ET',
  'FI',
  'FJ',
  'FK',
  'FM',
  'FO',
  'FR',
  'GA',
  'GB',
  'GD',
  'GE',
  'GF',
  'GG',
  'GH',
  'GI',
  'GL',
  'GM',
  'GN',
  'GP',
  'GQ',
  'GR',
  'GS',
  'GT',
  'GU',
  'GW',
  'GY',
  'HK',
  'HM',
  'HN',
  'HR',
  'HT',
  'HU',
  'ID',
  'IE',
  'IL',
  'IM',
  'IN',
  'IO',
  'IQ',
  'IR',
  'IS',
  'IT',
  'JE',
  'JM',
  'JO',
  'JP',
  'KE',
  'KG',
  'KH',
  'KI',
  'KM',
  'KN',
  'KP',
  'KR',
  'KW',
  'KY',
  'KZ',
  'LA',
  'LB',
  'LC',
  'LI',
  'LK',
  'LR',
  'LS',
  'LT',
  'LU',
  'LV',
  'LY',
  'MA',
  'MC',
  'MD',
  'ME',
  'MF',
  'MG',
  'MH',
  'MK',
  'ML',
  'MM',
  'MN',
  'MO',
  'MP',
  'MQ',
  'MR',
  'MS',
  'MT',
  'MU',
  'MV',
  'MW',
  'MX',
  'MY',
  'MZ',
  'NA',
  'NC',
  'NE',
  'NF',
  'NG',
  'NI',
  'NL',
  'NO',
  'NP',
  'NR',
  'NU',
  'NZ',
  'OM',
  'PA',
  'PE',
  'PF',
  'PG',
  'PH',
  'PK',
  'PL',
  'PM',
  'PN',
  'PR',
  'PS',
  'PT',
  'PW',
  'PY',
  'QA',
  'RE',
  'RO',
  'RS',
  'RU',
  'RW',
  'SA',
  'SB',
  'SC',
  'SD',
  'SE',
  'SG',
  'SH',
  'SI',
  'SJ',
  'SK',
  'SL',
  'SM',
  'SN',
  'SO',
  'SR',
  'SS',
  'ST',
  'SV',
  'SX',
  'SY',
  'SZ',
  'TC',
  'TD',
  'TF',
  'TG',
  'TH',
  'TJ',
  'TK',
  'TL',
  'TM',
  'TN',
  'TO',
  'TR',
  'TT',
  'TV',
  'TW',
  'TZ',
  'UA',
  'UG',
  'UM',
  'US',
  'UY',
  'UZ',
  'VA',
  'VC',
  'VE',
  'VG',
  'VI',
  'VN',
  'VU',
  'WF',
  'WS',
  'YE',
  'YT',
  'ZA',
  'ZM',
  'ZW',
}


def validate_payer_field(key, value):
  minimum, maximum = PAYER_LIMITS[key]
  if value is None:
    raise ValueError('Complete los datos obligatorios del pagador.')
  if not isinstance(value, str):
    raise TypeError('Los datos del pagador deben ser texto.')
  if not minimum <= len(value) <= maximum or value != value.strip():
    raise ValueError('Complete los datos obligatorios del pagador con la longitud indicada.')
  if not value.isprintable() or (
    key not in ('billing_country', 'shipping_country') and value.casefold() in PLACEHOLDERS
  ):
    raise ValueError('Ingrese datos reales del pagador, sin valores por defecto.')
  if key in ('first_name', 'buyer_middle_name', 'last_name') and not all(
    char.isalnum() or char == ' ' for char in value
  ):
    raise ValueError('Ingrese nombres y apellidos alfanuméricos reales.')
  if key == 'email':
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    try:
      validate_email(value)
    except ValidationError as exc:
      raise ValueError('Ingrese un correo electrónico válido.') from exc
  if key == 'identify' and (
    not value.isascii() or not value.isalnum() or (len(value) > 10 and (len(value) != 13 or not value.isdecimal()))
  ):
    raise ValueError('Ingrese un documento de hasta 10 caracteres o un RUC de 13 dígitos.')
  if key == 'phone' and not all(char.isalnum() or char in '+ -()' for char in value):
    raise ValueError('Ingrese un teléfono válido.')
  if key.endswith('_country') and value not in COUNTRY_CODES:
    raise ValueError('Seleccione el código ISO de país de dos letras mayúsculas.')
  return value


def validate_client_ip(value):
  if value is None:
    raise ValueError('No se pudo verificar la dirección IP del pagador.')
  if not isinstance(value, str):
    raise TypeError('La dirección IP del pagador debe ser texto.')
  try:
    if value != value.strip() or '%' in value:
      raise ValueError
    address = ipaddress.ip_address(value)
    effective = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address
    # Development tests may use documentation-only IPs; strict profiles may not.
    if effective.is_loopback or effective.is_unspecified or effective.is_multicast or effective.is_link_local:
      raise ValueError
    if settings.STRICT_PROFILE and not effective.is_global:
      raise ValueError
  except ValueError as exc:
    raise ValueError('No se pudo verificar la dirección IP del pagador.') from exc
  return str(address)


def validate_checkout_payer(customer_data, client_ip):
  if customer_data is None:
    raise ValueError('Complete los datos obligatorios del pagador.')
  if not isinstance(customer_data, dict):
    raise TypeError('Los datos del pagador deben ser un diccionario.')
  for key in PAYER_LIMITS:
    validate_payer_field(key, customer_data.get(key))
  reference = customer_data.get('merchant_customer_id')
  if reference is None:
    raise ValueError('Referencia interna del pagador inválida.')
  if not isinstance(reference, str):
    raise TypeError('La referencia interna del pagador debe ser texto.')
  if not re.fullmatch(r'[1-9][0-9]{0,15}', reference):
    raise ValueError('Referencia interna del pagador inválida.')
  validate_client_ip(client_ip)


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
    validate_checkout_payer(customer_data, client_ip)
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
      base_imp = Decimal('0.00')  # noqa: F841 -- Preserve the existing calculation for T5b2 tax payload work.
      base_0 = subtotal  # noqa: F841 -- Preserve the existing calculation for T5b2 tax payload work.
      val_iva = Decimal('0.00')  # noqa: F841 -- Preserve the existing calculation for T5b2 tax payload work.

    payload = {
      'entityId': self.entity_id,
      'amount': f'{amount:.2f}',
      'currency': 'USD',
      'paymentType': 'DB',
      'merchantTransactionId': transaction_id,
      # Datos del Cliente (Obligatorios Fase 2)
      'customer.givenName': customer_data['first_name'],
      'customer.middleName': customer_data['buyer_middle_name'],
      'customer.surname': customer_data['last_name'],
      'customer.email': customer_data['email'],
      'customer.merchantCustomerId': customer_data['merchant_customer_id'],
      'customer.ip': client_ip,
      'customer.identificationDocType': 'IDCARD',
      'customer.identificationDocId': customer_data['identify'][:10].zfill(10),
      'customer.phone': customer_data['phone'],
      # Direcciones (Obligatorios)
      'billing.street1': customer_data['billing_street'],
      'billing.country': customer_data['billing_country'],
      'shipping.street1': customer_data['shipping_street'],
      'shipping.country': customer_data['shipping_country'],
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
    except Exception:  # noqa: BLE001 -- Unknown provider errors must remain unresolved, retaining holds.
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
    except Exception:  # noqa: BLE001 -- Unknown provider errors must remain unresolved, retaining holds.
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

  def query_by_provider_id(self, provider_id: str) -> dict[str, Any]:
    """Query a stored transaction ID, never a caller-supplied URL."""
    if not self._refund_id_is_safe(provider_id):
      return {'outcome': 'UNKNOWN'}
    return self._query(f'/v1/query/{provider_id}', {'entityId': self.entity_id})

  def query_by_merchant_id(self, merchant_id: str) -> dict[str, Any]:
    """requests encodes the merchant identity as a query parameter, not a path."""
    if not isinstance(merchant_id, str) or not merchant_id.strip() or len(merchant_id) > 255:
      return {'outcome': 'UNKNOWN'}
    return self._query('/v1/query', {'entityId': self.entity_id, 'merchantTransactionId': merchant_id})

  def _query(self, path: str, params: dict[str, str]) -> dict[str, Any]:
    unknown = {'outcome': 'UNKNOWN'}
    try:
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
        return unknown
      token = self.auth_token.strip()
      headers = self._get_headers()
      headers['Authorization'] = token if token.startswith('Bearer ') else f'Bearer {token}'
      response = requests.get(
        f'https://{base.netloc}{path}', params=params, headers=headers, timeout=10, allow_redirects=False, verify=True
      )
      response.raise_for_status()
      if response.status_code != 200:
        return unknown
      data = response.json(parse_float=Decimal)
      return data if isinstance(data, dict) else unknown
    except (requests.RequestException, ValueError, TypeError, AttributeError, ArithmeticError):
      logger.warning('Datafast query unavailable; reconciliation unresolved')
      return unknown

  def normalize_refund_observation(self, data: Any, transaction_id: str, amount: Decimal) -> dict[str, Any]:
    """Shared strict RF binding for POST responses and complete query records."""
    unknown = {'outcome': 'UNKNOWN'}
    try:
      if not isinstance(data, dict):
        return unknown
      refund_id = data.get('id')
      original_id = data.get('referencedId', data.get('referencedid'))
      if 'referencedId' in data and 'referencedid' in data and data['referencedId'] != data['referencedid']:
        return unknown
      raw_amount = data.get('amount')
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
      sandbox = urlsplit(self.base_url).netloc == 'eu-test.oppwa.com' and self.test_mode == 'EXTERNAL'
      outcome = 'UNKNOWN'
      if code == '000.000.000' or (sandbox and code == '000.100.112'):
        outcome = 'CONFIRMED'
      elif code == '800.100.174':
        outcome = 'DECLINED'
      return {
        'outcome': outcome,
        'refund_id': refund_id,
        'original_id': original_id,
        'amount': returned_amount,
        'currency': 'USD',
        'code': code,
      }
    except (ValueError, TypeError, ArithmeticError):
      return unknown

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
      return self.normalize_refund_observation(data, transaction_id, amount)
    except (requests.RequestException, ValueError, TypeError, ArithmeticError):
      logger.warning('Datafast refund outcome unavailable; reconciliation required')
      return unknown
