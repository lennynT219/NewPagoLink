"""Checkout metadata/tax contract using synthetic records and blocked provider I/O."""

from decimal import Decimal, localcontext
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from gateways.services import DatafastClient
from gateways.test_checkout_data import synthetic_payer


@override_settings(
  DATAFAST_ENVIRONMENT='phase2',
  DATAFAST_ECI='configured-eci',
  DATAFAST_PSERV='configured-pserv',
  DATAFAST_MERCHANT_NAME='ApprovedMerchant',
  DATAFAST_CART_PRICE_BASIS='gross',
  DATAFAST_BASE_URL='https://eu-test.oppwa.com/v1/',
  DATAFAST_TEST_MODE='EXTERNAL',
)
class CheckoutTaxTests(SimpleTestCase):
  def prepare(self, amount=Decimal('115.00'), subtotal=Decimal('100.00'), igv=Decimal('15.00'), **kwargs):
    return DatafastClient().prepare_checkout(
      amount,
      subtotal,
      igv,
      kwargs.pop('include_igv', False),
      'PAY-reserved-unique',
      synthetic_payer(),
      kwargs.pop('client_ip', '198.51.100.42'),
      product_description=kwargs.pop('description', 'Recorded service'),
    )

  def payload(self, **kwargs):
    response = Mock(status_code=200)
    response.json.return_value = {'id': 'checkout-123'}
    with patch('gateways.services.requests.post', return_value=response) as post:
      self.assertEqual(self.prepare(**kwargs), 'checkout-123')
    self.assertEqual(post.call_args.args[0], 'https://' + DatafastClient().base_url.split('/')[2] + '/v1/checkouts')
    self.assertFalse(post.call_args.kwargs['allow_redirects'])
    self.assertEqual(post.call_args.kwargs['timeout'], 15)
    self.assertNotEqual(post.call_args.kwargs.get('verify'), False)
    return post.call_args.kwargs

  def test_stored_tax_cents_and_zero_bases_always_sent(self):
    for amount, subtotal, igv, included in (
      ('115.00', '100.00', '15.00', False),
      ('100.00', '86.96', '13.04', True),
      ('17.43', '17.43', '0.00', False),
      ('17.43', '17.43', '0.00', True),
    ):
      with self.subTest(amount=amount, included=included):
        data = self.payload(amount=Decimal(amount), subtotal=Decimal(subtotal), igv=Decimal(igv), include_igv=included)[
          'data'
        ]
        taxed = Decimal(igv) > 0
        self.assertEqual(data['customParameters[SHOPPER_VAL_BASE0]'], '0.00' if taxed else subtotal)
        self.assertEqual(data['customParameters[SHOPPER_VAL_BASEIMP]'], subtotal if taxed else '0.00')
        self.assertEqual(data['customParameters[SHOPPER_VAL_IVA]'], igv)
        self.assertEqual(data['amount'], amount)

  def test_exact_cent_validation_ignores_decimal_context_and_tax_hash_width(self):
    with localcontext() as context:
      context.prec = 6
      data = self.payload(amount=Decimal('12345678.91'), subtotal=Decimal('12345678.90'), igv=Decimal('0.01'))['data']
      self.assertEqual(data['customParameters[SHOPPER_VAL_BASEIMP]'], '12345678.90')
      self.assertEqual(data['amount'], '12345678.91')
      with patch('gateways.services.requests.post') as post, self.assertRaises(ValueError):
        self.prepare(amount=Decimal('12345678.92'), subtotal=Decimal('12345678.90'), igv=Decimal('0.01'))
      post.assert_not_called()

  def test_explicit_metadata_actual_aggregate_cart_and_price_basis(self):
    for basis, price in (('net', '100.00'), ('gross', '115.00')):
      with self.subTest(basis=basis), override_settings(DATAFAST_CART_PRICE_BASIS=basis):
        data = self.payload()['data']
        self.assertEqual(data['cart.items[0].price'], price)
        self.assertEqual(data['cart.items[0].name'], 'Recorded service')
        self.assertEqual(data['cart.items[0].description'], 'Recorded service')
        self.assertEqual(data['cart.items[0].quantity'], '1')
        self.assertEqual(data['risk.parameters[USER_DATA2]'], 'ApprovedMerchant')
        self.assertEqual(data['customParameters[SHOPPER_ECI]'], 'configured-eci')
        self.assertEqual(data['customParameters[SHOPPER_PSERV]'], 'configured-pserv')
        self.assertEqual(data['testMode'], 'EXTERNAL')

  def test_missing_or_invalid_metadata_never_posts(self):
    for key, values in {
      'DATAFAST_ECI': ('', ' ', 'bad\nvalue'),
      'DATAFAST_PSERV': ('', 'bad\rvalue'),
      'DATAFAST_MERCHANT_NAME': ('', 'x' * 31, 'Merchant&Co'),
      'DATAFAST_CART_PRICE_BASIS': ('', 'other', 'gross\n'),
    }.items():
      for value in values:
        with (
          self.subTest(key=key, value=value),
          override_settings(**{key: value}),
          patch('gateways.services.requests.post') as post,
        ):
          with self.assertRaises(ValueError):
            self.prepare()
          post.assert_not_called()

  def test_invalid_cart_and_amounts_never_post(self):
    for description in ('', ' ', 'A&B', 'x' * 256, 'bad\ntext'):
      with self.subTest(description=description), patch('gateways.services.requests.post') as post:
        with self.assertRaises(ValueError):
          self.prepare(description=description)
        post.assert_not_called()
    cases = [
      {'amount': value}
      for value in (Decimal('NaN'), Decimal('Infinity'), Decimal(-1), Decimal('115.001'), Decimal(114))
    ]
    cases += [
      {'subtotal': Decimal(-1)},
      {'igv': Decimal('0.001')},
      {'amount': Decimal(10000000000), 'subtotal': Decimal(9999999985)},
    ]
    for case in cases:
      with self.subTest(case=case), patch('gateways.services.requests.post') as post:
        with self.assertRaises(ValueError):
          self.prepare(**case)
        post.assert_not_called()

  def test_checkout_bearer_once_and_reject_invalid_tokens(self):
    for token in ('raw-token', 'Bearer raw-token'):
      with override_settings(DATAFAST_AUTH_TOKEN=token):
        self.assertEqual(self.payload()['headers']['Authorization'], 'Bearer raw-token')
    for token in ('', ' ', 'Bearer ', 'Bearer Bearer token', 'raw\r\ntoken'):
      with (
        self.subTest(token=token),
        override_settings(DATAFAST_AUTH_TOKEN=token),
        patch('gateways.services.requests.post') as post,
      ):
        with self.assertRaises(ValueError):
          self.prepare()
        post.assert_not_called()

  def test_production_omits_test_mode_and_rejects_external(self):
    with override_settings(
      DATAFAST_ENVIRONMENT='production',
      DJANGO_ENV='production',
      STRICT_PROFILE=True,
      DEBUG=False,
      DATAFAST_ALLOW_LOCALHOST=False,
      DATAFAST_BASE_URL='https://eu-prod.oppwa.com/v1/',
      DATAFAST_TEST_MODE='',
    ):
      self.assertNotIn('testMode', self.payload(client_ip='8.8.8.8')['data'])
      with override_settings(DATAFAST_TEST_MODE='EXTERNAL'), patch('gateways.services.requests.post') as post:
        with self.assertRaises(ValueError):
          self.prepare(client_ip='8.8.8.8')
        post.assert_not_called()

  def test_root_profile_posts_to_checkout_endpoint(self):
    with override_settings(DATAFAST_BASE_URL='https://eu-test.oppwa.com'):
      self.payload()

  def test_redirect_cannot_supply_checkout_id(self):
    response = Mock(status_code=302)
    response.json.return_value = {'id': 'redirected-checkout'}
    with patch('gateways.services.requests.post', return_value=response):
      self.assertIsNone(self.prepare())
    response.json.assert_not_called()
