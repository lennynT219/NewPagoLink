"""Synthetic checkout identity tests; no real payer, network or mail operations."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from gateways.services import DatafastClient
from gateways.test_checkout_data import synthetic_payer
from payments import services
from payments.forms import CheckoutForm, LinkForm
from payments.models import Link, Payment, PaymentAttempt


def payer_input():
  data = synthetic_payer()
  del data['merchant_customer_id']
  return data


class CheckoutFormTests(SimpleTestCase):
  def test_every_actual_field_required_without_confirmation(self):
    for key in payer_input():
      data = payer_input()
      del data[key]
      with self.subTest(field=key):
        form = CheckoutForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn(key, form.errors)

  def test_same_delivery_requires_explicit_confirmation(self):
    data = payer_input()
    del data['shipping_street']
    del data['shipping_country']
    self.assertFalse(CheckoutForm(data).is_valid())
    data['shipping_same_as_billing'] = 'on'
    form = CheckoutForm(data)
    self.assertTrue(form.is_valid(), form.errors)
    self.assertEqual(form.cleaned_data['shipping_street'], data['billing_street'])
    self.assertEqual(form.cleaned_data['shipping_country'], data['billing_country'])

  def test_invitation_fields_remain_optional(self):
    form = LinkForm({'description': 'Synthetic invitation', 'subtotal': '100', 'tax_type': '0'})
    self.assertTrue(form.is_valid(), form.errors)


class CheckoutPayerTests(TestCase):
  def setUp(self):
    self.seller = CustomUser.objects.create(
      user=User.objects.create_user('synthetic-owner', first_name='Owner', last_name='Different'),
      identification=1234567890,
    )
    self.link = Link.objects.create(
      seller=self.seller, description='Synthetic purchase', subtotal=100, igv=15, amount=115, include_igv=False
    )
    self.url = reverse('payments:link_checkout', kwargs={'pk': self.link.pk})
    self.gateway = Mock()
    self.gateway.prepare_checkout.return_value = 'synthetic-checkout'

  def payment(self, **overrides):
    values = dict(
      link=self.link,
      seller=self.seller,
      description=self.link.description,
      subtotal=100,
      igv=15,
      amount=115,
      amount_client=115,
      **payer_input(),
    )
    values.update(overrides)
    return Payment.objects.create(**values)

  def private_payer(self):
    # Distinct synthetic values make accidental saved-data disclosure observable.
    return {
      'first_name': 'PrivateGivenMarker',
      'buyer_middle_name': 'PrivateMiddleMarker',
      'last_name': 'PrivateSurnameMarker',
      'email': 'private-marker@example.invalid',
      'identify': '8675309001',
      'phone': '023498765',
      'billing_street': 'Private billing marker 813',
      'shipping_street': 'Private shipping marker 914',
      'billing_country': 'AD',
      'shipping_country': 'BZ',
    }

  def private_record(self, state):
    payment = self.payment(**self.private_payer(), status=state if state in ('PAID', 'REFUNDED') else 'PENDING')
    if state in ('LIVE', 'EXPIRED', 'DECLINED'):
      PaymentAttempt.objects.create(
        payment=payment, amount=payment.amount, checkout_id=f'synthetic-private-{payment.pk}', state=state
      )
    return payment

  def test_anonymous_get_never_prefills_saved_payer_in_any_state(self):
    for state in ('INVITATION', 'LIVE', 'EXPIRED', 'DECLINED', 'PAID', 'REFUNDED'):
      payment = self.private_record(state)
      before = Payment.objects.filter(pk=payment.pk).values().get()
      attempts_before = list(PaymentAttempt.objects.filter(payment=payment).values())
      for anonymous in (self.client, Client()):
        with self.subTest(state=state, anonymous=anonymous), patch('payments.views.DatafastClient') as gateway:
          response = anonymous.get(f'{self.url}?p={payment.pk}')
          gateway.assert_not_called()
          self.assertEqual(response.status_code, 200)
          disclosed = [
            key
            for key, value in self.private_payer().items()
            if not key.endswith('_country') and value in response.content.decode()
          ]
          self.assertEqual(disclosed, [], f'saved payer fields disclosed in {state}')
          form = response.context['form']
          self.assertFalse(form.is_bound)
          self.assertEqual(form.initial, {})
          for key in self.private_payer():
            self.assertIn(form[key].value(), (None, ''))
          for country in ('AD', 'BZ'):
            self.assertNotContains(response, f'<option value="{country}" selected')
      self.assertEqual(Payment.objects.filter(pk=payment.pk).values().get(), before)
      self.assertEqual(list(PaymentAttempt.objects.filter(payment=payment).values()), attempts_before)

  def test_invalid_post_reflects_only_submitted_data_not_saved_payer(self):
    submitted = {
      'first_name': 'SubmittedOnlyMarker',
      'email': 'submitted-only@example.invalid',
      'billing_street': 'Submitted-only address',
    }
    for state in ('INVITATION', 'LIVE', 'EXPIRED', 'DECLINED'):
      payment = self.private_record(state)
      before = Payment.objects.filter(pk=payment.pk).values().get()
      attempts_before = list(PaymentAttempt.objects.filter(payment=payment).values())
      with self.subTest(state=state), patch('payments.views.DatafastClient') as gateway:
        response = Client().post(f'{self.url}?p={payment.pk}', submitted, REMOTE_ADDR='198.51.100.42')
        gateway.assert_not_called()
        self.assertEqual(response.status_code, 200)
        for value in submitted.values():
          self.assertContains(response, value)
        for key, value in self.private_payer().items():
          if not key.endswith('_country'):
            self.assertNotContains(response, value)
        form = response.context['form']
        self.assertEqual(form.initial, {})
        for key in self.private_payer():
          self.assertEqual(form[key].value(), submitted.get(key))
        self.assertEqual(Payment.objects.filter(pk=payment.pk).values().get(), before)
        self.assertEqual(list(PaymentAttempt.objects.filter(payment=payment).values()), attempts_before)

  def test_incomplete_historical_invitation_cannot_prepare(self):
    payment = self.payment(buyer_middle_name=None, billing_street=None)
    with self.assertRaises(ValueError):
      services.prepare_payment_checkout(payment.pk, self.gateway, {}, '198.51.100.42')
    self.gateway.prepare_checkout.assert_not_called()
    self.assertFalse(PaymentAttempt.objects.exists())
    payment.refresh_from_db()
    self.assertIsNone(payment.buyer_middle_name)

  def test_view_invalid_middle_name_has_spanish_error_no_io_or_row(self):
    data = payer_input()
    del data['buyer_middle_name']
    with patch('payments.views.DatafastClient') as gateway:
      response = self.client.post(self.url, data, REMOTE_ADDR='198.51.100.42')
      gateway.return_value.prepare_checkout.assert_not_called()
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, 'Segundo nombre (obligatorio)')
    self.assertContains(response, 'Este dato real del pagador es obligatorio.')
    self.assertFalse(Payment.objects.exists())

  def test_actual_payer_saved_before_io_not_owner_or_client_reference(self):
    def prepared(**kwargs):
      payment = Payment.objects.get()
      customer = kwargs['customer_data']
      for key, value in payer_input().items():
        self.assertEqual(getattr(payment, key), value)
        self.assertEqual(customer[key], value)
      self.assertEqual(customer['merchant_customer_id'], str(payment.pk))
      self.assertLessEqual(len(customer['merchant_customer_id']), 16)
      self.assertEqual(payment.buyer_client_ip, '198.51.100.42')
      self.assertEqual(kwargs['client_ip'], '198.51.100.42')
      self.assertEqual(payment.amount, Decimal(115))
      self.assertEqual(payment.subtotal, Decimal(100))
      self.assertEqual(payment.igv, Decimal(15))
      self.assertEqual(payment.commission, Decimal(0))
      return 'synthetic-checkout'

    self.gateway.prepare_checkout.side_effect = prepared
    data = {**payer_input(), 'merchant_customer_id': '999', 'client_ip': '1.1.1.1'}
    with patch('payments.views.DatafastClient', return_value=self.gateway):
      response = self.client.post(
        self.url, data, REMOTE_ADDR='198.51.100.42', HTTP_X_FORWARDED_FOR='1.1.1.1', HTTP_X_REAL_IP='8.8.8.8'
      )
    self.assertEqual(response.status_code, 200)
    self.gateway.prepare_checkout.assert_called_once()

  @override_settings(TAX_IVA=Decimal('0.12'), DATAFAST_CART_PRICE_BASIS='gross')
  def test_per_link_tax_snapshots_reach_sdk_unchanged(self):
    cases = (
      (Link.TaxType.VAT_15, False, '100.00', '15.00', '115.00'),
      (Link.TaxType.VAT_15, True, '86.96', '13.04', '100.00'),
      (Link.TaxType.VAT_0, False, '100.00', '0.00', '100.00'),
      (Link.TaxType.NO_VAT, True, '100.00', '0.00', '100.00'),
    )
    for tax_type, included, subtotal, igv, amount in cases:
      link = services.create_payment_link(
        self.seller,
        {
          'subtotal': '100.00',
          'description': 'Actual service charge',
          'tax_type': tax_type,
          'include_igv': included,
        },
      )
      link_before = Link.objects.filter(pk=link.pk).values().get()
      payment = self.payment(
        link=link, description=link.description, subtotal=link.subtotal, igv=link.igv, amount=link.amount
      )
      financial = ('amount', 'subtotal', 'igv', 'commission', 'description')
      before = Payment.objects.filter(pk=payment.pk).values(*financial).get()
      response = Mock(status_code=200)
      response.json.return_value = {'id': f'synthetic-tax-{payment.pk}'}
      with (
        self.subTest(tax_type=tax_type, included=included),
        patch('gateways.services.requests.post', return_value=response) as post,
      ):
        attempt = services.prepare_payment_checkout(payment.pk, DatafastClient(), {}, '198.51.100.42')
      data = post.call_args.kwargs['data']
      self.assertEqual(data['amount'], amount)
      self.assertEqual(data['cart.items[0].price'], amount)
      self.assertEqual(data['merchantTransactionId'], attempt.merchant_transaction_id)
      self.assertEqual(attempt.amount, Decimal(amount))
      self.assertEqual(data['customParameters[SHOPPER_VAL_BASEIMP]'], subtotal if Decimal(igv) else '0.00')
      self.assertEqual(data['customParameters[SHOPPER_VAL_BASE0]'], '0.00' if Decimal(igv) else subtotal)
      self.assertEqual(data['customParameters[SHOPPER_VAL_IVA]'], igv)
      self.assertEqual(Payment.objects.filter(pk=payment.pk).values(*financial).get(), before)
      self.assertEqual(Link.objects.filter(pk=link.pk).values().get(), link_before)
      self.assertEqual(settings.TAX_IVA, Decimal('0.12'))

  def test_actual_locked_description_forwarded_without_link_rewrite(self):
    payment = self.payment(description='Actual recorded charge')
    before = Payment.objects.filter(pk=payment.pk).values('description', 'amount', 'subtotal', 'igv').get()
    services.prepare_payment_checkout(payment.pk, self.gateway, {}, '198.51.100.42')
    self.assertEqual(self.gateway.prepare_checkout.call_args.kwargs['product_description'], before['description'])
    self.assertEqual(Payment.objects.filter(pk=payment.pk).values(*before).get(), before)
    self.link.refresh_from_db()
    self.assertEqual(self.link.description, 'Synthetic purchase')

  def test_invalid_cart_before_attempt_reservation(self):
    for description in ('', ' ', 'A&B', 'x' * 256):
      payment = self.payment(description=description)
      before = Payment.objects.filter(pk=payment.pk).values().get()
      with self.subTest(description=description), self.assertRaises(ValueError):
        services.prepare_payment_checkout(payment.pk, self.gateway, {}, '198.51.100.42')
      self.assertFalse(PaymentAttempt.objects.filter(payment=payment).exists())
      self.assertEqual(Payment.objects.filter(pk=payment.pk).values().get(), before)
    self.gateway.prepare_checkout.assert_not_called()

  def test_invalid_payer_before_service_reservation_each_field(self):
    for key in payer_input():
      for value in (None, '', 123, 'x' * 130):
        payment = self.payment()
        with self.subTest(field=key, value=value), self.assertRaises((ValueError, TypeError)):
          services.prepare_payment_checkout(payment.pk, self.gateway, {key: value}, '198.51.100.42')
        self.assertFalse(PaymentAttempt.objects.filter(payment=payment).exists())
    self.gateway.prepare_checkout.assert_not_called()

  def test_record_reference_over_16_characters_blocked_before_io(self):
    payment = self.payment(id=10000000000000000)
    with self.assertRaises(ValueError):
      services.prepare_payment_checkout(payment.pk, self.gateway, {}, '198.51.100.42')
    self.gateway.prepare_checkout.assert_not_called()

  def test_retry_uses_persisted_data_and_never_changes_prepared_buyer(self):
    payment = self.payment()
    first = services.prepare_payment_checkout(payment.pk, self.gateway, {}, '198.51.100.42')
    retry = services.prepare_payment_checkout(payment.pk, self.gateway, {}, '198.51.100.43')
    self.assertEqual(first.pk, retry.pk)
    with self.assertRaises(ValueError):
      services.prepare_payment_checkout(payment.pk, self.gateway, {'first_name': 'Changed'}, '198.51.100.43')
    payment.refresh_from_db()
    self.assertEqual(payment.first_name, 'Prueba')
    self.assertEqual(payment.buyer_client_ip, '198.51.100.42')
    PaymentAttempt.objects.filter(pk=first.pk).update(updated_at=timezone.now() - timedelta(minutes=31))
    self.gateway.prepare_checkout.return_value = 'synthetic-retry'
    new = services.prepare_payment_checkout(payment.pk, self.gateway, {}, '198.51.100.43')
    self.assertNotEqual(first.pk, new.pk)
    self.assertEqual(
      self.gateway.prepare_checkout.call_args.kwargs['customer_data']['merchant_customer_id'], str(payment.pk)
    )
    payment.refresh_from_db()
    self.assertEqual(payment.buyer_client_ip, '198.51.100.43')

  def test_terminal_rows_without_new_fields_are_untouched(self):
    for status in ('PAID', 'REFUNDED'):
      payment = self.payment(status=status, buyer_middle_name=None, billing_street=None)
      before = Payment.objects.filter(pk=payment.pk).values().get()
      services.process_payment_result(payment.pk, {})
      with self.assertRaises(ValueError):
        services.prepare_payment_checkout(payment.pk, self.gateway, payer_input(), '198.51.100.42')
      with patch('payments.views.DatafastClient') as gateway:
        self.client.post(f'{self.url}?p={payment.pk}', payer_input(), REMOTE_ADDR='198.51.100.42')
        gateway.return_value.prepare_checkout.assert_not_called()
      self.assertEqual(Payment.objects.filter(pk=payment.pk).values().get(), before)
    self.gateway.prepare_checkout.assert_not_called()

  def test_invitation_completed_only_by_actual_payer(self):
    payment = self.payment(
      buyer_middle_name=None, billing_street=None, shipping_street=None, billing_country=None, shipping_country=None
    )
    with patch('payments.views.DatafastClient', return_value=self.gateway):
      response = self.client.post(f'{self.url}?p={payment.pk}', payer_input(), REMOTE_ADDR='198.51.100.42')
    self.assertEqual(response.status_code, 200)
    self.assertEqual(Payment.objects.count(), 1)
    payment.refresh_from_db()
    self.assertEqual(payment.buyer_middle_name, 'Segundo')


class CheckoutIPTests(SimpleTestCase):
  def client_ip(self, request):
    # Resolve at runtime so RED can exercise the not-yet-implemented boundary.
    boundary_name = 'checkout_client_ip'
    return getattr(services, boundary_name)(request)

  def request(self, remote='198.51.100.42', **headers):
    return RequestFactory().post('/', {'client_ip': '1.1.1.1'}, REMOTE_ADDR=remote, **headers)

  @override_settings(SECURE_PROXY_SSL_HEADER=None)
  def test_untrusted_headers_ignored(self):
    request = self.request(HTTP_X_REAL_IP='8.8.8.8', HTTP_X_FORWARDED_FOR='1.1.1.1')
    self.assertEqual(self.client_ip(request), '198.51.100.42')
    for remote in ('', 'invalid', '127.0.0.1', '::1', '0.0.0.0', '::'):
      with self.subTest(remote=remote), self.assertRaises(ValueError):
        self.client_ip(self.request(remote, HTTP_X_REAL_IP='8.8.8.8'))

  @override_settings(SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
  def test_trusted_proxy_requires_single_valid_real_ip_without_fallback(self):
    request = self.request('10.0.0.2', HTTP_X_REAL_IP='198.51.100.42', HTTP_X_FORWARDED_FOR='1.1.1.1')
    self.assertEqual(self.client_ip(request), '198.51.100.42')
    for value in (None, '', 'bad', '198.51.100.42, 8.8.8.8', '127.0.0.1', '10.0.0.2'):
      headers = {'HTTP_X_FORWARDED_FOR': '8.8.8.8'}
      if value is not None:
        headers['HTTP_X_REAL_IP'] = value
      with self.subTest(value=value), self.assertRaises(ValueError):
        self.client_ip(self.request('10.0.0.2', **headers))

  @override_settings(STRICT_PROFILE=True, SECURE_PROXY_SSL_HEADER=None)
  def test_strict_profiles_reject_nonpublic_addresses(self):
    for remote in ('10.0.0.2', '198.51.100.42', '::ffff:127.0.0.1'):
      with self.subTest(remote=remote), self.assertRaises(ValueError):
        self.client_ip(self.request(remote))
    self.assertEqual(self.client_ip(self.request('8.8.8.8')), '8.8.8.8')
