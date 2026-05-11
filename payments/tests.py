from decimal import Decimal

from django.contrib.auth.models import User
from django.core import mail
from django.conf import settings
from django.test import TestCase, RequestFactory

from accounts.models import CustomUser
from payments.models import Link, Payment


class SendPaymentInviteTest(TestCase):
    """Approval tests for payments.services.send_payment_invite (C2)."""

    def setUp(self) -> None:
        self.factory = RequestFactory()
        django_user = User.objects.create_user(
            username='seller@test.com',
            email='seller@test.com',
            password='pass123',
            first_name='Seller',
            last_name='Name',
        )
        self.seller = CustomUser.objects.create(
            user=django_user, phone='0999999999', identification=1234567890,
        )
        self.link = Link.objects.create(
            seller=self.seller,
            description='Test Link',
            tax_type=Link.TaxType.VAT_15,
            vat_rate=Decimal('0.15'),
            include_igv=True,
            subtotal=Decimal('100.00'),
            igv=Decimal('15.00'),
            amount=Decimal('115.00'),
        )
        self.payment = Payment.objects.create(
            link=self.link,
            seller=self.seller,
            first_name='Cliente',
            last_name='Pago',
            email='cliente@example.com',
            identify='1234567890',
            phone='0987654321',
            description='Pago de prueba',
            subtotal=Decimal('100.00'),
            igv=Decimal('15.00'),
            amount_client=Decimal('115.00'),
            amount=Decimal('115.00'),
        )

    def test_invite_uses_default_from_email(self) -> None:
        """C2: send_payment_invite must use settings.DEFAULT_FROM_EMAIL."""
        from payments.services import send_payment_invite

        request = self.factory.get('/')
        send_payment_invite(self.payment, request)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, settings.DEFAULT_FROM_EMAIL)

    def test_invite_subject_and_recipient(self) -> None:
        """C2: Email subject includes seller name, recipient matches payment email."""
        from payments.services import send_payment_invite

        request = self.factory.get('/')
        send_payment_invite(self.payment, request)

        msg = mail.outbox[0]
        self.assertIn('invitación', msg.subject.lower())
        self.assertIn('Seller Name', msg.subject)
        self.assertIn(self.payment.email, msg.to)

    def test_invite_contains_pay_url(self) -> None:
        """C2: Email body must contain the payment URL."""
        from payments.services import send_payment_invite

        request = self.factory.get('/')
        send_payment_invite(self.payment, request)

        msg = mail.outbox[0]
        html_body = next(content for content, mime in msg.alternatives if mime == 'text/html')
        self.assertIn('/payments/pay/', html_body, 'Invite email must contain pay URL')

    def test_invite_no_email_returns_early(self) -> None:
        """C2: If payment has no email, function returns without sending."""
        from payments.services import send_payment_invite

        self.payment.email = ''
        self.payment.save()
        request = self.factory.get('/')
        send_payment_invite(self.payment, request)

        self.assertEqual(len(mail.outbox), 0, 'Should not send email when payment has no email')


class SendPaymentConfirmationTest(TestCase):
    """Approval tests for payments.services.send_payment_confirmation (C3)."""

    def setUp(self) -> None:
        django_user = User.objects.create_user(
            username='seller2@test.com',
            email='seller2@test.com',
            password='pass123',
        )
        self.seller = CustomUser.objects.create(
            user=django_user, phone='0999999998', identification=9876543210,
        )
        self.link = Link.objects.create(
            seller=self.seller,
            description='Confirmation Link',
            tax_type=Link.TaxType.VAT_15,
            vat_rate=Decimal('0.15'),
            include_igv=True,
            subtotal=Decimal('200.00'),
            igv=Decimal('30.00'),
            amount=Decimal('230.00'),
        )
        self.payment = Payment.objects.create(
            link=self.link,
            seller=self.seller,
            first_name='Cliente',
            last_name='Confirmado',
            email='confirmado@example.com',
            identify='9876543210',
            phone='0912345678',
            description='Pago confirmado',
            subtotal=Decimal('200.00'),
            igv=Decimal('30.00'),
            amount_client=Decimal('230.00'),
            amount=Decimal('230.00'),
            status=Payment.PaymentStatus.PAID,
            state=True,
        )

    def test_confirmation_uses_default_from_email(self) -> None:
        """C3: send_payment_confirmation must use settings.DEFAULT_FROM_EMAIL."""
        from payments.services import send_payment_confirmation

        send_payment_confirmation(self.payment)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, settings.DEFAULT_FROM_EMAIL)

    def test_confirmation_subject_and_recipient(self) -> None:
        """C3: Subject includes description and recipient matches payment email."""
        from payments.services import send_payment_confirmation

        send_payment_confirmation(self.payment)

        msg = mail.outbox[0]
        self.assertIn('Comprobante', msg.subject)
        self.assertIn(self.payment.email, msg.to)

    def test_confirmation_contains_payment_info(self) -> None:
        """C3: Email body should reference payment description."""
        from payments.services import send_payment_confirmation

        send_payment_confirmation(self.payment)

        msg = mail.outbox[0]
        html_body = next(content for content, mime in msg.alternatives if mime == 'text/html')
        self.assertIn('Pago confirmado', html_body,
                      'Confirmation email should reference payment description')

    def test_confirmation_no_email_returns_early(self) -> None:
        """C3: If payment has no email, function returns without sending."""
        from payments.services import send_payment_confirmation

        self.payment.email = ''
        self.payment.save()
        send_payment_confirmation(self.payment)

        self.assertEqual(len(mail.outbox), 0, 'Should not send when payment has no email')


class PrintToLoggerTest(TestCase):
    """C4: Verify no print() statements remain for email error handling."""

    def test_accounts_services_no_print_for_errors(self) -> None:
        """C4: accounts/services.py must use logger.error(), not print()."""
        import ast
        import inspect
        from accounts import services as mod

        source = inspect.getsource(mod)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'print':
                    self.fail(
                        f'C4: print() found in accounts/services.py at line {node.lineno}. '
                        'Replace with logger.error()'
                    )

    def test_payments_services_no_print_for_errors(self) -> None:
        """C4: payments/services.py must use logger.error(), not print()."""
        import ast
        import inspect
        from payments import services as mod

        source = inspect.getsource(mod)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'print':
                    self.fail(
                        f'C4: print() found in payments/services.py at line {node.lineno}. '
                        'Replace with logger.error()'
                    )
