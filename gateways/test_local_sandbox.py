"""Local opt-in gates; synthetic input, no real provider calls."""

from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from gateways.services import DatafastClient, checkout_base_url, validate_client_ip
from gateways.test_checkout_data import synthetic_payer


@override_settings(
  DATAFAST_ALLOW_LOCALHOST=True,
  DEBUG=True,
  STRICT_PROFILE=False,
  DATAFAST_BASE_URL='https://eu-test.oppwa.com',
  DATAFAST_TEST_MODE='EXTERNAL',
)
class LocalSandboxTests(SimpleTestCase):
  def prepare(self, gateway, address):
    return gateway.prepare_checkout(
      amount=Decimal('10.00'),
      subtotal=Decimal('10.00'),
      igv=Decimal('0.00'),
      include_igv=False,
      transaction_id='fixture-attempt',
      customer_data=synthetic_payer(),
      client_ip=address,
      product_description='Synthetic charge',
    )

  def test_opt_in_preserves_actual_loopback_ip_in_sdk_payload(self):
    for address in ('127.0.0.1', '127.0.0.2', '::1', '::ffff:127.0.0.1'):
      with self.subTest(address=address), patch('gateways.services.requests.post') as post:
        post.return_value.status_code = 200
        post.return_value.json.return_value = {'id': 'fixture-local-checkout'}
        self.assertEqual(validate_client_ip(address), address)
        self.assertEqual(self.prepare(DatafastClient(), address), 'fixture-local-checkout')
        self.assertEqual(post.call_args.kwargs['data']['customer.ip'], address)

  def test_each_gate_denies_loopback_without_io(self):
    cases = (
      {'DATAFAST_ALLOW_LOCALHOST': False},
      {'DEBUG': False},
      {'STRICT_PROFILE': True},
      {'DATAFAST_BASE_URL': 'https://eu-prod.oppwa.com'},
      {'DATAFAST_BASE_URL': 'https://foreign.example'},
      {'DATAFAST_BASE_URL': 'http://eu-test.oppwa.com'},
      {'DATAFAST_BASE_URL': 'https://eu-test.oppwa.com:443'},
      {'DATAFAST_TEST_MODE': None},
      {'DATAFAST_TEST_MODE': 'INTERNAL'},
    )
    for overrides in cases:
      for address in ('127.0.0.1', '::1', '::ffff:127.0.0.1'):
        with self.subTest(overrides=overrides, address=address), override_settings(**overrides):
          with patch('gateways.services.requests.post') as post, self.assertRaises(ValueError):
            self.prepare(DatafastClient(), address)
          post.assert_not_called()

  def test_actual_client_override_cannot_borrow_global_sandbox_permission(self):
    for base, mode in (
      ('https://eu-prod.oppwa.com', None),
      ('https://foreign.example', 'EXTERNAL'),
      ('https://eu-test.oppwa.com', None),
    ):
      gateway = DatafastClient()
      gateway.base_url, gateway.test_mode = base, mode
      with self.subTest(base=base, mode=mode), patch('gateways.services.requests.post') as post:
        with self.assertRaises(ValueError):
          self.prepare(gateway, '127.0.0.1')
        post.assert_not_called()

  def test_opt_in_never_allows_other_forbidden_address_classes(self):
    for address in ('0.0.0.0', '::', '224.0.0.1', 'ff02::1', '169.254.1.1', 'fe80::1'):
      with self.subTest(address=address), self.assertRaises(ValueError):
        validate_client_ip(address)

  def test_widget_helper_rejects_unsafe_bases_without_echo(self):
    for base in (
      'http://eu-test.oppwa.com',
      'https://user:private@eu-test.oppwa.com',
      'https://eu-test.oppwa.com/v2',
      'https://eu-test.oppwa.com?private=value',
      'https://eu-test.oppwa.com#private',
      'https://eu-test.oppwa.com?',
      'https://eu-test.oppwa.com#',
      'https://eu-test.oppwa.com?#',
      'https://eu-test.oppwa.com/v1/?',
      'https://eu-test.oppwa.com/v1/#',
    ):
      with self.subTest(base=base):
        with self.assertRaises(ValueError) as error:
          checkout_base_url(base)
        self.assertNotIn(base, str(error.exception))


@override_settings(
  DATAFAST_ENVIRONMENT='phase1',
  DJANGO_ENV='development',
  DEBUG=True,
  STRICT_PROFILE=False,
  DATAFAST_ALLOW_LOCALHOST=True,
  DATAFAST_PHASE1_ENTITY_ID='synthetic-phase1-entity',
  DATAFAST_PHASE1_AUTH_TOKEN='synthetic-phase1-token',
  DATAFAST_BASE_URL='https://test.oppwa.com/v1/',
  DATAFAST_ENTITY_ID='synthetic-phase2-entity',
  DATAFAST_AUTH_TOKEN='synthetic-phase2-token',
  DATAFAST_TEST_MODE=None,
  DATAFAST_MID='',
  DATAFAST_TID='',
  DATAFAST_ECI='',
  DATAFAST_PSERV='',
  DATAFAST_MERCHANT_NAME='',
  DATAFAST_CART_PRICE_BASIS='',
)
class LocalPhaseOneTests(SimpleTestCase):
  def prepare(self, gateway=None):
    return (gateway or DatafastClient()).prepare_checkout(
      amount=Decimal('10.00'),
      subtotal=Decimal('10.00'),
      igv=Decimal('0.00'),
      include_igv=False,
      transaction_id='synthetic-phase1-attempt',
      customer_data=synthetic_payer(),
      client_ip='127.0.0.1',
      product_description='Synthetic charge',
    )

  def test_phase1_checkout_uses_fixed_host_dedicated_credentials_and_minimum_payload(self):
    with patch('gateways.services.requests.post') as post:
      post.return_value.status_code = 200
      post.return_value.json.return_value = {'id': 'synthetic-phase1-checkout'}
      self.assertEqual(self.prepare(), 'synthetic-phase1-checkout')
    self.assertEqual(post.call_args.args[0], 'https://test.oppwa.com/v1/checkouts')
    self.assertEqual(
      post.call_args.kwargs['data'],
      {
        'entityId': 'synthetic-phase1-entity',
        'amount': '10.00',
        'currency': 'USD',
        'paymentType': 'DB',
      },
    )
    self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer synthetic-phase1-token')
    self.assertFalse(post.call_args.kwargs['allow_redirects'])
    # Dedicated credentials must not overwrite unrelated settings.
    self.assertEqual(settings.DATAFAST_BASE_URL, 'https://test.oppwa.com/v1/')
    self.assertEqual(settings.DATAFAST_ENTITY_ID, 'synthetic-phase2-entity')
    self.assertEqual(settings.DATAFAST_AUTH_TOKEN, 'synthetic-phase2-token')
    self.assertIsNone(settings.DATAFAST_TEST_MODE)

  def test_phase1_status_uses_same_fixed_host_and_dedicated_credentials(self):
    data = {'id': 'synthetic-provider', 'result': {'code': '000.100.110'}}
    with patch('gateways.services.requests.get') as get:
      get.return_value.status_code = 200
      get.return_value.json.return_value = data
      self.assertEqual(DatafastClient().get_payment_status('/v1/checkouts/synthetic-phase1-checkout/payment'), data)
    self.assertEqual(get.call_args.args[0], 'https://test.oppwa.com/v1/checkouts/synthetic-phase1-checkout/payment')
    self.assertEqual(get.call_args.kwargs['params'], {'entityId': 'synthetic-phase1-entity'})
    self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer synthetic-phase1-token')
    self.assertFalse(get.call_args.kwargs['allow_redirects'])

  def test_phase1_widget_uses_fixed_test_host(self):
    self.assertEqual(checkout_base_url(DatafastClient().base_url), 'https://test.oppwa.com/v1/')

  def test_phase1_rejects_nonlocal_profiles_before_provider_io(self):
    cases = (
      {'DEBUG': False},
      {'STRICT_PROFILE': True},
      {'DJANGO_ENV': 'staging'},
      {'DJANGO_ENV': 'production'},
    )
    for overrides in cases:
      with (
        self.subTest(overrides=overrides),
        override_settings(**overrides),
        patch('gateways.services.requests.post') as post,
        patch('gateways.services.requests.get') as get,
      ):
        with self.assertRaises((ValueError, ImproperlyConfigured)):
          self.prepare()
        with self.assertRaises((ValueError, ImproperlyConfigured)):
          DatafastClient().get_payment_status('/v1/checkouts/synthetic-phase1-checkout/payment')
        post.assert_not_called()
        get.assert_not_called()

  def test_phase1_missing_credentials_never_fall_back_to_phase2(self):
    for key in ('DATAFAST_PHASE1_ENTITY_ID', 'DATAFAST_PHASE1_AUTH_TOKEN'):
      for value in ('', ' '):
        with (
          self.subTest(key=key, value=value),
          override_settings(**{key: value}),
          patch('gateways.services.requests.post') as post,
          patch('gateways.services.requests.get') as get,
        ):
          with self.assertRaises((ValueError, ImproperlyConfigured)):
            self.prepare()
          with self.assertRaises((ValueError, ImproperlyConfigured)):
            DatafastClient().get_payment_status('/v1/checkouts/synthetic-phase1-checkout/payment')
          post.assert_not_called()
          get.assert_not_called()

  def test_phase1_refund_unsupported_before_provider_post(self):
    with patch('gateways.services.requests.post') as post:
      with self.assertRaises(ValueError):
        DatafastClient().refund_payment('synthetic-provider', Decimal('10.00'))
      post.assert_not_called()

  def test_phase1_actual_sdk_override_rejected_for_checkout_and_status(self):
    for base, test_mode in (('https://eu-test.oppwa.com', 'EXTERNAL'), ('https://foreign.example', None)):
      gateway = DatafastClient()
      gateway.base_url, gateway.test_mode = base, test_mode
      with patch('gateways.services.requests.get') as get, patch('gateways.services.requests.post') as post:
        with self.assertRaises(ValueError):
          gateway.get_payment_status('/v1/checkouts/synthetic-checkout/payment')
        with self.assertRaises(ValueError):
          self.prepare(gateway)
        get.assert_not_called()
        post.assert_not_called()

  def test_phase1_malformed_checkout_id_is_not_accepted(self):
    for checkout_id in ('', 'bad/id', ' padded ', None):
      with self.subTest(checkout_id=checkout_id), patch('gateways.services.requests.post') as post:
        post.return_value.status_code = 200
        post.return_value.json.return_value = {'id': checkout_id}
        self.assertIsNone(self.prepare())

  def test_missing_phase_selector_preserves_phase2_client_configuration(self):
    with override_settings():
      del settings.DATAFAST_ENVIRONMENT
      settings.DATAFAST_BASE_URL = 'https://eu-test.oppwa.com/v1/'
      settings.DATAFAST_TEST_MODE = 'EXTERNAL'
      client = DatafastClient()
      self.assertEqual(client.base_url, 'https://eu-test.oppwa.com/v1/')
      self.assertEqual(client.entity_id, 'synthetic-phase2-entity')
      self.assertEqual(client.auth_token, 'synthetic-phase2-token')
      self.assertEqual(client.test_mode, 'EXTERNAL')

  def test_explicit_phase2_preserves_external_and_phase2_payload(self):
    with (
      override_settings(
        DATAFAST_ENVIRONMENT='phase2',
        DATAFAST_BASE_URL='https://eu-test.oppwa.com/v1/',
        DATAFAST_TEST_MODE='EXTERNAL',
        DATAFAST_MID='synthetic-mid',
        DATAFAST_TID='synthetic-tid',
        DATAFAST_ECI='0103910',
        DATAFAST_PSERV='17913101',
        DATAFAST_MERCHANT_NAME='Synthetic Merchant',
        DATAFAST_CART_PRICE_BASIS='net',
      ),
      patch('gateways.services.requests.post') as post,
    ):
      post.return_value.status_code = 200
      post.return_value.json.return_value = {'id': 'synthetic-phase2-checkout'}
      self.assertEqual(self.prepare(), 'synthetic-phase2-checkout')
    self.assertEqual(post.call_args.args[0], 'https://eu-test.oppwa.com/v1/checkouts')
    payload = post.call_args.kwargs['data']
    self.assertEqual(payload['entityId'], 'synthetic-phase2-entity')
    self.assertEqual(payload['testMode'], 'EXTERNAL')
    self.assertEqual(payload['merchantTransactionId'], 'synthetic-phase1-attempt')
    self.assertEqual(payload['customParameters[SHOPPER_MID]'], 'synthetic-mid')
    self.assertEqual(payload['customer.ip'], '127.0.0.1')
    self.assertEqual(payload['cart.items[0].price'], '10.00')
