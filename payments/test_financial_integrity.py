from decimal import Decimal
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from unittest.mock import Mock, patch
from typing import Any

from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory, override_settings
from django.contrib.messages.storage.fallback import FallbackStorage

from accounts.models import CustomUser
from payments.models import Link, Payment, PaymentAttempt, Sale
from payments import services
from payments.views import LinkCheckoutView, PaymentResultView


@override_settings(DATAFAST_TEST_MODE='', DATAFAST_BASE_URL='https://eu-prod.oppwa.com/v1/')
class PaymentIntegrityTests(TestCase):
  def setUp(self):
    self.seller = CustomUser.objects.create(
      user=User.objects.create_user('seller'), identification=1234567890)
    self.link = Link.objects.create(seller=self.seller, description='Purchase',
      subtotal=Decimal('100'), amount=Decimal('100'))
    self.payment = self.make_payment()
    self.gateway = Mock()
    self.gateway.prepare_checkout.return_value = 'checkout-123'

  def make_payment(self):
    return Payment.objects.create(link=self.link, seller=self.seller,
      description='Purchase', subtotal=Decimal('100'), amount=Decimal('100'),
      amount_client=Decimal('100'), first_name='Test', last_name='Buyer',
      email='buyer@example.invalid', identify='123', phone='123')

  def attempt(self, payment=None, gateway=None):
    return services.prepare_payment_checkout(
      (payment or self.payment).pk, gateway or self.gateway, {}, '127.0.0.1')

  def result(self, attempt, **changes):
    data = {'id': 'provider-123', 'merchantTransactionId': attempt.merchant_transaction_id,
      'amount': '100.00', 'currency': 'USD', 'paymentType': 'DB',
      'result': {'code': '000.000.000'}}
    data.update(changes)
    return data

  def assert_no_credit(self):
    self.seller.refresh_from_db()
    self.payment.refresh_from_db()
    self.assertEqual(self.seller.available_balance, Decimal('0'))
    self.assertEqual(Sale.objects.count(), 0)
    self.assertNotEqual(self.payment.status, Payment.PaymentStatus.PAID)

  def test_checkout_persists_identity_snapshot_and_reuses_live_attempt(self):
    first = self.attempt()
    second = self.attempt()
    self.assertEqual(first.pk, second.pk)
    self.assertGreaterEqual(len(first.merchant_transaction_id), 8)
    self.assertEqual(first.checkout_id, 'checkout-123')
    self.assertEqual(first.amount, Decimal('100'))
    self.assertEqual(first.currency, 'USD')
    self.gateway.prepare_checkout.assert_called_once()
    self.assertEqual(self.gateway.prepare_checkout.call_args.kwargs['transaction_id'],
      first.merchant_transaction_id)
    self.assertEqual(self.gateway.prepare_checkout.call_args.kwargs['amount'], Decimal('100'))

  def test_credit_fee_confirmation_and_replay_once(self):
    attempt = self.attempt()
    with patch('payments.services.send_payment_confirmation') as confirmation:
      with self.captureOnCommitCallbacks(execute=True):
        services.process_payment_result(self.payment.pk, self.result(attempt))
      services.process_payment_result(self.payment.pk, self.result(attempt))
      services.process_payment_result(self.payment.pk, {'result': {'code': 'ERROR'}})
      confirmation.assert_called_once()
    self.seller.refresh_from_db()
    self.payment.refresh_from_db()
    self.assertEqual(self.seller.available_balance, Decimal('99.65'))
    self.assertEqual(self.payment.commission, Decimal('0.35'))
    self.assertEqual(self.payment.amount_client, Decimal('100'))
    self.assertEqual(Sale.objects.get().net_amount, Decimal('99.65'))
    self.assertEqual(Sale.objects.get().commission, Decimal('0.35'))
    self.assertEqual(self.payment.status, Payment.PaymentStatus.PAID)
    self.assertEqual(self.payment.transaction_id, 'provider-123')
    with self.assertRaises(ValueError):
      self.attempt()
    self.gateway.prepare_checkout.assert_called_once()

  def test_invalid_results_never_post_money(self):
    attempt = self.attempt()
    variants = [
      {'merchantTransactionId': 'another-payment'}, {'amount': '99.99'},
      {'amount': 'NaN'}, {'amount': 'Infinity'}, {'amount': '100.001'},
      {'amount': None}, {'amount': True}, {'amount': 100.0}, {'currency': 'EUR'},
      {'paymentType': 'RF'}, {'id': ''}, {'id': None}, {'id': ' '},
      {'result': {'code': 'prefix000.000.000suffix'}},
      {'result': {'code': '000.100.110'}}, {'result': {'code': '000.100.112'}},
      {'result': {'code': '000.400.010'}}, {'result': {'code': '000.400.020'}},
      {'result': None}, {'result': 'invalid'},
    ]
    for change in variants:
      with self.subTest(change=change):
        services.process_payment_result(self.payment.pk, self.result(attempt, **change))
        self.assert_no_credit()
    malformed: Any = None
    services.process_payment_result(self.payment.pk, malformed)
    malformed = []
    services.process_payment_result(self.payment.pk, malformed)
    self.assert_no_credit()
    self.payment.refresh_from_db()
    self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)

  def test_duplicate_provider_id_and_cross_payment_merchant_rejected(self):
    attempt = self.attempt()
    other = self.make_payment()
    other_gateway = Mock()
    other_gateway.prepare_checkout.return_value = 'checkout-other'
    other_attempt = self.attempt(other, other_gateway)
    services.process_payment_result(other.pk, self.result(attempt))
    self.assert_no_credit()
    services.process_payment_result(self.payment.pk, self.result(attempt))
    services.process_payment_result(other.pk, self.result(other_attempt))
    other.refresh_from_db()
    self.assertEqual(Sale.objects.count(), 1)
    self.assertNotEqual(other.status, Payment.PaymentStatus.PAID)

  def test_historical_sale_prevents_recredit_or_downgrade(self):
    Sale.objects.create(vendor=self.seller, payment=self.payment, amount=100,
      commission=Decimal('5'), net_amount=95)
    self.payment.status = Payment.PaymentStatus.FAILED  # Existing refund convention.
    self.payment.commission = Decimal('5')
    self.payment.transaction_id = 'historic-provider'
    self.payment.save()
    services.process_payment_result(self.payment.pk, {'result': {'code': '000.000.000'}})
    services.process_payment_result(self.payment.pk, {'result': {'code': '800.100.155'}})
    self.payment.refresh_from_db()
    self.seller.refresh_from_db()
    self.assertEqual(self.payment.commission, Decimal('5'))
    self.assertEqual(self.payment.transaction_id, 'historic-provider')
    self.assertEqual(self.payment.status, Payment.PaymentStatus.FAILED)
    self.assertEqual(self.seller.available_balance, Decimal('0'))
    with self.assertRaises(ValueError):
      self.attempt()

  def test_snapshot_mismatch_and_historical_provider_claim_block_credit(self):
    attempt = self.attempt()
    self.payment.amount = Decimal('101')
    self.payment.save()
    services.process_payment_result(self.payment.pk, self.result(attempt, amount='101.00'))
    self.assert_no_credit()
    self.payment.amount = Decimal('100')
    self.payment.save()
    other = self.make_payment()
    other.transaction_id = 'provider-123'
    other.save()
    services.process_payment_result(self.payment.pk, self.result(attempt))
    self.assert_no_credit()

  @override_settings(DATAFAST_TEST_MODE='EXTERNAL', DATAFAST_BASE_URL='https://eu-prod.oppwa.com/v1/')
  def test_test_mode_setting_cannot_authorize_test_code_on_production_host(self):
    attempt = self.attempt()
    services.process_payment_result(self.payment.pk,
      self.result(attempt, result={'code': '000.100.110'}))
    self.assert_no_credit()

  @override_settings(DATAFAST_TEST_MODE='EXTERNAL', DATAFAST_BASE_URL='https://eu-test.oppwa.com/v1/')
  def test_explicit_sandbox_allows_exact_test_connector_code(self):
    attempt = self.attempt()
    services.process_payment_result(self.payment.pk,
      self.result(attempt, result={'code': '000.100.112'}))
    self.assertEqual(Sale.objects.count(), 1)

  def test_small_gross_rejected_before_gateway(self):
    self.payment.amount = Decimal('0.34')
    self.payment.save()
    with self.assertRaises(ValueError):
      self.attempt()
    self.gateway.prepare_checkout.assert_not_called()

  def test_checkout_timeout_blocks_duplicate_and_keeps_history(self):
    self.gateway.prepare_checkout.return_value = None
    attempt = self.attempt()
    retry = self.attempt()
    self.assertEqual(attempt.pk, retry.pk)
    self.assertEqual(attempt.state, 'UNKNOWN')
    self.assertTrue(attempt.history)
    self.gateway.prepare_checkout.assert_called_once()
    self.assert_no_credit()

  def test_decline_retries_with_fresh_merchant_and_preserves_old_mapping(self):
    attempt = self.attempt()
    services.process_payment_result(self.payment.pk,
      self.result(attempt, result={'code': '800.100.155'}))
    self.payment.refresh_from_db()
    self.assertEqual(self.payment.status, Payment.PaymentStatus.FAILED)
    self.gateway.prepare_checkout.return_value = 'checkout-new'
    retry = self.attempt()
    self.assertNotEqual(attempt.merchant_transaction_id, retry.merchant_transaction_id)
    self.assertEqual(getattr(self.payment, 'checkout_attempts').count(), 2)
    attempt.refresh_from_db()
    self.assertEqual(attempt.provider_transaction_id, 'provider-123')
    self.assertEqual(attempt.state, 'DECLINED')

  def test_expired_attempt_mapping_survives_and_old_success_wins_once(self):
    old = self.attempt()
    PaymentAttempt.objects.filter(pk=old.pk).update(
      created_at=timezone.now() - timedelta(minutes=31),
      updated_at=timezone.now() - timedelta(minutes=31))
    self.gateway.prepare_checkout.return_value = 'checkout-new'
    new = self.attempt()
    self.assertNotEqual(old.pk, new.pk)
    old.refresh_from_db()
    self.assertEqual(old.state, 'EXPIRED')
    self.assertEqual(old.checkout_id, 'checkout-123')
    services.process_payment_result(self.payment.pk, self.result(old))
    services.process_payment_result(self.payment.pk,
      self.result(new, id='provider-new', result={'code': '800.100.155'}))
    new.refresh_from_db()
    self.payment.refresh_from_db()
    self.assertEqual(new.state, 'SUPERSEDED')
    self.assertEqual(self.payment.status, Payment.PaymentStatus.PAID)
    self.assertEqual(Sale.objects.count(), 1)

  def test_checkout_window_starts_no_earlier_than_last_provider_observation(self):
    attempt = self.attempt()
    PaymentAttempt.objects.filter(pk=attempt.pk).update(
      created_at=timezone.now() - timedelta(minutes=31))
    retry = self.attempt()
    self.assertEqual(retry.pk, attempt.pk)
    self.gateway.prepare_checkout.assert_called_once()

  def test_late_decline_cannot_fail_new_live_attempt(self):
    old = self.attempt()
    services.process_payment_result(self.payment.pk,
      self.result(old, result={'code': '800.100.155'}))
    self.gateway.prepare_checkout.return_value = 'checkout-new'
    new = self.attempt()
    services.process_payment_result(self.payment.pk,
      self.result(old, result={'code': '800.100.155'}))
    self.payment.refresh_from_db()
    self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
    self.assertEqual(new.state, 'LIVE')
    self.assert_no_credit()

  def test_ambiguous_bound_result_retains_mapping_and_can_later_succeed(self):
    attempt = self.attempt()
    services.process_payment_result(self.payment.pk,
      {'outcome': 'UNKNOWN'}, attempt_id=attempt.pk)
    attempt.refresh_from_db()
    self.assertEqual(attempt.state, 'UNKNOWN')
    self.assertEqual(self.attempt().pk, attempt.pk)
    pending = self.result(attempt, result={'code': '000.200.000'})
    services.process_payment_result(self.payment.pk, pending, attempt_id=attempt.pk)
    attempt.refresh_from_db()
    self.assertEqual(attempt.provider_transaction_id, 'provider-123')
    self.assertEqual(attempt.state, 'UNKNOWN')
    services.process_payment_result(self.payment.pk, self.result(attempt))
    self.assertEqual(Sale.objects.count(), 1)

  def test_constraints_reject_duplicate_open_attempt_and_provider_claim(self):
    attempt = self.attempt()
    with self.assertRaises(IntegrityError), transaction.atomic():
      PaymentAttempt.objects.create(payment=self.payment, amount=100)
    other = self.make_payment()
    with self.assertRaises(IntegrityError), transaction.atomic():
      PaymentAttempt.objects.create(payment=other, amount=100,
        merchant_transaction_id=attempt.merchant_transaction_id)
    with self.assertRaises(IntegrityError), transaction.atomic():
      PaymentAttempt.objects.create(payment=other, amount=100,
        checkout_id=attempt.checkout_id)
    services.process_payment_result(self.payment.pk, self.result(attempt))
    with self.assertRaises(IntegrityError), transaction.atomic():
      PaymentAttempt.objects.create(payment=other, amount=100,
        provider_transaction_id='provider-123')

  def test_gateway_observes_reserved_identity_before_checkout_request(self):
    def remote_checkout(**kwargs):
      attempt = PaymentAttempt.objects.get(
        merchant_transaction_id=kwargs['transaction_id'])
      self.assertEqual(attempt.state, 'CREATING')
      self.assertIsNone(attempt.checkout_id)
      return 'checkout-123'
    self.gateway.prepare_checkout.side_effect = remote_checkout
    self.attempt()

  def test_fee_boundary_credits_zero_net_and_does_not_cap_tariff(self):
    self.payment.amount = Decimal('0.35')
    self.payment.save()
    attempt = self.attempt()
    services.process_payment_result(self.payment.pk, self.result(attempt, amount='0.35'))
    sale = Sale.objects.get()
    self.assertEqual(sale.net_amount, Decimal('0'))
    self.assertEqual(sale.commission, Decimal('0.35'))

  def test_bound_path_does_not_accept_another_attempt_merchant(self):
    attempt = self.attempt()
    data = self.result(attempt, merchantTransactionId='unbound-merchant')
    services.process_payment_result(self.payment.pk, data, attempt_id=attempt.pk)
    self.assert_no_credit()

  def test_result_view_rejects_unbound_paths_before_gateway(self):
    self.attempt()
    paths = ['/v1/checkouts/other/payment', 'https://example.invalid/payment',
      '/v1/checkouts/checkout-123/payment?x=1',
      '/v1/checkouts/checkout-123/../payment',
      '/v1/checkouts/checkout-123/payment/',
      '/v1/checkouts/checkout-123/payment#fragment']
    for path in paths:
      request = RequestFactory().get('/result', {'payment_id': self.payment.pk,
        'resourcePath': path})
      with patch('payments.views.DatafastClient') as client:
        response = PaymentResultView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        client.return_value.get_payment_status.assert_not_called()
    self.assert_no_credit()

  def test_result_view_fetches_only_bound_path_and_credits(self):
    attempt = self.attempt()
    request = RequestFactory().get('/result', {'payment_id': self.payment.pk,
      'resourcePath': '/v1/checkouts/checkout-123/payment'})
    with patch('payments.views.DatafastClient') as client:
      client.return_value.get_payment_status.return_value = self.result(attempt)
      response = PaymentResultView.as_view()(request)
      self.assertEqual(response.status_code, 200)
      client.return_value.get_payment_status.assert_called_once_with(
        '/v1/checkouts/checkout-123/payment')
    self.assertEqual(Sale.objects.count(), 1)

  def test_checkout_view_does_not_edit_or_restart_paid_payment(self):
    self.payment.status = Payment.PaymentStatus.PAID
    self.payment.save()
    request: Any = RequestFactory().post('/checkout?p=' + str(self.payment.pk),
      {'first_name': 'Changed'})
    request.session = {}
    request._messages = FallbackStorage(request)
    with patch('payments.views.DatafastClient') as client:
      response = LinkCheckoutView.as_view()(request, pk=self.link.pk)
      self.assertEqual(response.status_code, 302)
      client.return_value.prepare_checkout.assert_not_called()
    self.payment.refresh_from_db()
    self.assertEqual(self.payment.first_name, 'Test')
