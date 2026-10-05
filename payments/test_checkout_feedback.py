"""Rendered checkout feedback using synthetic input and mocked provider I/O."""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from gateways.services import DatafastClient
from payments import services
from payments.models import Link, Payment, PaymentAttempt
from payments.test_checkout_data import payer_input


@override_settings(STRICT_PROFILE=False, SECURE_PROXY_SSL_HEADER=None)
class CheckoutFeedbackTests(TestCase):
  def setUp(self):
    seller = CustomUser.objects.create(user=User.objects.create_user('feedback-owner'), identification=1234567890)
    self.link = Link.objects.create(
      seller=seller, description='Synthetic feedback charge', subtotal=100, igv=15, amount=115
    )
    self.url = reverse('payments:link_checkout', kwargs={'pk': self.link.pk})

  def assert_summary(self, response):
    self.assertContains(response, 'id="checkout-errors"')
    self.assertContains(response, 'role="alert"')
    self.assertContains(response, 'aria-labelledby="checkout-errors-title"')
    self.assertContains(response, 'No se pudo continuar al pago')

  @override_settings(DATAFAST_ALLOW_LOCALHOST=False)
  def test_loopback_denial_visible_without_gateway_or_reservation(self):
    with patch('payments.views.DatafastClient') as gateway:
      response = self.client.post(self.url, payer_input(), REMOTE_ADDR='127.0.0.1')
    gateway.assert_not_called()
    self.assert_summary(response)
    self.assertContains(response, 'No se pudo verificar la dirección IP del pagador.')
    self.assertContains(response, 'DATAFAST_ALLOW_LOCALHOST')
    self.assertFalse(Payment.objects.exists())
    self.assertFalse(PaymentAttempt.objects.exists())

  def test_invalid_fields_have_linked_summary_and_only_submitted_values(self):
    payment = Payment.objects.create(
      link=self.link,
      seller=self.link.seller,
      description=self.link.description,
      subtotal=100,
      igv=15,
      amount=115,
      amount_client=115,
      first_name='PrivateSavedMarker',
      email='private-saved@example.invalid',
    )
    with patch('payments.views.DatafastClient') as gateway:
      response = self.client.post(
        f'{self.url}?p={payment.pk}',
        {'first_name': 'SubmittedMarker', 'email': 'not-an-email'},
        REMOTE_ADDR='198.51.100.42',
      )
    gateway.assert_not_called()
    self.assert_summary(response)
    self.assertContains(response, 'href="#id_buyer_middle_name"')
    self.assertContains(response, 'Este dato real del pagador es obligatorio.')
    self.assertContains(response, 'Ingrese un dato válido.')
    self.assertContains(response, 'SubmittedMarker')
    self.assertNotContains(response, 'PrivateSavedMarker')
    self.assertNotContains(response, 'private-saved@example.invalid')
    self.assertNotContains(response, 'novalidate')
    get = self.client.get(f'{self.url}?p={payment.pk}')
    self.assertFalse(get.context['form'].is_bound)
    self.assertNotContains(get, 'id="checkout-errors"')
    self.assertNotContains(get, 'PrivateSavedMarker')
    self.assertNotContains(get, 'private-saved@example.invalid')

  def test_missing_metadata_visible_before_gateway_or_reservation(self):
    for key in ('DATAFAST_ECI', 'DATAFAST_PSERV', 'DATAFAST_MERCHANT_NAME', 'DATAFAST_CART_PRICE_BASIS'):
      with self.subTest(key=key), override_settings(**{key: ''}), patch('payments.views.DatafastClient') as gateway:
        response = self.client.post(self.url, payer_input(), REMOTE_ADDR='198.51.100.42')
        gateway.assert_not_called()
        self.assert_summary(response)
        self.assertContains(response, key)
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(PaymentAttempt.objects.exists())

  @override_settings(DATAFAST_ALLOW_LOCALHOST=True, DEBUG=True)
  def test_local_view_and_service_use_actual_ip_without_substitution(self):
    with patch('gateways.services.requests.post') as post:
      post.return_value.status_code = 200
      post.return_value.json.return_value = {'id': 'fixture-local-view'}
      response = self.client.post(self.url, payer_input(), REMOTE_ADDR='127.0.0.1')
    self.assertEqual(response.context['step'], 'payment')
    self.assertEqual(response.context['payment'].buyer_client_ip, '127.0.0.1')
    self.assertEqual(post.call_args.kwargs['data']['customer.ip'], '127.0.0.1')

  @override_settings(DATAFAST_ALLOW_LOCALHOST=True, DEBUG=True)
  def test_service_preflight_rejects_actual_client_override_before_reservation(self):
    payment = Payment.objects.create(
      link=self.link,
      seller=self.link.seller,
      description=self.link.description,
      subtotal=100,
      igv=15,
      amount=115,
      amount_client=115,
      **payer_input(),
    )
    gateway = DatafastClient()
    gateway.base_url, gateway.test_mode = 'https://eu-prod.oppwa.com', None
    with patch('gateways.services.requests.post') as post, self.assertRaises(ValueError):
      services.prepare_payment_checkout(payment.pk, gateway, {}, '127.0.0.1')
    post.assert_not_called()
    self.assertFalse(PaymentAttempt.objects.exists())
    payment.refresh_from_db()
    self.assertFalse(payment.buyer_client_ip)

  @override_settings(
    DATAFAST_ENVIRONMENT='phase1',
    DJANGO_ENV='development',
    STRICT_PROFILE=False,
    DEBUG=True,
    DATAFAST_ALLOW_LOCALHOST=True,
    DATAFAST_BASE_URL='https://test.oppwa.com/v1/',
    DATAFAST_TEST_MODE='',
    DATAFAST_PHASE1_ENTITY_ID='fake-phase1-entity',
    DATAFAST_PHASE1_AUTH_TOKEN='fake-phase1-token',
    DATAFAST_MID='',
    DATAFAST_TID='',
    DATAFAST_ECI='',
    DATAFAST_PSERV='',
    DATAFAST_MERCHANT_NAME='',
    DATAFAST_CART_PRICE_BASIS='',
  )
  def test_phase1_widget_minimum_payload_and_actual_ip_snapshot(self):
    with patch('gateways.services.requests.post') as post:
      post.return_value.status_code = 200
      post.return_value.json.return_value = {'id': 'fixture-phase1-widget'}
      response = self.client.post(self.url, payer_input(), REMOTE_ADDR='127.0.0.1')
    self.assertEqual(response.context['step'], 'payment')
    payment = response.context['payment']
    self.assertEqual(payment.buyer_client_ip, '127.0.0.1')
    self.assertEqual(PaymentAttempt.objects.get(payment=payment).environment, 'phase1')
    self.assertContains(response, 'https://test.oppwa.com/v1/paymentWidgets.js?checkoutId=fixture-phase1-widget')
    self.assertEqual(
      post.call_args.kwargs['data'],
      {
        'entityId': 'fake-phase1-entity',
        'amount': '115.00',
        'currency': 'USD',
        'paymentType': 'DB',
      },
    )
    for value in ('fake-phase1-entity', 'fake-phase1-token'):
      self.assertNotContains(response, value)

  def test_widget_url_variants_preserve_checkout_and_payment_binding(self):
    for suffix in ('', '/', '/v1', '/v1/'):
      with (
        self.subTest(suffix=suffix),
        override_settings(DATAFAST_BASE_URL=f'https://eu-test.oppwa.com{suffix}'),
        patch('gateways.services.requests.post') as post,
      ):
        post.return_value.status_code = 200
        checkout_id = f'fixture-checkout-{len(suffix)}'
        post.return_value.json.return_value = {'id': checkout_id}
        response = self.client.post(self.url, payer_input(), REMOTE_ADDR='198.51.100.42')
        self.assertEqual(response.status_code, 200)
        attempt = PaymentAttempt.objects.get(payment=response.context['payment'])
        self.assertEqual(attempt.checkout_id, checkout_id)
        self.assertContains(response, f'src="https://eu-test.oppwa.com/v1/paymentWidgets.js?checkoutId={checkout_id}"')
        self.assertContains(response, f'?payment_id={attempt.payment.pk}" class="paymentWidgets"')
        self.assertEqual(post.call_args.args[0], 'https://eu-test.oppwa.com/v1/checkouts')
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        for secret in ('test-token', 'test-entity', 'test-mid', 'test-tid'):
          self.assertNotContains(response, secret)
