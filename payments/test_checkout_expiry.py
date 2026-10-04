from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase

from accounts.models import CustomUser
from gateways.test_checkout_data import synthetic_payer
from payments import services
from payments.models import Link, Payment, PaymentAttempt, Sale


class CheckoutExpiryTests(TestCase):
  def setUp(self):
    self.now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    self.seller = CustomUser.objects.create(user=User.objects.create_user('expiry-seller'), identification=1234567890)
    self.link = Link.objects.create(
      seller=self.seller, description='Recorded charge', subtotal=Decimal('100.00'), amount=Decimal('100.00')
    )
    self.payment = Payment.objects.create(
      seller=self.seller,
      link=self.link,
      description=self.link.description,
      subtotal=self.link.subtotal,
      igv=Decimal('0.00'),
      amount=self.link.amount,
      amount_client=self.link.amount,
    )
    self.payer = synthetic_payer()
    self.gateway = Mock()
    self.gateway.prepare_checkout.side_effect = ['checkout-original', 'checkout-fresh']
    self.clock = patch('payments.services.timezone.now', return_value=self.now)
    self.clock_mock = self.clock.start()
    self.addCleanup(self.clock.stop)
    self.first = self.prepare()

  def prepare(self):
    return services.prepare_payment_checkout(self.payment.pk, self.gateway, self.payer, '198.51.100.42')

  def assert_expired_and_replaced(self, elapsed):
    self.clock_mock.return_value = self.now + elapsed
    fresh = self.prepare()
    self.first.refresh_from_db()
    self.assertEqual(self.first.state, 'EXPIRED')
    self.assertEqual(self.first.history[-1]['reason'], 'checkout_window_elapsed')
    self.assertNotEqual(fresh.pk, self.first.pk)
    self.assertNotEqual(fresh.merchant_transaction_id, self.first.merchant_transaction_id)
    self.assertEqual(fresh.state, 'LIVE')
    self.assertEqual(fresh.checkout_id, 'checkout-fresh')
    self.assertEqual(fresh.amount, self.first.amount)
    self.assertEqual(PaymentAttempt.objects.filter(payment=self.payment).count(), 2)
    self.assertEqual(self.gateway.prepare_checkout.call_count, 2)
    self.assertEqual(self.gateway.prepare_checkout.call_args.kwargs['transaction_id'], fresh.merchant_transaction_id)
    self.assertEqual(
      self.gateway.prepare_checkout.call_args.kwargs['customer_data']['merchant_customer_id'], str(self.payment.pk)
    )
    self.seller.refresh_from_db()
    self.assertEqual(self.seller.available_balance, Decimal('0.00'))
    self.assertFalse(Sale.objects.filter(payment=self.payment).exists())

  def test_just_before_thirty_minutes_reuses_attempt(self):
    self.clock_mock.return_value = self.now + timedelta(minutes=30) - timedelta(microseconds=1)
    reused = self.prepare()
    self.assertEqual(reused.pk, self.first.pk)
    self.assertEqual(reused.merchant_transaction_id, self.first.merchant_transaction_id)
    self.assertEqual(reused.state, 'LIVE')
    self.assertEqual(PaymentAttempt.objects.filter(payment=self.payment).count(), 1)
    self.gateway.prepare_checkout.assert_called_once()

  def test_exactly_thirty_minutes_creates_fresh_attempt(self):
    self.assert_expired_and_replaced(timedelta(minutes=30))

  def test_after_thirty_minutes_creates_fresh_attempt(self):
    self.assert_expired_and_replaced(timedelta(minutes=30, microseconds=1))

  def test_window_uses_last_observation_not_reservation_time(self):
    PaymentAttempt.objects.filter(pk=self.first.pk).update(updated_at=self.now + timedelta(minutes=5), state='UNKNOWN')
    self.clock_mock.return_value = self.now + timedelta(minutes=30)
    reused = self.prepare()
    self.assertEqual(reused.pk, self.first.pk)
    self.assertEqual(reused.state, 'UNKNOWN')
    self.gateway.prepare_checkout.assert_called_once()
    self.assert_expired_and_replaced(timedelta(minutes=35))

  def test_finalized_payment_neither_expires_nor_recredits(self):
    result = {
      'id': 'provider-finalized',
      'merchantTransactionId': self.first.merchant_transaction_id,
      'amount': '100.00',
      'currency': 'USD',
      'paymentType': 'DB',
      'result': {'code': '000.000.000'},
    }
    services.process_payment_result(self.payment.pk, result, self.first.pk)
    self.first.refresh_from_db()
    history = self.first.history
    self.clock_mock.return_value = self.now + timedelta(minutes=31)
    # REFUNDED and legacy FAILED-with-Sale records are also settled guards.
    for status in (Payment.PaymentStatus.PAID, Payment.PaymentStatus.REFUNDED, Payment.PaymentStatus.FAILED):
      with self.subTest(status=status):
        Payment.objects.filter(pk=self.payment.pk).update(status=status, state=False)
        with self.assertRaisesMessage(ValueError, 'Este pago ya ha sido procesado.'):
          self.prepare()
        services.process_payment_result(self.payment.pk, result, self.first.pk)
        self.payment.refresh_from_db()
        self.first.refresh_from_db()
        self.seller.refresh_from_db()
        self.assertEqual(self.payment.status, status)
        self.assertEqual(self.first.state, 'SUCCEEDED')
        self.assertEqual(self.first.history, history)
        self.assertEqual(self.payment.commission, Decimal('0.35'))
        self.assertEqual(self.seller.available_balance, Decimal('99.65'))
        self.assertEqual(Sale.objects.filter(payment=self.payment).count(), 1)
        self.assertEqual(PaymentAttempt.objects.filter(payment=self.payment).count(), 1)
    self.gateway.prepare_checkout.assert_called_once()
