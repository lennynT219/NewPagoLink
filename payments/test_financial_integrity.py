from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from payments import services
from payments.models import Link, Payment, PaymentAttempt, Refund, Sale
from payments.views import LinkCheckoutView, PaymentResultView


@override_settings(
  DATAFAST_ENVIRONMENT='production',
  DJANGO_ENV='production',
  STRICT_PROFILE=True,
  DEBUG=False,
  DATAFAST_TEST_MODE='',
  DATAFAST_BASE_URL='https://eu-prod.oppwa.com/v1/',
)
class PaymentIntegrityTests(TestCase):
  def setUp(self):
    self.seller = CustomUser.objects.create(user=User.objects.create_user('seller'), identification=1234567890)
    self.link = Link.objects.create(
      seller=self.seller, description='Purchase', subtotal=Decimal(100), amount=Decimal(100)
    )
    self.payment = self.make_payment()
    self.gateway = Mock()
    self.gateway.prepare_checkout.return_value = 'checkout-123'

  def make_payment(self):
    return Payment.objects.create(
      link=self.link,
      seller=self.seller,
      description='Purchase',
      subtotal=Decimal(100),
      amount=Decimal(100),
      amount_client=Decimal(100),
      first_name='Test',
      last_name='Buyer',
      email='buyer@example.invalid',
      identify='123',
      phone='023456789',
      # Synthetic actual-payer data for positive provider preparation fixtures.
      buyer_middle_name='Segundo',
      billing_street='Calle de prueba 123',
      shipping_street='Entrega de prueba 456',
      billing_country='EC',
      shipping_country='CL',
    )

  def attempt(self, payment=None, gateway=None):
    return services.prepare_payment_checkout((payment or self.payment).pk, gateway or self.gateway, {}, '8.8.8.8')

  def result(self, attempt, **changes):
    data = {
      'id': 'provider-123',
      'merchantTransactionId': attempt.merchant_transaction_id,
      'amount': '100.00',
      'currency': 'USD',
      'paymentType': 'DB',
      'result': {'code': '000.000.000'},
    }
    data.update(changes)
    return data

  def assert_no_credit(self):
    self.seller.refresh_from_db()
    self.payment.refresh_from_db()
    self.assertEqual(self.seller.available_balance, Decimal(0))
    self.assertEqual(Sale.objects.count(), 0)
    self.assertNotEqual(self.payment.status, Payment.PaymentStatus.PAID)

  def test_checkout_persists_identity_snapshot_and_reuses_live_attempt(self):
    first = self.attempt()
    second = self.attempt()
    self.assertEqual(first.pk, second.pk)
    self.assertGreaterEqual(len(first.merchant_transaction_id), 8)
    self.assertEqual(first.checkout_id, 'checkout-123')
    self.assertEqual(first.amount, Decimal(100))
    self.assertEqual(first.currency, 'USD')
    self.assertEqual(first.environment, 'production')
    self.gateway.prepare_checkout.assert_called_once()
    self.assertEqual(self.gateway.prepare_checkout.call_args.kwargs['transaction_id'], first.merchant_transaction_id)
    self.assertEqual(self.gateway.prepare_checkout.call_args.kwargs['amount'], Decimal(100))

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
    self.assertEqual(self.payment.amount_client, Decimal(100))
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
      {'merchantTransactionId': 'another-payment'},
      {'amount': '99.99'},
      {'amount': 'NaN'},
      {'amount': 'Infinity'},
      {'amount': '100.001'},
      {'amount': None},
      {'amount': True},
      {'amount': 100.0},
      {'currency': 'EUR'},
      {'paymentType': 'RF'},
      {'id': ''},
      {'id': None},
      {'id': ' '},
      {'result': {'code': 'prefix000.000.000suffix'}},
      {'result': {'code': '000.100.110'}},
      {'result': {'code': '000.100.112'}},
      {'result': {'code': '000.400.010'}},
      {'result': {'code': '000.400.020'}},
      {'result': None},
      {'result': 'invalid'},
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
    Sale.objects.create(vendor=self.seller, payment=self.payment, amount=100, commission=Decimal(5), net_amount=95)
    self.payment.status = Payment.PaymentStatus.FAILED  # Existing refund convention.
    self.payment.commission = Decimal(5)
    self.payment.transaction_id = 'historic-provider'
    self.payment.save()
    services.process_payment_result(self.payment.pk, {'result': {'code': '000.000.000'}})
    services.process_payment_result(self.payment.pk, {'result': {'code': '800.100.155'}})
    self.payment.refresh_from_db()
    self.seller.refresh_from_db()
    self.assertEqual(self.payment.commission, Decimal(5))
    self.assertEqual(self.payment.transaction_id, 'historic-provider')
    self.assertEqual(self.payment.status, Payment.PaymentStatus.FAILED)
    self.assertEqual(self.seller.available_balance, Decimal(0))
    with self.assertRaises(ValueError):
      self.attempt()

  def test_snapshot_mismatch_and_historical_provider_claim_block_credit(self):
    attempt = self.attempt()
    self.payment.amount = Decimal(101)
    self.payment.save()
    services.process_payment_result(self.payment.pk, self.result(attempt, amount='101.00'))
    self.assert_no_credit()
    self.payment.amount = Decimal(100)
    self.payment.save()
    other = self.make_payment()
    other.transaction_id = 'provider-123'
    other.save()
    services.process_payment_result(self.payment.pk, self.result(attempt))
    self.assert_no_credit()

  @override_settings(DATAFAST_TEST_MODE='EXTERNAL', DATAFAST_BASE_URL='https://eu-prod.oppwa.com/v1/')
  def test_test_mode_setting_cannot_authorize_test_code_on_production_host(self):
    with override_settings(DATAFAST_TEST_MODE=''):
      attempt = self.attempt()
    services.process_payment_result(self.payment.pk, self.result(attempt, result={'code': '000.100.110'}))
    self.assert_no_credit()

  @override_settings(
    DATAFAST_ENVIRONMENT='phase2',
    DJANGO_ENV='development',
    STRICT_PROFILE=False,
    DEBUG=True,
    DATAFAST_TEST_MODE='EXTERNAL',
    DATAFAST_BASE_URL='https://eu-test.oppwa.com/v1/',
  )
  def test_explicit_sandbox_allows_exact_test_connector_code(self):
    attempt = self.attempt()
    services.process_payment_result(self.payment.pk, self.result(attempt, result={'code': '000.100.112'}))
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
    services.process_payment_result(self.payment.pk, self.result(attempt, result={'code': '800.100.155'}))
    self.payment.refresh_from_db()
    self.assertEqual(self.payment.status, Payment.PaymentStatus.FAILED)
    self.gateway.prepare_checkout.return_value = 'checkout-new'
    retry = self.attempt()
    self.assertNotEqual(attempt.merchant_transaction_id, retry.merchant_transaction_id)
    self.assertEqual(PaymentAttempt.objects.filter(payment=self.payment).count(), 2)
    attempt.refresh_from_db()
    self.assertEqual(attempt.provider_transaction_id, 'provider-123')
    self.assertEqual(attempt.state, 'DECLINED')

  def test_expired_attempt_mapping_survives_and_old_success_wins_once(self):
    old = self.attempt()
    PaymentAttempt.objects.filter(pk=old.pk).update(
      created_at=timezone.now() - timedelta(minutes=31), updated_at=timezone.now() - timedelta(minutes=31)
    )
    self.gateway.prepare_checkout.return_value = 'checkout-new'
    new = self.attempt()
    self.assertNotEqual(old.pk, new.pk)
    old.refresh_from_db()
    self.assertEqual(old.state, 'EXPIRED')
    self.assertEqual(old.checkout_id, 'checkout-123')
    services.process_payment_result(self.payment.pk, self.result(old))
    services.process_payment_result(
      self.payment.pk, self.result(new, id='provider-new', result={'code': '800.100.155'})
    )
    new.refresh_from_db()
    self.payment.refresh_from_db()
    self.assertEqual(new.state, 'SUPERSEDED')
    self.assertEqual(self.payment.status, Payment.PaymentStatus.PAID)
    self.assertEqual(Sale.objects.count(), 1)

  def test_checkout_window_starts_no_earlier_than_last_provider_observation(self):
    attempt = self.attempt()
    PaymentAttempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now() - timedelta(minutes=31))
    retry = self.attempt()
    self.assertEqual(retry.pk, attempt.pk)
    self.gateway.prepare_checkout.assert_called_once()

  def test_late_decline_cannot_fail_new_live_attempt(self):
    old = self.attempt()
    services.process_payment_result(self.payment.pk, self.result(old, result={'code': '800.100.155'}))
    self.gateway.prepare_checkout.return_value = 'checkout-new'
    new = self.attempt()
    services.process_payment_result(self.payment.pk, self.result(old, result={'code': '800.100.155'}))
    self.payment.refresh_from_db()
    self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
    self.assertEqual(new.state, 'LIVE')
    self.assert_no_credit()

  def test_ambiguous_bound_result_retains_mapping_and_can_later_succeed(self):
    attempt = self.attempt()
    services.process_payment_result(self.payment.pk, {'outcome': 'UNKNOWN'}, attempt_id=attempt.pk)
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
      PaymentAttempt.objects.create(payment=other, amount=100, merchant_transaction_id=attempt.merchant_transaction_id)
    with self.assertRaises(IntegrityError), transaction.atomic():
      PaymentAttempt.objects.create(payment=other, amount=100, checkout_id=attempt.checkout_id)
    services.process_payment_result(self.payment.pk, self.result(attempt))
    with self.assertRaises(IntegrityError), transaction.atomic():
      PaymentAttempt.objects.create(payment=other, amount=100, provider_transaction_id='provider-123')

  def test_gateway_observes_reserved_identity_before_checkout_request(self):
    def remote_checkout(**kwargs):
      attempt = PaymentAttempt.objects.get(merchant_transaction_id=kwargs['transaction_id'])
      self.assertEqual(attempt.state, 'CREATING')
      self.assertIsNone(attempt.checkout_id)
      return 'checkout-123'

    self.gateway.prepare_checkout.side_effect = remote_checkout
    self.attempt()

  def test_fee_boundary_credits_zero_net_and_does_not_cap_tariff(self):
    self.payment.amount = Decimal('0.35')
    self.payment.subtotal = Decimal('0.35')  # Untaxed fixture must preserve subtotal + IVA = gross.
    self.payment.save()
    attempt = self.attempt()
    services.process_payment_result(self.payment.pk, self.result(attempt, amount='0.35'))
    sale = Sale.objects.get()
    self.assertEqual(sale.net_amount, Decimal(0))
    self.assertEqual(sale.commission, Decimal('0.35'))

  def test_bound_path_does_not_accept_another_attempt_merchant(self):
    attempt = self.attempt()
    data = self.result(attempt, merchantTransactionId='unbound-merchant')
    services.process_payment_result(self.payment.pk, data, attempt_id=attempt.pk)
    self.assert_no_credit()

  def test_result_view_rejects_unbound_paths_before_gateway(self):
    self.attempt()
    paths = [
      '/v1/checkouts/other/payment',
      'https://example.invalid/payment',
      '/v1/checkouts/checkout-123/payment?x=1',
      '/v1/checkouts/checkout-123/../payment',
      '/v1/checkouts/checkout-123/payment/',
      '/v1/checkouts/checkout-123/payment#fragment',
    ]
    for path in paths:
      request = RequestFactory().get('/result', {'payment_id': self.payment.pk, 'resourcePath': path})
      with patch('payments.views.DatafastClient') as client:
        response = PaymentResultView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        client.return_value.get_payment_status.assert_not_called()
    self.assert_no_credit()

  def test_result_view_fetches_only_bound_path_and_credits(self):
    attempt = self.attempt()
    request = RequestFactory().get(
      '/result', {'payment_id': self.payment.pk, 'resourcePath': '/v1/checkouts/checkout-123/payment'}
    )
    with patch('payments.views.DatafastClient') as client:
      client.return_value.get_payment_status.return_value = self.result(attempt)
      response = PaymentResultView.as_view()(request)
      self.assertEqual(response.status_code, 200)
      client.return_value.get_payment_status.assert_called_once_with('/v1/checkouts/checkout-123/payment')
    self.assertEqual(Sale.objects.count(), 1)

  def test_checkout_view_does_not_edit_or_restart_paid_payment(self):
    self.payment.status = Payment.PaymentStatus.PAID
    self.payment.save()
    request: Any = RequestFactory().post('/checkout?p=' + str(self.payment.pk), {'first_name': 'Changed'})
    request.session = {}
    request._messages = FallbackStorage(request)
    with patch('payments.views.DatafastClient') as client:
      response = LinkCheckoutView.as_view()(request, pk=self.link.pk)
      self.assertEqual(response.status_code, 302)
      client.return_value.prepare_checkout.assert_not_called()
    self.payment.refresh_from_db()
    self.assertEqual(self.payment.first_name, 'Test')

  def phase1_settings(self, **changes):
    config = {
      'DATAFAST_ENVIRONMENT': 'phase1',
      'DJANGO_ENV': 'development',
      'DEBUG': True,
      'STRICT_PROFILE': False,
      'DATAFAST_PHASE1_ENTITY_ID': 'synthetic-phase1-entity',
      'DATAFAST_PHASE1_AUTH_TOKEN': 'synthetic-phase1-token',
      'DATAFAST_BASE_URL': 'https://test.oppwa.com/v1/',
      'DATAFAST_TEST_MODE': None,
    }
    config.update(changes)
    return override_settings(**config)

  def phase1_attempt(self):
    with self.phase1_settings():
      return self.attempt()

  def phase1_result(self, attempt, **changes):
    data = self.result(
      attempt,
      result={
        'code': '000.100.110',
        'description': 'Request successfully processed in Merchant in Integrator Test Mode',
      },
    )
    del data['merchantTransactionId']
    data.update(changes)
    return data

  def test_phase1_bound_result_without_merchant_credits_and_replays_once(self):
    attempt = self.phase1_attempt()
    with self.phase1_settings(), patch('payments.services.send_payment_confirmation') as confirmation:
      with self.captureOnCommitCallbacks(execute=True):
        services.process_payment_result(self.payment.pk, self.phase1_result(attempt), attempt_id=attempt.pk)
      services.process_payment_result(self.payment.pk, self.phase1_result(attempt), attempt_id=attempt.pk)
      confirmation.assert_called_once()
    self.payment.refresh_from_db()
    self.seller.refresh_from_db()
    attempt.refresh_from_db()
    self.assertEqual(self.payment.status, Payment.PaymentStatus.PAID)
    self.assertEqual(self.payment.transaction_id, 'provider-123')
    self.assertEqual(attempt.provider_transaction_id, 'provider-123')
    self.assertEqual(self.seller.available_balance, Decimal('99.65'))
    self.assertEqual(Sale.objects.count(), 1)
    self.assertEqual(Sale.objects.get().commission, Decimal('0.35'))

  def test_phase1_supplied_matching_merchant_is_accepted(self):
    attempt = self.phase1_attempt()
    with self.phase1_settings():
      services.process_payment_result(
        self.payment.pk,
        self.phase1_result(attempt, merchantTransactionId=attempt.merchant_transaction_id),
        attempt_id=attempt.pk,
      )
    self.assertEqual(Sale.objects.count(), 1)

  def test_phase1_result_without_callback_attempt_binding_never_credits(self):
    attempt = self.phase1_attempt()
    with self.phase1_settings():
      services.process_payment_result(self.payment.pk, self.phase1_result(attempt))
      services.process_payment_result(self.payment.pk, self.phase1_result(attempt), attempt_id=attempt.pk + 1000)
    self.assert_no_credit()

  def test_phase1_cross_payment_attempt_and_mismatched_merchant_never_credit(self):
    attempt = self.phase1_attempt()
    other = self.make_payment()
    other_gateway = Mock()
    other_gateway.prepare_checkout.return_value = 'checkout-other'
    other_attempt = self.attempt(other, other_gateway)
    with self.phase1_settings():
      services.process_payment_result(self.payment.pk, self.phase1_result(attempt), attempt_id=other_attempt.pk)
      services.process_payment_result(
        self.payment.pk,
        self.phase1_result(attempt, merchantTransactionId=other_attempt.merchant_transaction_id),
        attempt_id=attempt.pk,
      )
    self.assert_no_credit()

  def test_phase1_invalid_or_unavailable_bound_results_never_credit(self):
    attempt = self.phase1_attempt()
    variants = (
      {'merchantTransactionId': None},
      {'id': ''},
      {'id': None},
      {'id': ' padded '},
      {'id': 'bad/id'},
      {'amount': '99.99'},
      {'amount': '100.001'},
      {'amount': 'NaN'},
      {'amount': 'Infinity'},
      {'amount': None},
      {'amount': True},
      {'amount': 100.0},
      {'currency': 'EUR'},
      {'paymentType': 'RF'},
      {'result': {'code': 'prefix000.100.110suffix'}},
      {'result': {'code': '000.400.010'}},
      {'result': {'code': '000.200.000'}},
      {'result': None},
    )
    with self.phase1_settings():
      for changes in variants:
        with self.subTest(changes=changes):
          services.process_payment_result(
            self.payment.pk,
            self.phase1_result(attempt, **changes),
            attempt_id=attempt.pk,
          )
          self.assert_no_credit()
      for malformed in (None, [], {'outcome': 'UNKNOWN'}):
        with self.subTest(malformed=malformed):
          services.process_payment_result(self.payment.pk, malformed, attempt_id=attempt.pk)
          self.assert_no_credit()

  def test_phase1_nonlocal_profiles_cannot_confirm_test_result(self):
    attempt = self.phase1_attempt()
    for changes in (
      {'DEBUG': False},
      {'STRICT_PROFILE': True},
      {'DJANGO_ENV': 'staging'},
      {'DJANGO_ENV': 'production'},
    ):
      with self.subTest(changes=changes), self.phase1_settings(**changes):
        services.process_payment_result(self.payment.pk, self.phase1_result(attempt), attempt_id=attempt.pk)
        self.assert_no_credit()

  def test_phase2_still_requires_merchant_for_bound_results(self):
    with override_settings(
      DATAFAST_ENVIRONMENT='phase2',
      DJANGO_ENV='development',
      STRICT_PROFILE=False,
      DEBUG=True,
      DATAFAST_BASE_URL='https://eu-test.oppwa.com/v1/',
      DATAFAST_TEST_MODE='EXTERNAL',
    ):
      attempt = self.attempt()
      self.assertEqual(attempt.environment, 'phase2')
      for code in ('000.000.000', '000.100.110', '000.100.112'):
        with self.subTest(code=code):
          data = self.phase1_result(attempt, result={'code': code})
          services.process_payment_result(self.payment.pk, data, attempt_id=attempt.pk)
          self.assert_no_credit()

  def test_phase1_result_view_fetches_bound_path_and_credits_without_merchant(self):
    attempt = self.phase1_attempt()
    request = RequestFactory().get(
      '/result', {'payment_id': self.payment.pk, 'resourcePath': '/v1/checkouts/checkout-123/payment'}
    )
    with self.phase1_settings(), patch('payments.views.DatafastClient') as client:
      client.return_value.get_payment_status.return_value = self.phase1_result(attempt)
      response = PaymentResultView.as_view()(request)
      self.assertEqual(response.status_code, 200)
      client.return_value.get_payment_status.assert_called_once_with('/v1/checkouts/checkout-123/payment')
    self.assertEqual(Sale.objects.count(), 1)

  def test_production_and_legacy_require_merchant_binding(self):
    attempt = self.attempt()
    for environment in ('production', ''):
      attempt.environment = environment
      attempt.save()
      services.process_payment_result(
        self.payment.pk,
        self.phase1_result(attempt, result={'code': '000.000.000'}),
        attempt_id=attempt.pk,
      )
      self.assert_no_credit()
    # A legacy production debit still needs the complete original binding.
    services.process_payment_result(self.payment.pk, self.result(attempt), attempt_id=attempt.pk)
    self.assertEqual(Sale.objects.count(), 1)
    self.payment.refresh_from_db()
    refund = services.request_refund(self.seller, self.payment, 'Legacy compatible refund')
    self.assertEqual(refund.amount, self.payment.amount)

  def test_phase1_does_not_borrow_production_or_phase2_success_codes(self):
    attempt = self.phase1_attempt()
    with self.phase1_settings():
      for code in ('000.000.000', '000.100.112'):
        services.process_payment_result(
          self.payment.pk,
          self.phase1_result(attempt, result={'code': code}),
          attempt_id=attempt.pk,
        )
        self.assert_no_credit()

  def test_phase1_legacy_and_other_mode_attempts_never_reinterpreted(self):
    attempt = self.attempt()
    for environment in ('', 'production', 'phase2'):
      attempt.environment = environment
      attempt.save()
      with self.phase1_settings():
        services.process_payment_result(self.payment.pk, self.phase1_result(attempt), attempt_id=attempt.pk)
        self.assert_no_credit()

  def test_phase1_attempt_pins_mode_and_rejects_switch_before_status_io(self):
    attempt = self.phase1_attempt()
    self.assertEqual(attempt.environment, 'phase1')
    request = RequestFactory().get(
      '/result',
      {
        'payment_id': self.payment.pk,
        'resourcePath': '/v1/checkouts/checkout-123/payment',
      },
    )
    with patch('payments.views.DatafastClient') as client:
      self.assertEqual(PaymentResultView.as_view()(request).status_code, 400)
      client.return_value.get_payment_status.assert_not_called()
    services.process_payment_result(self.payment.pk, self.result(attempt), attempt_id=attempt.pk)
    self.assert_no_credit()

  def test_phase1_refund_fails_before_request_reservation(self):
    attempt = self.phase1_attempt()
    with self.phase1_settings():
      services.process_payment_result(self.payment.pk, self.phase1_result(attempt), attempt_id=attempt.pk)
      self.payment.refresh_from_db()
      with self.assertRaises(ValueError):
        services.request_refund(self.seller, self.payment, 'Synthetic refund')
      self.assertFalse(hasattr(self.payment, 'refund'))

  def test_phase1_result_view_rejects_unbound_path_before_provider_io(self):
    self.phase1_attempt()
    request = RequestFactory().get(
      '/result', {'payment_id': self.payment.pk, 'resourcePath': '/v1/checkouts/checkout-other/payment'}
    )
    with self.phase1_settings(), patch('payments.views.DatafastClient') as client:
      response = PaymentResultView.as_view()(request)
      self.assertEqual(response.status_code, 400)
      client.return_value.get_payment_status.assert_not_called()
    self.assert_no_credit()


@override_settings(
  DATAFAST_ENVIRONMENT='production',
  DJANGO_ENV='production',
  STRICT_PROFILE=True,
  DEBUG=False,
  DATAFAST_BASE_URL='https://eu-prod.oppwa.com/v1/',
  DATAFAST_TEST_MODE='',
)
class RefundEnvironmentTests(TransactionTestCase):
  def setUp(self):
    self.seller = CustomUser.objects.create(
      user=User.objects.create_user('mode-refund-owner'),
      identification=1234567890,
      available_balance=Decimal('150.00'),
    )
    self.payment = Payment.objects.create(
      seller=self.seller,
      description='Synthetic refund charge',
      subtotal=100,
      amount=100,
      amount_client=100,
      commission=Decimal('0.35'),
      status=Payment.PaymentStatus.PAID,
      state=True,
      transaction_id='mode-provider',
    )
    self.attempt = PaymentAttempt.objects.create(
      payment=self.payment,
      amount=100,
      environment='production',
      state='SUCCEEDED',
      provider_transaction_id='mode-provider',
      checkout_id='mode-checkout',
    )
    self.sale = Sale.objects.create(
      vendor=self.seller,
      payment=self.payment,
      amount=100,
      commission=Decimal('0.35'),
      net_amount=Decimal('99.65'),
    )
    self.refund = Refund.objects.create(seller=self.seller, payment=self.payment, amount=100, description='Synthetic')
    self.gateway = Mock()
    self.gateway.refund_payment.return_value = {
      'outcome': 'CONFIRMED',
      'refund_id': 'mode-refund',
      'original_id': 'mode-provider',
      'amount': Decimal('100.00'),
      'currency': 'USD',
      'code': '000.000.000',
    }

  def test_wrong_successful_pin_cannot_reserve_or_post(self):
    for environment in ('phase1', 'phase2'):
      self.attempt.environment = environment
      self.attempt.save()
      with self.assertRaises(ValueError):
        services.approve_refund_logic(self.refund.pk, self.seller.user, gateway=self.gateway)
      self.seller.refresh_from_db()
      self.refund.refresh_from_db()
      self.assertEqual(self.seller.available_balance, Decimal('150.00'))
      self.assertEqual(self.refund.held_amount, Decimal('0.00'))
      self.assertEqual(self.refund.status, Refund.RefundStatus.PENDING)
      self.gateway.refund_payment.assert_not_called()

  def test_compatible_refund_retains_fee_sale_and_replay_protection(self):
    services.approve_refund_logic(self.refund.pk, self.seller.user, gateway=self.gateway)
    self.seller.refresh_from_db()
    self.payment.refresh_from_db()
    self.sale.refresh_from_db()
    self.assertEqual(self.seller.available_balance, Decimal('50.00'))
    self.assertEqual(self.payment.status, Payment.PaymentStatus.REFUNDED)
    self.assertEqual(self.payment.commission, Decimal('0.35'))
    self.assertEqual(self.sale.commission, Decimal('0.35'))
    with self.assertRaises(ValueError):
      services.approve_refund_logic(self.refund.pk, self.seller.user, gateway=self.gateway)
    self.gateway.refund_payment.assert_called_once_with('mode-provider', Decimal('100.00'))

  def compatible_settings(self, mode):
    return override_settings(
      DATAFAST_ENVIRONMENT=mode,
      DJANGO_ENV='production' if mode == 'production' else 'development',
      STRICT_PROFILE=mode == 'production',
      DEBUG=mode != 'production',
      DATAFAST_BASE_URL='https://eu-prod.oppwa.com/v1/' if mode == 'production' else 'https://eu-test.oppwa.com/v1/',
      DATAFAST_TEST_MODE='' if mode == 'production' else 'EXTERNAL',
    )

  def legacy_fixture(self, mode, pin, suffix, already_held=False):
    payment = Payment.objects.create(
      seller=self.seller,
      description='Legacy fixture',
      subtotal=100,
      amount=100,
      amount_client=100,
      commission=Decimal('0.35'),
      status=Payment.PaymentStatus.PAID,
      state=True,
      transaction_id='legacy-provider-' + suffix,
    )
    if pin is not None:
      PaymentAttempt.objects.create(
        payment=payment,
        amount=100,
        environment=pin,
        state='SUCCEEDED',
        provider_transaction_id=payment.transaction_id,
      )
    Sale.objects.create(
      vendor=self.seller, payment=payment, amount=100, commission=Decimal('0.35'), net_amount=Decimal('99.65')
    )
    if already_held:
      # Historical reservation: no request gate or original RF POST is replayed.
      refund = Refund.objects.create(seller=self.seller, payment=payment, amount=100, description='Legacy hold')
    else:
      with self.compatible_settings(mode):
        refund = services.request_refund(self.seller, payment, 'Legacy fixture')
    result = dict(
      self.gateway.refund_payment.return_value, original_id=payment.transaction_id, refund_id='legacy-refund-' + suffix
    )
    return payment, refund, result

  def test_legacy_blank_and_absent_pins_refund_in_both_contracts_once(self):
    for mode in ('phase2', 'production'):
      for pin in ('', None):
        with self.subTest(mode=mode, pin=pin), self.compatible_settings(mode):
          payment, refund, result = self.legacy_fixture(mode, pin, mode + str(pin))
          self.seller.available_balance = Decimal('150.00')
          self.seller.save(update_fields=['available_balance'])
          gateway = Mock()
          gateway.refund_payment.return_value = result
          services.approve_refund_logic(refund.pk, self.seller.user, gateway=gateway)
          services.settle_refund(refund.pk, result)
          with self.assertRaises(ValueError):
            services.approve_refund_logic(refund.pk, self.seller.user, gateway=gateway)
          gateway.refund_payment.assert_called_once_with(payment.transaction_id, Decimal('100.00'))
          payment.refresh_from_db()
          refund.refresh_from_db()
          self.seller.refresh_from_db()
          self.assertEqual(payment.status, Payment.PaymentStatus.REFUNDED)
          self.assertEqual(refund.held_amount, Decimal('0.00'))
          self.assertEqual(self.seller.available_balance, Decimal('50.00'))
          self.assertEqual(payment.commission, Decimal('0.35'))
          self.assertEqual(Sale.objects.get(payment=payment).commission, Decimal('0.35'))
          self.assertEqual(
            list(PaymentAttempt.objects.filter(payment=payment).values_list('environment', flat=True)),
            [] if pin is None else [''],
          )

  def test_matching_transaction_pin_wins_over_unrelated_blank_attempt(self):
    PaymentAttempt.objects.create(
      payment=self.payment, amount=100, environment='', state='SUCCEEDED', provider_transaction_id='unrelated-provider'
    )
    for mode in ('phase2', 'production'):
      for pin in ('phase1', 'phase2', 'production'):
        with self.subTest(mode=mode, pin=pin), self.compatible_settings(mode):
          self.attempt.environment = pin
          self.attempt.save(update_fields=['environment'])
          self.assertEqual(services._refund_environment_valid(self.payment), mode == pin)
          if mode != pin:
            with self.assertRaises(ValueError):
              services.approve_refund_logic(self.refund.pk, self.seller.user, gateway=self.gateway)
            self.refund.refresh_from_db()
            self.seller.refresh_from_db()
            self.assertEqual(self.refund.held_amount, Decimal('0.00'))
            self.assertEqual(self.seller.available_balance, Decimal('150.00'))
            self.gateway.refund_payment.assert_not_called()

  def test_legacy_open_holds_settle_bound_terminal_results_once_without_post(self):
    for mode in ('phase2', 'production'):
      for state in ('PROCESSING', 'UNKNOWN'):
        for outcome, code in (('CONFIRMED', '000.000.000'), ('DECLINED', '800.100.174')):
          with self.subTest(mode=mode, state=state, outcome=outcome), self.compatible_settings(mode):
            pin = '' if state == 'PROCESSING' else None
            payment, refund, result = self.legacy_fixture(mode, pin, mode + state + outcome, already_held=True)
            Refund.objects.filter(pk=refund.pk).update(
              status=state,
              held_amount=100,
              original_transaction_id=payment.transaction_id,
              initiated_by=self.seller.user,
            )
            self.seller.available_balance = Decimal('50.00')
            self.seller.save(update_fields=['available_balance'])
            result.update(outcome=outcome, code=code)
            services.settle_refund(refund.pk, result)
            services.settle_refund(refund.pk, result)
            with self.assertRaises(ValueError):
              services.approve_refund_logic(refund.pk, self.seller.user, gateway=self.gateway)
            refund.refresh_from_db()
            payment.refresh_from_db()
            self.seller.refresh_from_db()
            self.assertEqual(refund.status, 'APPROVED' if outcome == 'CONFIRMED' else 'REJECTED')
            self.assertEqual(refund.held_amount, Decimal('0.00'))
            self.assertEqual(
              self.seller.available_balance, Decimal('50.00') if outcome == 'CONFIRMED' else Decimal('150.00')
            )
            self.assertEqual(
              payment.status, Payment.PaymentStatus.REFUNDED if outcome == 'CONFIRMED' else Payment.PaymentStatus.PAID
            )
            self.assertEqual(Sale.objects.get(payment=payment).commission, Decimal('0.35'))
    self.gateway.refund_payment.assert_not_called()

  def test_legacy_invalid_observations_retain_open_hold(self):
    for mode in ('phase2', 'production'):
      with self.compatible_settings(mode):
        payment, refund, result = self.legacy_fixture(mode, None, mode + 'invalid', already_held=True)
        Refund.objects.filter(pk=refund.pk).update(
          status='PROCESSING', held_amount=100, original_transaction_id=payment.transaction_id
        )
        self.seller.available_balance = Decimal('50.00')
        self.seller.save(update_fields=['available_balance'])
        variants = (
          None,
          [],
          {'outcome': 'UNKNOWN'},
          dict(result, original_id='wrong'),
          dict(result, amount=Decimal('99.00')),
          dict(result, currency='EUR'),
          dict(result, refund_id='bad/id'),
          dict(result, outcome='DECLINED'),
          dict(result, code='800.100.100'),
        )
        for observation in variants:
          with self.subTest(mode=mode, observation=observation):
            services.settle_refund(refund.pk, observation)
            refund.refresh_from_db()
            self.seller.refresh_from_db()
            payment.refresh_from_db()
            self.assertEqual(refund.status, 'UNKNOWN')
            self.assertEqual(refund.held_amount, Decimal('100.00'))
            self.assertEqual(self.seller.available_balance, Decimal('50.00'))
            self.assertEqual(payment.status, Payment.PaymentStatus.PAID)
        with self.assertRaises(ValueError):
          services.approve_refund_logic(refund.pk, self.seller.user, gateway=self.gateway)
    self.gateway.refund_payment.assert_not_called()

  @override_settings(
    DATAFAST_ENVIRONMENT='phase1',
    DJANGO_ENV='development',
    STRICT_PROFILE=False,
    DEBUG=True,
    DATAFAST_BASE_URL='https://test.oppwa.com/v1/',
    DATAFAST_TEST_MODE='',
    DATAFAST_PHASE1_ENTITY_ID='fake-phase1-entity',
    DATAFAST_PHASE1_AUTH_TOKEN='fake-phase1-token',
  )
  def test_phase1_legacy_refund_denied_before_hold_or_post(self):
    self.attempt.environment = ''
    self.attempt.save(update_fields=['environment'])
    with self.assertRaises(ValueError):
      services.approve_refund_logic(self.refund.pk, self.seller.user, gateway=self.gateway)
    self.refund.refresh_from_db()
    self.seller.refresh_from_db()
    self.assertEqual(self.refund.held_amount, Decimal('0.00'))
    self.assertEqual(self.seller.available_balance, Decimal('150.00'))
    self.gateway.refund_payment.assert_not_called()

  def test_invalid_active_configuration_cannot_enable_legacy_refunds(self):
    self.attempt.environment = ''
    self.attempt.save(update_fields=['environment'])
    for changes in (
      {'DATAFAST_AUTH_TOKEN': ''},
      {'DATAFAST_BASE_URL': 'https://eu-test.oppwa.com/v1/'},
      {'DATAFAST_ENVIRONMENT': 'phase2'},
      {'DEBUG': True},
    ):
      with self.subTest(changes=changes), override_settings(**changes):
        with self.assertRaises(ValueError):
          services.approve_refund_logic(self.refund.pk, self.seller.user, gateway=self.gateway)
        self.refund.refresh_from_db()
        self.assertEqual(self.refund.held_amount, Decimal('0.00'))
    self.gateway.refund_payment.assert_not_called()
