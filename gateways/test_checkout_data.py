"""Synthetic payer fixtures only; all provider I/O is mocked."""

from decimal import Decimal
from typing import Any
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from gateways.services import DatafastClient


def synthetic_payer() -> dict[str, Any]:
  return {
    'first_name': 'Prueba',
    'buyer_middle_name': 'Segundo',
    'last_name': 'Sintetico',
    'email': 'payer@example.invalid',
    'identify': '1234567890001',
    'phone': '023456789',
    'billing_street': 'Calle de prueba 123',
    'shipping_street': 'Entrega de prueba 456',
    'billing_country': 'EC',
    'shipping_country': 'CL',
    'merchant_customer_id': '12345',
  }


@override_settings(DEBUG=False)
class CheckoutDataTests(SimpleTestCase):
  def prepare(self, payer, ip: Any = '198.51.100.42'):
    return DatafastClient().prepare_checkout(
      Decimal(115),
      Decimal(100),
      Decimal(15),
      False,
      'PAY-synthetic-unique',
      payer,
      ip,
      product_description='Recorded service',
    )

  def test_missing_mandatory_payer_fields_never_post(self):
    for key in synthetic_payer():
      data = synthetic_payer()
      del data[key]
      with self.subTest(field=key), patch('gateways.services.requests.post') as post:
        with self.assertRaises(ValueError):
          self.prepare(data)
        post.assert_not_called()

  def test_exact_actual_payer_fields_forwarded(self):
    response = Mock(status_code=200)
    response.json.return_value = {'id': 'synthetic-checkout'}
    with patch('gateways.services.requests.post', return_value=response) as post:
      self.assertEqual(self.prepare(synthetic_payer()), 'synthetic-checkout')
    payload = post.call_args.kwargs['data']
    for field, value in {
      'customer.givenName': 'Prueba',
      'customer.middleName': 'Segundo',
      'customer.surname': 'Sintetico',
      'customer.email': 'payer@example.invalid',
      'customer.identificationDocId': '1234567890',
      'customer.phone': '023456789',
      'customer.ip': '198.51.100.42',
      'customer.merchantCustomerId': '12345',
      'billing.street1': 'Calle de prueba 123',
      'shipping.street1': 'Entrega de prueba 456',
      'billing.country': 'EC',
      'shipping.country': 'CL',
    }.items():
      self.assertEqual(payload[field], value)
    self.assertNotIn('billing.city', payload)
    self.assertNotIn('billing.postcode', payload)
    self.assertEqual(payload['amount'], '115.00')

  def test_invalid_types_lengths_and_placeholders_never_post(self):
    bounds = {
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
      'merchant_customer_id': (1, 16),
    }
    for key, (minimum, maximum) in bounds.items():
      placeholders = () if key.endswith('_country') else ('SN', 'NA')
      for value in (None, 123, True, [], {}, '', 'x' * (minimum - 1), 'x' * (maximum + 1), *placeholders):
        data = synthetic_payer()
        data[key] = value
        with self.subTest(field=key, value=value), patch('gateways.services.requests.post') as post:
          expected = ValueError if value is None or isinstance(value, str) else TypeError
          with self.assertRaises(expected):
            self.prepare(data)
          post.assert_not_called()

  def test_document_padding_and_reject_unsupported_lengths(self):
    for raw, normalized in [('ABC123', '0000ABC123'), ('1234567890', '1234567890')]:
      data = synthetic_payer()
      data['identify'] = raw
      response = Mock(status_code=200)
      response.json.return_value = {'id': 'synthetic-checkout'}
      with patch('gateways.services.requests.post', return_value=response) as post:
        self.prepare(data)
      self.assertEqual(post.call_args.kwargs['data']['customer.identificationDocId'], normalized)
    for value in ('12345678901', '123456789012', 'ABCDEFGHIJKLM', '0000000000'):
      data = synthetic_payer()
      data['identify'] = value
      with patch('gateways.services.requests.post') as post:
        with self.assertRaises(ValueError):
          self.prepare(data)
        post.assert_not_called()

  def test_complete_iso_country_set_and_actual_codes(self):
    from gateways.services import COUNTRY_CODES

    self.assertEqual(len(COUNTRY_CODES), 249)
    for country in ('AD', 'BZ', 'SN', 'NA', 'EC', 'US', 'DE', 'JP', 'AU', 'AQ'):
      data = synthetic_payer()
      data['billing_country'] = country
      data['shipping_country'] = country
      response = Mock(status_code=200)
      response.json.return_value = {'id': 'synthetic-checkout'}
      with self.subTest(country=country), patch('gateways.services.requests.post', return_value=response) as post:
        self.prepare(data)
      self.assertEqual(post.call_args.kwargs['data']['billing.country'], country)
      self.assertEqual(post.call_args.kwargs['data']['shipping.country'], country)
    for country in ('ZZ', 'ec', ' EC', 'EC ', 'E1', 'XX', 'USA'):
      for key in ('billing_country', 'shipping_country'):
        data = synthetic_payer()
        data[key] = country
        with self.subTest(country=country, field=key), patch('gateways.services.requests.post') as post:
          with self.assertRaises(ValueError):
            self.prepare(data)
          post.assert_not_called()

  def test_non_dictionary_payer_raises_type_error_before_io(self):
    for payer in ([], 'payer', 123):
      with self.subTest(payer=payer), patch('gateways.services.requests.post') as post:
        with self.assertRaises(TypeError):
          self.prepare(payer)
        post.assert_not_called()

  def test_invalid_ip_never_post(self):
    for ip in (None, 123, '', 'bad', '198.51.100.42, 1.1.1.1', '127.0.0.1', '::1', '0.0.0.0', '::', 'fe80::1%eth0'):
      with self.subTest(ip=ip), patch('gateways.services.requests.post') as post:
        expected = TypeError if isinstance(ip, int) else ValueError
        with self.assertRaises(expected):
          self.prepare(synthetic_payer(), ip)
        post.assert_not_called()
