from copy import deepcopy
from decimal import Decimal
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from gateways.services import DatafastClient


@override_settings(
  DATAFAST_BASE_URL='https://eu-prod.oppwa.com/v1/',
  DATAFAST_AUTH_TOKEN='test-token',
  DATAFAST_ENTITY_ID='test-entity',
  DATAFAST_MID='test-mid',
  DATAFAST_TID='test-tid',
  DATAFAST_TEST_MODE='',
)
class DatafastRefundTests(SimpleTestCase):
  def approved(self):
    return {
      'id': 'refund-123',
      'referencedId': 'original-123',
      'paymentType': 'RF',
      'amount': '10.00',
      'currency': 'USD',
      'result': {'code': '000.000.000', 'description': 'private'},
      'customer': {'email': 'private'},
      'card': {'number': 'private'},
    }

  def invoke(self, data, status=200):
    response = Mock(status_code=status)
    response.json.return_value = data
    with patch('gateways.services.requests.post', return_value=response) as post:
      result = DatafastClient().refund_payment('original-123', Decimal('10.00'))
    post.assert_called_once()
    return result, response, post

  def test_post_contract_and_safe_confirmed_result(self):
    result, response, post = self.invoke(self.approved())
    self.assertEqual(
      result,
      {
        'outcome': 'CONFIRMED',
        'refund_id': 'refund-123',
        'original_id': 'original-123',
        'amount': Decimal('10.00'),
        'currency': 'USD',
        'code': '000.000.000',
      },
    )
    self.assertEqual(post.call_args.args, ('https://eu-prod.oppwa.com/v1/payments/original-123',))
    self.assertEqual(
      post.call_args.kwargs,
      {
        'data': {'entityId': 'test-entity', 'amount': '10.00', 'currency': 'USD', 'paymentType': 'RF'},
        'headers': {'Authorization': 'Bearer test-token', 'Content-Type': 'application/x-www-form-urlencoded'},
        'timeout': 10,
        'allow_redirects': False,
        'verify': True,
      },
    )
    response.json.assert_called_once_with(parse_float=Decimal)

  def test_invalid_parameters_do_not_make_any_request(self):
    ids = [
      '',
      '.',
      '..',
      '../id',
      'id/path',
      'id?x=1',
      'id#x',
      '%2fid',
      '//evil',
      'https://evil',
      ' id',
      'id\n',
      None,
      123,
    ]
    amounts = [
      Decimal(0),
      Decimal(-1),
      Decimal('0.001'),
      Decimal('10.0000000000000000000000000001'),
      Decimal('NaN'),
      Decimal('Infinity'),
      Decimal('-Infinity'),
      10.0,
      10,
      '10.00',
      None,
      True,
    ]
    with patch('gateways.services.requests.post') as post, patch('gateways.services.requests.delete') as delete:
      for transaction_id in ids:
        with self.subTest(transaction_id=transaction_id), self.assertRaises(ValueError):
          DatafastClient().refund_payment(transaction_id, Decimal(10))
      for amount in amounts:
        with self.subTest(amount=amount), self.assertRaises(ValueError):
          DatafastClient().refund_payment('original-123', amount)
      post.assert_not_called()
      delete.assert_not_called()

  def test_unsafe_endpoint_configuration_is_rejected_before_io(self):
    for base in (
      'http://eu-test.oppwa.com/v1/',
      'https://user:password@eu-test.oppwa.com/v1/',
      'https://eu-test.oppwa.com/v1/?x=1',
      'https://eu-test.oppwa.com/v1/#fragment',
      'https://eu-test.oppwa.com/other/',
    ):
      with (
        self.subTest(base=base),
        override_settings(DATAFAST_BASE_URL=base),
        patch('gateways.services.requests.post') as post,
      ):
        with self.assertRaises(ValueError):
          DatafastClient().refund_payment('original-123', Decimal(10))
        post.assert_not_called()

  def test_real_json_numbers_preserve_subcent_precision(self):
    for literal, expected in [('10.00', 'CONFIRMED'), ('10.0000000000000000000000000001', 'UNKNOWN')]:
      response = requests.Response()
      response.status_code = 200
      response._content = (
        '{"id":"refund-123","referencedId":"original-123",'
        '"paymentType":"RF","currency":"USD",'
        '"result":{"code":"000.000.000"},"amount":' + literal + '}'
      ).encode('ascii')
      with self.subTest(literal=literal), patch('gateways.services.requests.post', return_value=response) as post:
        result = DatafastClient().refund_payment('original-123', Decimal(10))
        self.assertEqual(result['outcome'], expected)
        post.assert_called_once()

  def test_whole_cent_amounts_are_not_rounded(self):
    for amount in (Decimal(10), Decimal('10.0000'), Decimal('1E+1')):
      with (
        self.subTest(amount=amount),
        patch('gateways.services.requests.post', return_value=Mock(status_code=503)) as post,
      ):
        DatafastClient().refund_payment('original-123', amount)
        self.assertEqual(post.call_args.kwargs['data']['amount'], '10.00')

  def test_test_mode_is_gated_by_exact_sandbox_host_and_explicit_config(self):
    cases = [
      ('https://eu-test.oppwa.com/v1/', 'EXTERNAL', True),
      ('https://eu-test.oppwa.com', '', False),
      ('https://eu-test.oppwa.com/v1/', 'external', False),
      ('https://eu-prod.oppwa.com/v1/', 'EXTERNAL', False),
      ('https://eu-test.oppwa.com.evil.invalid/v1/', 'EXTERNAL', False),
    ]
    for base, mode, enabled in cases:
      with self.subTest(base=base, mode=mode), override_settings(DATAFAST_BASE_URL=base, DATAFAST_TEST_MODE=mode):
        data = self.approved()
        data['result']['code'] = '000.100.112'
        result, _, post = self.invoke(data)
        self.assertEqual(result['outcome'], 'CONFIRMED' if enabled else 'UNKNOWN')
        self.assertEqual('testMode' in post.call_args.kwargs['data'], enabled)

  def test_existing_bearer_prefix_is_not_duplicated(self):
    with override_settings(DATAFAST_AUTH_TOKEN='Bearer test-token'):
      _, _, post = self.invoke(self.approved())
    self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer test-token')

  def test_archived_reference_spelling_is_supported_but_conflicts_are_unknown(self):
    data = self.approved()
    data['referencedid'] = data.pop('referencedId')
    result, _, _ = self.invoke(data)
    self.assertEqual(result['outcome'], 'CONFIRMED')
    data['referencedId'] = 'foreign'
    result, _, _ = self.invoke(data)
    self.assertEqual(result, {'outcome': 'UNKNOWN'})

  def test_missing_malformed_or_foreign_fields_are_unknown(self):
    invalid = {
      'id': ['', None, [], '../refund'],
      'referencedId': ['', None, 'foreign', []],
      'paymentType': ['DB', 'RV', None],
      'amount': ['9.99', '10.001', 'NaN', 'Infinity', None, 10.0, True, []],
      'currency': ['EUR', 'usd', None],
      'result': [None, [], {}, {'code': None}, {'code': '000.000.000.extra'}],
    }
    for field, values in invalid.items():
      for value in values + ['MISSING']:
        data = self.approved()
        if value == 'MISSING':
          del data[field]
        else:
          data[field] = value
        with self.subTest(field=field, value=value):
          result, _, _ = self.invoke(data)
          self.assertEqual(result, {'outcome': 'UNKNOWN'})
    for data in (None, [], 'not an object'):
      with self.subTest(data=data):
        result, _, _ = self.invoke(data)
        self.assertEqual(result, {'outcome': 'UNKNOWN'})

  def test_only_documented_definitive_decline_with_matching_fields_is_declined(self):
    data = self.approved()
    data['result']['code'] = '800.100.174'
    result, _, _ = self.invoke(data)
    self.assertEqual(result['outcome'], 'DECLINED')
    for field, value in [('referencedId', 'foreign'), ('amount', '9.99'), ('paymentType', 'DB'), ('currency', 'EUR')]:
      changed = deepcopy(data)
      changed[field] = value
      with self.subTest(field=field):
        result, _, _ = self.invoke(changed)
        self.assertEqual(result, {'outcome': 'UNKNOWN'})

  def test_ambiguous_codes_are_unknown_and_never_retried(self):
    for code in ('700.400.200', '900.100.300', '000.200.000', '000.000.001', '800.100.176', '800.100.100', 'ERROR'):
      data = self.approved()
      data['result']['code'] = code
      with self.subTest(code=code):
        result, _, _ = self.invoke(data)
        self.assertEqual(result['outcome'], 'UNKNOWN')
        self.assertNotIn('description', result)

  def test_redirects_and_http_errors_cannot_confirm(self):
    for status in (201, 302, 307, 400, 500):
      with self.subTest(status=status):
        result, response, _ = self.invoke(self.approved(), status)
        self.assertEqual(result, {'outcome': 'UNKNOWN'})
        response.json.assert_not_called()

  def test_transport_and_json_errors_are_unknown_without_retry_or_exception_leak(self):
    for error in (
      requests.Timeout('private'),
      requests.ConnectionError('private'),
      requests.HTTPError('private'),
      ValueError('private'),
    ):
      with (
        self.subTest(error=type(error).__name__),
        patch('gateways.services.requests.post', side_effect=error) as post,
      ):
        result = DatafastClient().refund_payment('original-123', Decimal(10))
        self.assertEqual(result, {'outcome': 'UNKNOWN'})
        post.assert_called_once()
    response = Mock(status_code=200)
    response.json.side_effect = ValueError('private')
    with patch('gateways.services.requests.post', return_value=response) as post:
      result = DatafastClient().refund_payment('original-123', Decimal(10))
    self.assertEqual(result, {'outcome': 'UNKNOWN'})
    post.assert_called_once()
