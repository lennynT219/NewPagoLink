"""Synthetic public checkout requests over server-owned Gunicorn socket metadata."""

import io
import socket
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from gunicorn.config import Config
from gunicorn.http.message import Request
from gunicorn.http.wsgi import default_environ

from accounts.models import CustomUser
from payments.models import Link, Payment, PaymentAttempt, Sale
from payments.services import checkout_client_ip
from payments.test_checkout_data import payer_input

IP_ERROR = 'No se pudo verificar la dirección IP del pagador.'
PROXY_ERROR = 'No se pudo verificar el proxy del pagador.'


@override_settings(
  ALLOWED_HOSTS=['testserver'],
  EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
  SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
  STRICT_PROFILE=True,
  DJANGO_ENV='production',
  DEBUG=False,
  DATAFAST_ENVIRONMENT='production',
  DATAFAST_BASE_URL='https://eu-prod.oppwa.com/v1/',
  DATAFAST_TEST_MODE='',
  DATAFAST_AUTH_TOKEN='synthetic-only',
  DATAFAST_ECI='synthetic-eci',
  DATAFAST_PSERV='synthetic-pserv',
  DATAFAST_MERCHANT_NAME='Synthetic Merchant',
  DATAFAST_CART_PRICE_BASIS='gross',
)
class UnixProxyCheckoutTests(TestCase):
  def setUp(self):
    self.seller = CustomUser.objects.create(
      user=User.objects.create_user('unix-proxy-owner', first_name='Owner', last_name='Different'),
      identification=1234567890,
    )
    self.link = Link.objects.create(
      seller=self.seller, description='Synthetic Unix transport charge',
      subtotal=100, igv=15, amount=115, include_igv=False,
    )
    self.url = reverse('payments:link_checkout', kwargs={'pk': self.link.pk})
    self.gateway = Mock(base_url='https://eu-prod.oppwa.com/v1/', test_mode=None)
    self.gateway.prepare_checkout.return_value = 'synthetic-unix-checkout'

  def snapshot(self):
    return tuple(list(model.objects.order_by('pk').values()) for model in (
      User, CustomUser, Link, Payment, PaymentAttempt, Sale,
    )) + (len(mail.outbox),)

  def unix_metadata(self, transport):
    req = SimpleNamespace(body=io.BytesIO(), method='POST', query='', uri='/', version=(1, 1))
    # This synthetic request supplies the exact attributes consumed by Gunicorn's builder.
    environ = default_environ(cast(Request, req), transport, Config())
    self.assertIs(environ['gunicorn.socket'], transport)
    return {'gunicorn.socket': environ['gunicorn.socket'], 'REMOTE_ADDR': transport.getpeername()}

  def assert_prepared(self, response, expected_ip):
    self.assertEqual(response.status_code, 200)
    self.assertEqual(
      response.context.get('step'), 'payment',
      str(response.context['form'].errors) if response.context.get('form') else 'Missing payment step',
    )
    self.assertNotContains(response, PROXY_ERROR)
    self.assertNotContains(response, 'id="checkout-errors"')
    self.gateway.prepare_checkout.assert_called_once()
    self.assertEqual(Payment.objects.count(), 1)
    self.assertEqual(PaymentAttempt.objects.count(), 1)
    payment = Payment.objects.get()
    attempt = PaymentAttempt.objects.get()
    self.assertEqual(payment.buyer_client_ip, expected_ip)
    self.assertEqual(self.gateway.prepare_checkout.call_args.kwargs['client_ip'], expected_ip)
    customer = self.gateway.prepare_checkout.call_args.kwargs['customer_data']
    for key, value in payer_input().items():
      self.assertEqual(getattr(payment, key), value)
      self.assertEqual(customer[key], value)
    self.assertEqual(customer['merchant_customer_id'], str(payment.pk))
    self.assertEqual((payment.subtotal, payment.igv, payment.amount, payment.commission),
                     (Decimal(100), Decimal(15), Decimal(115), Decimal(0)))
    self.assertEqual(attempt.amount, Decimal(115))
    self.assertEqual(attempt.state, PaymentAttempt.State.LIVE)
    self.assertEqual(attempt.checkout_id, 'synthetic-unix-checkout')
    self.assertEqual(response.context['checkout_id'], attempt.checkout_id)
    self.assertEqual(response.context['widget_url'], 'https://eu-prod.oppwa.com/v1/paymentWidgets.js')
    self.assertFalse(Sale.objects.exists())
    self.assertEqual(len(mail.outbox), 0)

  def assert_rejected(self, metadata: dict[str, Any], error=PROXY_ERROR, headers: dict[str, Any] | None = None):
    before = self.snapshot()
    header_values: dict[str, Any] = {'HTTP_X_REAL_IP': '8.8.8.8', 'HTTP_X_FORWARDED_FOR': '1.1.1.1'}
    if headers is not None:
      header_values = headers
    with patch('payments.views.DatafastClient') as constructor:
      response = self.client.post(self.url, payer_input(), **metadata, **header_values)
    constructor.assert_not_called()
    self.assertEqual(response.status_code, 200)
    self.assertNotEqual(response.context.get('step'), 'payment')
    self.assertIsNone(response.context.get('checkout_id'))
    self.assertEqual(list(response.context['form'].non_field_errors()), [error])
    self.assertContains(response, error)
    self.assertContains(response, 'id="checkout-errors"')
    self.assertEqual(self.snapshot(), before)

  def test_controlled_unix_socket_prepares_with_validated_payer_ip(self):
    first, second = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    with first, second, patch('payments.views.DatafastClient', return_value=self.gateway):
      metadata = self.unix_metadata(first)
      self.assertEqual(metadata['REMOTE_ADDR'], '')
      response = self.client.post(
        self.url, {**payer_input(), 'client_ip': '1.1.1.1'}, **metadata,
        HTTP_X_REAL_IP='8.8.8.8', HTTP_X_FORWARDED_FOR='1.1.1.1',
      )
    self.assert_prepared(response, '8.8.8.8')

  def test_socket_metadata_is_not_a_client_header_or_a_socket_lookalike(self):
    closed = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    closed.close()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp, socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as datagram:
      for metadata in (
        {'REMOTE_ADDR': ''},
        {'REMOTE_ADDR': '', 'HTTP_GUNICORN_SOCKET': 'AF_UNIX'},
        {'REMOTE_ADDR': '', 'gunicorn.socket': 'AF_UNIX'},
        {'REMOTE_ADDR': '', 'gunicorn.socket': SimpleNamespace(family=socket.AF_UNIX)},
        {'REMOTE_ADDR': '', 'gunicorn.socket': tcp},
        {'REMOTE_ADDR': '', 'gunicorn.socket': datagram},
        {'REMOTE_ADDR': '', 'gunicorn.socket': closed},
      ):
        with self.subTest(metadata_kind=type(metadata.get('gunicorn.socket')).__name__):
          self.assert_rejected(metadata)

  def test_real_unix_socket_still_requires_valid_single_public_payer_ip(self):
    first, second = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    with first, second:
      metadata = self.unix_metadata(first)
      for value in (None, '', 'bad', '8.8.8.8, 1.1.1.1', '127.0.0.1', '10.0.0.2', '::ffff:127.0.0.1'):
        headers = {'HTTP_X_FORWARDED_FOR': '8.8.8.8'}
        if value is not None:
          headers['HTTP_X_REAL_IP'] = value
        with self.subTest(header=value):
          self.assert_rejected(metadata, IP_ERROR, headers)
      with self.settings(SECURE_PROXY_SSL_HEADER=None):
        self.assert_rejected(metadata, IP_ERROR)

  def test_trusted_tcp_proxy_behavior_remains_unchanged(self):
    with patch('payments.views.DatafastClient', return_value=self.gateway):
      response = self.client.post(self.url, payer_input(), REMOTE_ADDR='10.0.0.2', HTTP_X_REAL_IP='8.8.8.8')
    self.assert_prepared(response, '8.8.8.8')

  @override_settings(SECURE_PROXY_SSL_HEADER=None)
  def test_untrusted_tcp_ignores_forged_forwarded_headers(self):
    with patch('payments.views.DatafastClient', return_value=self.gateway):
      response = self.client.post(
        self.url, payer_input(), REMOTE_ADDR='9.9.9.9', HTTP_X_REAL_IP='8.8.8.8', HTTP_X_FORWARDED_FOR='1.1.1.1',
      )
    self.assert_prepared(response, '9.9.9.9')


@override_settings(STRICT_PROFILE=True, SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
class UnixTrustIndependentTests(SimpleTestCase):
  def request(self, transport, peer='', payer='8.8.8.8'):
    return SimpleNamespace(META={
      'gunicorn.socket': transport, 'REMOTE_ADDR': peer,
      'HTTP_X_REAL_IP': payer, 'HTTP_X_FORWARDED_FOR': '1.1.1.1',
    })

  def test_named_unix_peer_and_public_ipv6(self):
    first, second = socket.socketpair()
    with first, second:
      self.assertEqual(
        checkout_client_ip(self.request(first, '/run/backend.sock', '2606:4700:4700::1111')),
        '2606:4700:4700::1111',
      )

  def test_getsockopt_oserror_retains_legacy_peer_checks(self):
    first, second = socket.socketpair()
    with first, second, patch.object(socket.socket, 'getsockopt', side_effect=OSError('synthetic')):
      with self.assertRaisesMessage(ValueError, PROXY_ERROR) as caught:
        checkout_client_ip(self.request(first))
      self.assertEqual(str(caught.exception), PROXY_ERROR)
      self.assertEqual(checkout_client_ip(self.request(first, '10.0.0.2')), '8.8.8.8')

  @override_settings(SECURE_PROXY_SSL_HEADER=None)
  def test_optout_uses_only_raw_peer_without_transport_inspection(self):
    first, second = socket.socketpair()
    with first, second, patch.object(socket.socket, 'getsockopt', side_effect=AssertionError('inspected')):
      self.assertEqual(checkout_client_ip(self.request(first, '9.9.9.9')), '9.9.9.9')

  def test_callable_duck_does_not_authorize_unix(self):
    fake = SimpleNamespace(family=socket.AF_UNIX, getsockopt=Mock(return_value=socket.SOCK_STREAM))
    with self.assertRaisesMessage(ValueError, PROXY_ERROR) as caught:
      checkout_client_ip(self.request(fake))
    self.assertEqual(str(caught.exception), PROXY_ERROR)
    fake.getsockopt.assert_not_called()

  def test_additional_invalid_payer_boundaries(self):
    first, second = socket.socketpair()
    with first, second:
      for payer in ('0.0.0.0', '224.0.0.1', '169.254.1.1', '::ffff:10.0.0.2', ' 8.8.8.8', 'fe80::1%lo'):
        with self.subTest(payer=payer), self.assertRaisesMessage(ValueError, IP_ERROR) as caught:
          checkout_client_ip(self.request(first, payer=payer))
        self.assertEqual(str(caught.exception), IP_ERROR)
