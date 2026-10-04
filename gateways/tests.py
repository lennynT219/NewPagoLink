from decimal import Decimal
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings
from gateways.services import DatafastClient


@override_settings(DATAFAST_BASE_URL='https://eu-prod.oppwa.com/v1/',
  DATAFAST_AUTH_TOKEN='mock-token', DATAFAST_ENTITY_ID='mock-entity',
  DATAFAST_MID='mock-mid', DATAFAST_TID='mock-tid', DATAFAST_TEST_MODE='')
class DatafastStatusTests(SimpleTestCase):
  def test_status_path_must_be_canonical(self):
    client = DatafastClient()
    for path in ['https://example.invalid', '//example.invalid/payment',
      '/v1/checkouts/id/payment?entityId=other', '/v1/checkouts/../payment',
      '/v1/checkouts/id/payment#x', '/v1/checkouts/id/payment/']:
      with self.subTest(path=path), patch('gateways.services.requests.get') as get:
        with self.assertRaises(ValueError):
          client.get_payment_status(path)
        get.assert_not_called()

  def test_status_fetches_canonical_endpoint_without_redirects(self):
    response = Mock(status_code=200)
    response.json.return_value = {'result': {'code': '000.000.000'}}
    with patch('gateways.services.requests.get', return_value=response) as get:
      result = DatafastClient().get_payment_status('/v1/checkouts/id-123/payment')
    self.assertEqual(result, response.json.return_value)
    self.assertEqual(get.call_args.args[0],
      'https://eu-prod.oppwa.com/v1/checkouts/id-123/payment')
    self.assertFalse(get.call_args.kwargs['allow_redirects'])

  def test_checkout_forwards_reserved_merchant_and_gross(self):
    response = Mock()
    response.json.return_value = {'id': 'checkout-123'}
    with patch('gateways.services.requests.post', return_value=response) as post:
      checkout = DatafastClient().prepare_checkout(Decimal('100'), Decimal('100'),
        Decimal('0'), True, 'PAY-reserved-unique', {}, '127.0.0.1')
    self.assertEqual(checkout, 'checkout-123')
    payload = post.call_args.kwargs['data']
    self.assertEqual(payload['merchantTransactionId'], 'PAY-reserved-unique')
    self.assertEqual(payload['amount'], '100.00')
    self.assertEqual(payload['currency'], 'USD')
    self.assertEqual(payload['paymentType'], 'DB')

  def test_redirect_or_http_failure_cannot_supply_an_approval(self):
    for status in (302, 503):
      response = Mock(status_code=status)
      response.json.return_value = {'result': {'code': '000.000.000'}}
      with self.subTest(status=status), patch('gateways.services.requests.get', return_value=response):
        result = DatafastClient().get_payment_status('/v1/checkouts/id/payment')
        self.assertEqual(result, {'outcome': 'UNKNOWN'})
        response.json.assert_not_called()

  def test_unavailable_and_malformed_are_explicitly_unknown(self):
    with patch('gateways.services.requests.get', side_effect=requests.Timeout):
      result = DatafastClient().get_payment_status('/v1/checkouts/id/payment')
    self.assertEqual(result, {'outcome': 'UNKNOWN'})
    response = Mock(status_code=200)
    response.json.return_value = []
    with patch('gateways.services.requests.get', return_value=response):
      result = DatafastClient().get_payment_status('/v1/checkouts/id/payment')
    self.assertEqual(result, {'outcome': 'UNKNOWN'})
