"""Local opt-in gates; synthetic input, no real provider calls."""

from decimal import Decimal
from unittest.mock import patch

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
