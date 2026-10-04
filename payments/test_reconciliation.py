"""Synthetic fixtures only; these are NOT observed live provider contracts."""

from copy import deepcopy
from decimal import Decimal
from io import StringIO
from typing import Any
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TransactionTestCase, override_settings

from accounts.models import CustomUser
from payments import reconciliation
from payments.models import Link, Payment, PaymentAttempt, Refund, Sale
from payments.services import process_payment_result


@override_settings(DATAFAST_BASE_URL='https://eu-prod.oppwa.com/v1/', DATAFAST_TEST_MODE='')
class ReconciliationTests(TransactionTestCase):
  def setUp(self):
    self.seller = CustomUser.objects.create(user=User.objects.create_user('seller'), identification=1234567890)
    self.link = Link.objects.create(seller=self.seller, subtotal=100, amount=100)
    self.payment = Payment.objects.create(
      seller=self.seller, link=self.link, subtotal=100, amount=100, amount_client=100
    )
    self.attempt = PaymentAttempt.objects.create(payment=self.payment, amount=100, checkout_id='checkout')
    self.gateway = Mock()
    self.gateway.normalize_refund_observation.side_effect = self.normalizer
    self.gateway.query_by_merchant_id.side_effect = self.query
    self.gateway.query_by_provider_id.side_effect = self.query
    self.payload: Any = self.debit()

  @staticmethod
  def normalizer(*args):
    from gateways.services import DatafastClient

    return DatafastClient().normalize_refund_observation(*args)

  def query(self, identity):
    self.assertFalse(connection.in_atomic_block, 'GET must run outside database transactions')
    return deepcopy(self.payload)

  def debit(self, **changes):
    record = {
      'id': 'debit',
      'merchantTransactionId': self.attempt.merchant_transaction_id,
      'paymentType': 'DB',
      'amount': '100.00',
      'currency': 'USD',
      'result': {'code': '000.000.000'},
    }
    record.update(changes)
    return record

  def refund(self):
    process_payment_result(self.payment.pk, self.debit(), attempt_id=self.attempt.pk)
    self.seller.available_balance = Decimal(0)
    self.seller.save(update_fields=['available_balance'])
    self.refund_record = Refund.objects.create(
      payment=self.payment,
      seller=self.seller,
      amount=100,
      held_amount=100,
      original_transaction_id='debit',
      status='UNKNOWN',
    )
    self.payload = {
      'id': 'refund',
      'referencedId': 'debit',
      'paymentType': 'RF',
      'merchantTransactionId': self.attempt.merchant_transaction_id,
      'amount': '100.00',
      'currency': 'USD',
      'result': {'code': '000.000.000'},
    }

  def run_apply(self):
    return reconciliation.reconcile(limit=50, apply=True, gateway=self.gateway)

  def assert_no_credit(self):
    self.seller.refresh_from_db()
    self.assertEqual(self.seller.available_balance, 0)
    self.assertEqual(Sale.objects.count(), 0)

  def test_dry_run_neither_io_nor_writes(self):
    before = PaymentAttempt.objects.values().get()
    output = reconciliation.reconcile(limit=50, gateway=self.gateway)
    self.assertEqual(len(output), 1)
    self.assertEqual(PaymentAttempt.objects.values().get(), before)
    self.gateway.query_by_merchant_id.assert_not_called()
    self.gateway.query_by_provider_id.assert_not_called()
    self.assert_no_credit()

  def test_expired_debit_credits_once_and_skips_historical_records(self):
    self.attempt.state = 'EXPIRED'
    self.attempt.save()
    self.payload = {'payments': [self.debit()]}
    self.run_apply()
    self.assertEqual(self.run_apply(), [])
    self.seller.refresh_from_db()
    self.assertEqual(self.seller.available_balance, Decimal('99.65'))
    self.assertEqual(Sale.objects.count(), 1)
    self.gateway.query_by_merchant_id.assert_called_once_with(self.attempt.merchant_transaction_id)
    self.gateway.refund_payment.assert_not_called()
    self.gateway.prepare_checkout.assert_not_called()

  def test_stored_provider_id_is_preferred(self):
    self.attempt.provider_transaction_id = 'debit'
    self.attempt.save()
    self.run_apply()
    self.gateway.query_by_provider_id.assert_called_once_with('debit')
    self.gateway.query_by_merchant_id.assert_not_called()

  def test_invalid_ambiguous_and_incomplete_debits_never_credit(self):
    variants = [
      None,
      {},
      {'payments': []},
      {'payments': [self.debit(), self.debit()]},
      {'payments': [self.debit()] * 101},
      {'payments': [self.debit(), {}]},
      {'payments': [self.debit()], 'next': 'page'},
      {'payments': [self.debit()], 'total': 2},
      {'transactions': [self.debit()]},
      {'payments': [self.debit(), self.debit(id='other')]},
      self.debit(id='foreign', merchantTransactionId='foreign'),
      self.debit(amount='99.99'),
      self.debit(amount=100.0),
      self.debit(amount='100.000000000000000001'),
      self.debit(currency='EUR'),
      self.debit(paymentType='RF'),
      self.debit(id=None),
      self.debit(result={'code': '000.400.010'}),
      self.debit(result={'code': 'bad'}),
    ]
    for field in self.debit():
      missing = self.debit()
      missing.pop(field)
      variants.append(missing)
    for payload in variants:
      with self.subTest(payload=payload):
        self.payload = payload
        self.run_apply()
        self.assert_no_credit()
    self.gateway.refund_payment.assert_not_called()

  def test_valid_typed_sibling_is_ignored_but_malformed_sibling_blocks(self):
    sibling = {
      'id': 'refund',
      'referencedId': 'debit',
      'paymentType': 'RF',
      'amount': '100.00',
      'currency': 'USD',
      'result': {'code': '000.000.000'},
    }
    self.payload = {'payments': [self.debit(), dict(sibling, amount=None)]}
    self.run_apply()
    self.assert_no_credit()
    self.payload = {'payments': [sibling, self.debit()]}
    self.run_apply()
    self.assertEqual(Sale.objects.count(), 1)

  def test_refund_consumes_hold_once_preserving_fee_and_history(self):
    self.refund()
    self.payload = {'payments': [self.debit(), self.payload]}
    self.run_apply()
    self.assertEqual(self.run_apply(), [])
    self.refund_record.refresh_from_db()
    self.payment.refresh_from_db()
    self.seller.refresh_from_db()
    self.assertEqual(self.refund_record.status, 'APPROVED')
    self.assertEqual(self.refund_record.held_amount, 0)
    self.assertEqual(self.payment.status, 'REFUNDED')
    self.assertEqual(self.payment.commission, Decimal('0.35'))
    self.assertEqual(Sale.objects.get().commission, Decimal('0.35'))
    self.assertEqual(self.seller.available_balance, 0)
    self.gateway.refund_payment.assert_not_called()

  def test_refund_unavailable_foreign_and_unknown_hold_funds(self):
    self.refund()
    valid = deepcopy(self.payload)
    variants = [
      None,
      {},
      {'payments': []},
      {'payments': [valid, valid]},
      {'payments': [valid], 'pagination': {}},
      dict(valid, referencedId='foreign'),
      dict(valid, merchantTransactionId='foreign'),
      dict(valid, amount='99.99'),
      dict(valid, currency='EUR'),
      dict(valid, paymentType='DB'),
      dict(valid, id=None),
      dict(valid, result={'code': '000.400.010'}),
      dict(valid, result={'code': 'bad'}),
    ]
    for field in valid:
      missing = deepcopy(valid)
      missing.pop(field)
      variants.append(missing)
    for payload in variants:
      with self.subTest(payload=payload):
        # Each case exercises merchant fallback independently. A fully bound
        # UNKNOWN code can legitimately persist the RF ID for a later query.
        self.refund_record.provider_refund_id = None
        self.refund_record.save(update_fields=['provider_refund_id'])
        self.payload = payload
        self.run_apply()
        self.refund_record.refresh_from_db()
        self.seller.refresh_from_db()
        self.assertEqual(self.refund_record.held_amount, 100)
        self.assertEqual(self.seller.available_balance, 0)
    self.gateway.refund_payment.assert_not_called()

  def test_refund_provider_query_and_bound_decline_release_once(self):
    self.refund()
    self.refund_record.provider_refund_id = 'refund'
    self.refund_record.save()
    self.payload.pop('merchantTransactionId')
    self.payload['result']['code'] = '800.100.174'
    self.run_apply()
    self.run_apply()
    self.refund_record.refresh_from_db()
    self.seller.refresh_from_db()
    self.assertEqual(self.refund_record.status, 'REJECTED')
    self.assertEqual(self.refund_record.held_amount, 0)
    self.assertEqual(self.seller.available_balance, 100)
    self.gateway.query_by_provider_id.assert_called_once_with('refund')

  def test_legacy_identity_gap_and_terminal_records_skip_io(self):
    self.refund()
    PaymentAttempt.objects.filter(pk=self.attempt.pk).update(state='UNKNOWN')
    self.run_apply()
    self.gateway.query_by_merchant_id.assert_not_called()
    self.refund_record.status = 'APPROVED'
    self.refund_record.save()
    self.assertEqual(self.run_apply(), [])

  def test_unavailability_does_not_write_or_send_post(self):
    self.refund()
    before = Refund.objects.values().get()
    self.gateway.query_by_merchant_id.side_effect = RuntimeError('private')
    self.run_apply()
    self.assertEqual(Refund.objects.values().get(), before)
    self.gateway.refund_payment.assert_not_called()

  def test_selection_is_globally_bounded_and_scopes_are_internal(self):
    second = Payment.objects.create(seller=self.seller, link=self.link, subtotal=100, amount=100, amount_client=100)
    second_attempt = PaymentAttempt.objects.create(payment=second, amount=100, checkout_id='second')
    self.assertEqual(len(reconciliation.reconcile(limit=1)), 1)
    scoped = reconciliation.reconcile(limit=1, attempt_ids=[second_attempt.pk])
    self.assertEqual([row['id'] for row in scoped], [second_attempt.pk])
    self.refund()
    scoped = reconciliation.reconcile(limit=1, refund_ids=[self.refund_record.pk])
    self.assertEqual([row['kind'] for row in scoped], ['refund'])
    self.assertEqual(len(reconciliation.reconcile(limit=1)), 1)

  def test_settler_revalidates_after_unlocked_get(self):
    def stale_query(identity):
      self.assertFalse(connection.in_atomic_block)
      process_payment_result(self.payment.pk, self.debit(), attempt_id=self.attempt.pk)
      return self.debit()

    self.gateway.query_by_merchant_id.side_effect = stale_query
    self.run_apply()
    self.seller.refresh_from_db()
    self.assertEqual(self.seller.available_balance, Decimal('99.65'))
    self.assertEqual(Sale.objects.count(), 1)

  def test_stored_identity_conflicts_and_query_metadata_never_settle(self):
    self.attempt.provider_transaction_id = 'known'
    self.attempt.save()
    for payload in (
      self.debit(),
      dict(self.debit(id='known'), next='page'),
      {'payments': [self.debit(id='known')], 'result': {'code': '800.100.174'}},
      self.debit(id='known', result={'code': '000.000.000', 'next': 'page'}),
    ):
      self.payload = payload
      self.run_apply()
      self.assert_no_credit()
    self.attempt.provider_transaction_id = None
    self.attempt.save()
    self.refund()
    self.refund_record.provider_refund_id = 'known-refund'
    self.refund_record.save()
    self.run_apply()
    self.refund_record.refresh_from_db()
    self.assertEqual(self.refund_record.held_amount, 100)

  def test_command_default_scopes_limits_and_mocked_apply(self):
    out = StringIO()
    with patch('payments.reconciliation.DatafastClient') as client:
      call_command('datafast_reconcile', stdout=out)
      client.assert_not_called()
    self.assertIn('dry-run', out.getvalue())
    self.assert_no_credit()
    for limit in ('0', '-1', '201', 'bad'):
      with self.assertRaises(CommandError):
        call_command('datafast_reconcile', '--limit', limit, stdout=StringIO())
    with self.assertRaises(CommandError):
      call_command('datafast_reconcile', '--attempt-id', '0', stdout=StringIO())
    self.assertEqual(reconciliation.reconcile(limit=1, attempt_ids=[self.attempt.pk + 1]), [])
    with patch('payments.reconciliation.DatafastClient', return_value=self.gateway):
      call_command('datafast_reconcile', '--apply', '--attempt-id', str(self.attempt.pk), stdout=StringIO())
    self.assertEqual(Sale.objects.count(), 1)
