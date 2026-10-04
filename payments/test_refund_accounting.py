"""Refund ledger behavior, using mocked provider I/O and committed reservations."""

from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.db import connection, transaction
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from accounts.models import Contract, CustomUser
from banking.models import Bank, DisbursementRequest, PaymentMethod
from banking.services import process_disbursement
from payments import services
from payments.models import Payment, Refund, Sale


class RefundAccountingTests(TransactionTestCase):
  def setUp(self):
    self.user = User.objects.create_user(username='seller')
    self.seller = CustomUser.objects.create(user=self.user, identification=1, available_balance=Decimal('100.00'))
    self.admin = User.objects.create_user(username='admin')
    CustomUser.objects.create(user=self.admin, identification=2, is_admin_role=True)
    Contract.objects.create(seller=self.seller, ip='127.0.0.1', city='Test')
    self.payment = Payment.objects.create(
      seller=self.seller,
      subtotal=100,
      amount=100,
      amount_client=100,
      commission=Decimal('.35'),
      status='PAID',
      state=True,
      transaction_id='original-1',
    )
    self.sale = Sale.objects.create(
      vendor=self.seller, payment=self.payment, amount=100, commission=Decimal('.35'), net_amount=Decimal('99.65')
    )
    self.refund = Refund.objects.create(seller=self.seller, payment=self.payment, description='Full refund', amount=100)
    self.gateway = Mock()
    self.gateway.refund_payment.return_value = self.result()

  def result(self, outcome='CONFIRMED', **changes):
    data = dict(
      outcome=outcome,
      original_id='original-1',
      refund_id='refund-1',
      amount=Decimal('100.00'),
      currency='USD',
      code='800.100.174' if outcome == 'DECLINED' else '000.000.000',
    )
    data.update(changes)
    return data

  def approve(self):
    return services.approve_refund_logic(self.refund.pk, self.admin, gateway=self.gateway)

  def refresh(self):
    for obj in (self.seller, self.payment, self.refund, self.sale):
      obj.refresh_from_db()

  def test_request_full_amount_and_duplicate_guard(self):
    other = Payment.objects.create(
      seller=self.seller, subtotal=10, amount=10, amount_client=10, status='PAID', state=True
    )
    refund = services.request_refund(self.seller, other, 'Requested')
    self.assertEqual(refund.amount, Decimal(10))
    self.assertEqual(refund.status, 'PENDING')
    with self.assertRaises(ValueError):
      services.request_refund(self.seller, other, 'Again')

  def test_request_reloads_paid_state_and_checks_ownership(self):
    with self.assertRaises(ValueError):
      services.request_refund(self.admin.customuser, self.payment, 'Foreign')
    other = Payment.objects.create(seller=self.seller, subtotal=10, amount=10, amount_client=10, status='PAID')
    Payment.objects.filter(pk=other.pk).update(status='REFUNDED')
    with self.assertRaises(ValueError):
      services.request_refund(self.seller, other, 'Stale')

  def test_provider_sees_committed_hold_and_repeat_cannot_send(self):
    def provider(original_id, amount):
      self.assertFalse(connection.in_atomic_block)
      self.refresh()
      self.assertEqual(self.refund.status, 'PROCESSING')
      self.assertEqual(self.refund.held_amount, Decimal(100))
      self.assertEqual(self.seller.available_balance, Decimal(0))
      self.assertEqual(self.refund.original_transaction_id, original_id)
      self.assertEqual(self.refund.initiated_by, self.admin)
      self.assertIsNotNone(self.refund.initiated_at)
      with self.assertRaises(ValueError):
        self.approve()
      return self.result()

    self.gateway.refund_payment.side_effect = provider
    self.approve()
    self.gateway.refund_payment.assert_called_once_with('original-1', Decimal(100))
    self.refresh()
    self.assertEqual(self.refund.status, 'APPROVED')
    self.assertEqual(self.refund.held_amount, 0)
    self.assertEqual(self.seller.available_balance, 0)
    self.assertEqual(self.payment.status, 'REFUNDED')
    self.assertFalse(self.payment.state)
    self.assertEqual(self.payment.commission, Decimal('.35'))
    self.assertEqual(self.sale.net_amount, Decimal('99.65'))
    self.assertEqual(self.sale.commission, Decimal('.35'))
    self.assertEqual(self.refund.provider_refund_id, 'refund-1')
    self.assertEqual(self.refund.processed_by, self.admin)
    services.process_payment_result(self.payment.pk, {'result': {'code': '000.000.000'}})
    self.refresh()
    self.assertEqual(self.seller.available_balance, 0)
    self.assertEqual(Sale.objects.filter(payment=self.payment).count(), 1)

  def test_fee_shortfall_rejected_before_external_call(self):
    self.seller.available_balance = Decimal('99.65')
    self.seller.save()
    with self.assertRaisesMessage(ValueError, 'Saldo insuficiente'):
      self.approve()
    self.gateway.refund_payment.assert_not_called()
    self.refresh()
    self.assertEqual(self.refund.status, 'PENDING')
    self.assertEqual(self.refund.held_amount, 0)
    self.assertEqual(self.seller.available_balance, Decimal('99.65'))

  def test_decline_releases_once_and_preserves_paid_history(self):
    self.gateway.refund_payment.return_value = self.result('DECLINED')
    self.approve()
    services.settle_refund(self.refund.pk, self.result('DECLINED'))
    with self.assertRaises(ValueError):
      self.approve()
    self.refresh()
    self.assertEqual(self.refund.status, 'REJECTED')
    self.assertEqual(self.refund.held_amount, 0)
    self.assertEqual(self.refund.result_code, '800.100.174')
    self.assertEqual(self.seller.available_balance, 100)
    self.assertEqual(self.payment.status, 'PAID')
    self.assertTrue(self.payment.state)
    self.gateway.refund_payment.assert_called_once()

  def test_unknown_and_exception_hold_without_resend(self):
    self.gateway.refund_payment.side_effect = RuntimeError('sensitive provider detail')
    self.approve()
    self.refresh()
    self.assertEqual(self.refund.status, 'UNKNOWN')
    self.assertEqual(self.refund.held_amount, 100)
    self.assertEqual(self.seller.available_balance, 0)
    self.assertIsNone(self.refund.processed_at)
    self.assertNotIn('sensitive', str(self.refund.history))
    with self.assertRaises(ValueError):
      self.approve()
    self.gateway.refund_payment.assert_called_once()
    services.settle_refund(self.refund.pk, self.result())
    services.settle_refund(self.refund.pk, self.result())
    self.refresh()
    self.assertEqual(self.refund.status, 'APPROVED')
    self.assertEqual(self.seller.available_balance, 0)

  def test_malformed_or_foreign_normalized_results_keep_hold(self):
    variants = [
      None,
      {},
      self.result(original_id='foreign'),
      self.result(amount=Decimal('99.65')),
      self.result(currency='EUR'),
      self.result(refund_id=''),
      self.result(refund_id='original-1'),
      self.result(code='000.000.999'),
      self.result('DECLINED', original_id='foreign'),
      self.result(amount=100.0),
      self.result(refund_id='../foreign'),
    ]
    for result in variants:
      with self.subTest(result=result):
        # Each case starts from the same committed unresolved hold.
        if not Refund.objects.get(pk=self.refund.pk).held_amount:
          self.gateway.refund_payment.return_value = {'outcome': 'UNKNOWN'}
          self.approve()
        services.settle_refund(self.refund.pk, result)
        self.refresh()
        self.assertEqual(self.refund.status, 'UNKNOWN')
        self.assertEqual(self.refund.held_amount, 100)
        self.assertEqual(self.seller.available_balance, 0)
        self.assertEqual(self.payment.status, 'PAID')

  def test_crash_after_reservation_keeps_processing_and_blocks_retry(self):
    self.gateway.refund_payment.side_effect = KeyboardInterrupt()
    with self.assertRaises(KeyboardInterrupt):
      self.approve()
    self.refresh()
    self.assertEqual(self.refund.status, 'PROCESSING')
    self.assertEqual(self.refund.held_amount, 100)
    with self.assertRaises(ValueError):
      self.approve()
    services.settle_refund(self.refund.pk, self.result())
    self.refresh()
    self.assertEqual(self.refund.status, 'APPROVED')

  def test_finalization_failure_preserves_hold_not_resend(self):
    with patch('payments.services.settle_refund', side_effect=RuntimeError('DB unavailable')):
      self.approve()
    self.refresh()
    self.assertIn(self.refund.status, ['PROCESSING', 'UNKNOWN'])
    self.assertEqual(self.refund.held_amount, 100)
    self.assertEqual(self.seller.available_balance, 0)
    with self.assertRaises(ValueError):
      self.approve()
    self.gateway.refund_payment.assert_called_once()

  def test_partial_db_transition_rolls_back_after_provider_confirmation(self):
    record = services._record_refund

    def fail_terminal(refund, state, *args):
      if state == 'APPROVED':
        raise RuntimeError('DB write failed')
      return record(refund, state, *args)

    with patch('payments.services._record_refund', side_effect=fail_terminal):
      self.approve()
    self.refresh()
    self.assertEqual(self.refund.status, 'PROCESSING')
    self.assertEqual(self.refund.held_amount, 100)
    self.assertEqual(self.payment.status, 'PAID')
    self.assertEqual(self.seller.available_balance, 0)
    with self.assertRaises(ValueError):
      self.approve()
    services.settle_refund(self.refund.pk, self.result())
    self.refresh()
    self.assertEqual(self.refund.status, 'APPROVED')
    self.assertEqual(self.seller.available_balance, 0)
    self.gateway.refund_payment.assert_called_once()

  def test_conflicting_provider_identity_keeps_hold(self):
    other = Payment.objects.create(seller=self.seller, subtotal=1, amount=1, amount_client=1)
    Refund.objects.create(seller=self.seller, payment=other, amount=1, status='APPROVED', provider_refund_id='refund-1')
    self.approve()
    self.refresh()
    self.assertEqual(self.refund.status, 'UNKNOWN')
    self.assertEqual(self.refund.held_amount, 100)
    self.assertEqual(self.seller.available_balance, 0)

  def test_test_connector_confirmation_is_not_production_approval(self):
    self.gateway.refund_payment.return_value = {'outcome': 'UNKNOWN'}
    self.approve()
    result = self.result(code='000.100.112')
    for base, mode in [
      ('https://eu-prod.oppwa.com', 'EXTERNAL'),
      ('https://eu-test.oppwa.com', ''),
      ('https://eu-test.oppwa.com:443', 'EXTERNAL'),
    ]:
      with self.subTest(base=base, mode=mode), override_settings(DATAFAST_BASE_URL=base, DATAFAST_TEST_MODE=mode):
        services.settle_refund(self.refund.pk, result)
        self.refresh()
        self.assertEqual(self.refund.status, 'UNKNOWN')
        self.assertEqual(self.refund.held_amount, 100)
    with override_settings(DATAFAST_BASE_URL='https://eu-test.oppwa.com', DATAFAST_TEST_MODE='EXTERNAL'):
      services.settle_refund(self.refund.pk, result)
    self.refresh()
    self.assertEqual(self.refund.status, 'APPROVED')
    self.assertEqual(self.seller.available_balance, 0)

  def test_changed_payment_binding_after_rf_keeps_hold(self):
    self.gateway.refund_payment.return_value = {'outcome': 'UNKNOWN'}
    self.approve()
    for changes in [{'transaction_id': 'changed-original'}, {'amount': 99}, {'seller': self.admin.customuser}]:
      with self.subTest(changes=changes):
        Payment.objects.filter(pk=self.payment.pk).update(**changes)
        services.settle_refund(self.refund.pk, self.result())
        self.refresh()
        self.assertEqual(self.refund.status, 'UNKNOWN')
        self.assertEqual(self.refund.held_amount, 100)
        self.assertEqual(self.seller.available_balance, 0)
        Payment.objects.filter(pk=self.payment.pk).update(transaction_id='original-1', amount=100, seller=self.seller)

  def test_observed_unknown_identity_cannot_be_replaced(self):
    self.gateway.refund_payment.return_value = self.result('UNKNOWN', code='000.200.000')
    self.approve()
    services.settle_refund(self.refund.pk, self.result(refund_id='foreign-refund'))
    self.refresh()
    self.assertEqual(self.refund.status, 'UNKNOWN')
    self.assertEqual(self.refund.provider_refund_id, 'refund-1')
    self.assertEqual(self.refund.held_amount, 100)
    services.settle_refund(self.refund.pk, self.result())
    self.refresh()
    self.assertEqual(self.refund.status, 'APPROVED')

  def test_outer_transaction_rejected_before_reservation(self):
    with transaction.atomic(), self.assertRaises(ValueError):
      self.approve()
    self.gateway.refund_payment.assert_not_called()
    self.refresh()
    self.assertEqual(self.refund.status, 'PENDING')

  def test_invalid_binding_or_historic_refund_never_calls_provider(self):
    variants = [{'amount': Decimal('99.65')}, {'seller': self.admin.customuser}]
    for changes in variants:
      with self.subTest(changes=changes):
        Refund.objects.filter(pk=self.refund.pk).update(**changes)
        with self.assertRaises(ValueError):
          self.approve()
        Refund.objects.filter(pk=self.refund.pk).update(amount=100, seller=self.seller)
    for status in ['REFUNDED', 'FAILED', 'PENDING']:
      Payment.objects.filter(pk=self.payment.pk).update(status=status)
      with self.assertRaises(ValueError):
        self.approve()
    self.gateway.refund_payment.assert_not_called()

  def test_legacy_approved_no_hold_is_not_rewritten(self):
    Refund.objects.filter(pk=self.refund.pk).update(status='APPROVED')
    services.settle_refund(self.refund.pk, self.result())
    with self.assertRaises(ValueError):
      self.approve()
    self.refresh()
    self.assertEqual(self.refund.held_amount, 0)
    self.assertEqual(self.payment.status, 'PAID')
    self.assertEqual(self.seller.available_balance, 100)
    self.gateway.refund_payment.assert_not_called()

  def test_payout_cannot_spend_hold(self):
    method = PaymentMethod.objects.create(
      seller=self.seller, bank=Bank.objects.create(title='Test'), fullname='Test', account_number='123'
    )
    payout = DisbursementRequest.objects.create(vendor=self.seller, method=method, amount=1)

    def provider(*args):
      result = process_disbursement(payout.pk, 'APPROVED', self.admin)
      self.assertEqual(result.status, 'REJECTED')
      return {'outcome': 'UNKNOWN'}

    self.gateway.refund_payment.side_effect = provider
    self.approve()
    self.refresh()
    self.assertEqual(self.seller.available_balance, 0)
    self.assertEqual(self.refund.held_amount, 100)

  def test_payout_first_leaves_insufficient_gross_funds(self):
    method = PaymentMethod.objects.create(
      seller=self.seller, bank=Bank.objects.create(title='Test'), fullname='Test', account_number='123'
    )
    payout = DisbursementRequest.objects.create(vendor=self.seller, method=method, amount=Decimal('.35'))
    self.assertEqual(process_disbursement(payout.pk, 'APPROVED', self.admin).status, 'APPROVED')
    with self.assertRaisesMessage(ValueError, 'Saldo insuficiente'):
      self.approve()
    self.gateway.refund_payment.assert_not_called()
    self.refresh()
    self.assertEqual(self.seller.available_balance, Decimal('99.65'))
    self.assertEqual(self.refund.held_amount, 0)

  def test_seller_ui_shows_every_actual_status(self):
    self.client.force_login(self.user)
    for status, label in [
      ('PENDING', 'Pendiente'),
      ('PROCESSING', 'Procesando'),
      ('UNKNOWN', 'Desconocido'),
      ('APPROVED', 'Aprobado'),
      ('REJECTED', 'Rechazado'),
    ]:
      with self.subTest(status=status):
        Refund.objects.filter(pk=self.refund.pk).update(status=status)
        response = self.client.get(reverse('payments:refund_list'))
        self.assertContains(response, f'>{label}</span>')
        if status != 'APPROVED':
          self.assertNotContains(response, '>Aprobado</span>')
        if status in ['PROCESSING', 'UNKNOWN']:
          self.client.force_login(self.admin)
          response = self.client.get(reverse('payments:admin_refund_list'))
          self.assertContains(response, label)
          self.assertContains(response, 'disabled')
          self.client.force_login(self.user)

  def test_seller_request_view_ownership_and_existing_status(self):
    self.client.force_login(self.user)
    response = self.client.get(reverse('payments:refund_request', args=[self.payment.pk]))
    self.assertContains(response, 'Solicitud existente: Pendiente')
    self.assertContains(response, 'disabled')
    foreign = Payment.objects.create(seller=self.admin.customuser, subtotal=1, amount=1, amount_client=1, status='PAID')
    response = self.client.post(reverse('payments:refund_request', args=[foreign.pk]), {'description': 'Foreign'})
    self.assertEqual(response.status_code, 404)
    self.assertFalse(Refund.objects.filter(payment=foreign).exists())

  def test_admin_authorization_and_unknown_visibility(self):
    url = reverse('payments:admin_refund_approve', args=[self.refund.pk])
    with patch('gateways.services.DatafastClient.refund_payment') as provider:
      self.assertEqual(self.client.post(url).status_code, 302)
      self.client.force_login(self.user)
      self.assertEqual(self.client.post(url).status_code, 302)
      provider.assert_not_called()
    self.gateway.refund_payment.return_value = {'outcome': 'UNKNOWN'}
    self.approve()
    self.client.force_login(self.admin)
    response = self.client.get(reverse('payments:admin_refund_list'))
    self.assertContains(response, 'Desconocido')
    self.assertContains(response, 'No reenviar')
    self.assertNotContains(response, f'action="{url}"')
    self.client.force_login(self.user)
    response = self.client.get(reverse('payments:refund_list'))
    self.assertContains(response, 'Desconocido')
    self.assertNotContains(response, '>Aprobado<')

  def test_admin_insufficient_funds_and_unknown_messages(self):
    self.client.force_login(self.admin)
    url = reverse('payments:admin_refund_approve', args=[self.refund.pk])
    self.seller.available_balance = Decimal('99.65')
    self.seller.save()
    with patch('gateways.services.DatafastClient.refund_payment') as provider:
      response = self.client.post(url, follow=True)
      self.assertContains(response, 'Saldo insuficiente')
      provider.assert_not_called()
    self.seller.available_balance = 100
    self.seller.save()
    with patch(
      'gateways.services.DatafastClient.refund_payment', side_effect=RuntimeError('private-token')
    ) as provider:
      response = self.client.post(url, follow=True)
      self.assertContains(response, 'No reenviar')
      self.assertNotContains(response, 'private-token')
      self.assertNotContains(response, 'aprobado y procesado')
      self.client.post(url)
      provider.assert_called_once()
