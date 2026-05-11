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


# ══════════════════════════════════════════════════════════════════════
# Phase 3: Payment Management Template Redesign (T3.1-T3.7)
# ══════════════════════════════════════════════════════════════════════

from pathlib import Path


def _read_template(app_name, template_path):
    """Read a template file from an app's templates directory."""
    return (Path(settings.BASE_DIR) / app_name / 'templates' / template_path).read_text()


# ── T3.1: Link List Template ──

class LinkListTemplateTests(TestCase):
    """T3.1: Verify payments/link_list.html uses design-system classes."""

    @property
    def content(self):
        return _read_template('payments', 'payments/link_list.html')

    # ── Design-system classes present ──

    def test_link_list_has_card_modern(self):
        """Link list must use .card-modern for the filter/search card."""
        self.assertIn('card-modern', self.content,
                      'link_list.html must contain card-modern class')

    def test_link_list_has_table_modern(self):
        """Link list must use .table-modern for the links table."""
        self.assertIn('table-modern', self.content,
                      'link_list.html must contain table-modern class')

    def test_link_list_has_btn_primary_auth(self):
        """'Nuevo Link' button must use .btn-primary-auth."""
        self.assertIn('btn-primary-auth', self.content,
                      'link_list.html must use btn-primary-auth for the CTA')

    # ── Empty state component ──

    def test_link_list_has_empty_state(self):
        """Empty state (no links) must use .empty-state component."""
        self.assertIn('empty-state', self.content,
                      'link_list.html must contain empty-state component')

    # ── AdminLTE classes removed ──

    def test_link_list_removes_card_primary(self):
        """Must NOT use AdminLTE card-primary/card-outline."""
        self.assertNotIn('card-primary', self.content,
                         'AdminLTE card-primary must be removed')
        self.assertNotIn('card-outline', self.content,
                         'AdminLTE card-outline must be removed')

    def test_link_list_removes_content_header(self):
        """Must NOT use AdminLTE content-header class."""
        self.assertNotIn('content-header', self.content,
                         'AdminLTE content-header must be removed')

    def test_link_list_removes_adminlte_badges(self):
        """Must NOT use AdminLTE bg-* badge classes."""
        self.assertNotIn('badge bg-success', self.content,
                         'AdminLTE badge bg-success must be removed')
        self.assertNotIn('badge bg-warning', self.content,
                         'AdminLTE badge bg-warning must be removed')
        self.assertNotIn('badge bg-info', self.content,
                         'AdminLTE badge bg-info must be removed')
        self.assertNotIn('badge bg-danger', self.content,
                         'AdminLTE badge bg-danger must be removed')

    # ── Context variables preserved ──

    def test_link_list_preserves_links_variable(self):
        """links context variable must be preserved in for loop."""
        self.assertIn('{% for link in links %}', self.content,
                      'links iteration must be preserved')
        self.assertIn('link.description', self.content,
                      'link.description must be preserved')
        self.assertIn('link.amount', self.content,
                      'link.amount must be preserved')
        self.assertIn('link.active', self.content,
                      'link.active must be preserved')
        self.assertIn('link.unique', self.content,
                      'link.unique must be preserved')

    def test_link_list_preserves_url_tags(self):
        """All URL references must be preserved."""
        self.assertIn("{% url 'payments:link_create' %}", self.content)
        self.assertIn("{% url 'payments:link_detail'", self.content)

    def test_link_list_preserves_copy_js(self):
        """Copy-to-clipboard JS function must be preserved."""
        self.assertIn('copyToClipboard', self.content,
                      'copyToClipboard JS must be preserved')
        self.assertIn('navigator.clipboard', self.content,
                      'Modern clipboard API must be used')


# ── T3.2: Link Form Template ──

class LinkFormTemplateTests(TestCase):
    """T3.2: Verify payments/link_form.html aligns with design-system."""

    @property
    def content(self):
        return _read_template('payments', 'payments/link_form.html')

    def test_link_form_has_btn_primary_auth(self):
        """Submit button must use .btn-primary-auth."""
        self.assertIn('btn-primary-auth', self.content,
                      'link_form.html submit must use btn-primary-auth')

    def test_link_form_preserves_form_fields(self):
        """All form fields must be preserved."""
        self.assertIn('{{ form.subtotal }}', self.content)
        self.assertIn('{{ form.description }}', self.content)
        self.assertIn('{{ form.tax_type }}', self.content)
        self.assertIn('{{ form.include_igv }}', self.content)
        self.assertIn('{{ form.firstname }}', self.content)
        self.assertIn('{{ form.lastname }}', self.content)
        self.assertIn('{{ form.email }}', self.content)
        self.assertIn('{{ form.identity }}', self.content)
        self.assertIn('{{ form.unique }}', self.content)

    def test_link_form_preserves_csrf(self):
        """CSRF token must be preserved."""
        self.assertIn('{% csrf_token %}', self.content)

    def test_link_form_preserves_calculator_js(self):
        """JS calculator must be preserved."""
        self.assertIn('function calcular', self.content,
                      'Calculator JS must be preserved')
        self.assertIn('inputMonto', self.content)
        self.assertIn('lbl_total', self.content)
        self.assertIn('lbl_base', self.content)
        self.assertIn('lbl_iva', self.content)

    def test_link_form_uses_design_tokens(self):
        """Form should reference design-system color tokens."""
        content_lower = self.content.lower()
        self.assertTrue(
            'teal' in content_lower or 'navy' in content_lower or 'design-system' in content_lower,
            'link_form should use design-system tokens'
        )


# ── T3.3: Link Detail Template ──

class LinkDetailTemplateTests(TestCase):
    """T3.3: Verify payments/link_detail.html uses design-system."""

    @property
    def content(self):
        return _read_template('payments', 'payments/link_detail.html')

    def test_link_detail_has_card_modern(self):
        """Config section must use .card-modern."""
        self.assertIn('card-modern', self.content,
                      'link_detail.html must contain card-modern class')

    def test_link_detail_has_table_modern(self):
        """Transaction history must use .table-modern."""
        self.assertIn('table-modern', self.content,
                      'link_detail.html must contain table-modern class')

    def test_link_detail_has_btn_primary_auth(self):
        """Copy link button must use .btn-primary-auth."""
        self.assertIn('btn-primary-auth', self.content,
                      'link_detail.html must use btn-primary-auth for copy button')

    # ── AdminLTE removed ──

    def test_link_detail_removes_card_primary(self):
        """Must NOT use AdminLTE card classes."""
        self.assertNotIn('card-primary', self.content)
        self.assertNotIn('card-outline', self.content)
        self.assertNotIn('card-info', self.content)

    def test_link_detail_removes_content_header(self):
        """Must NOT use AdminLTE content-header."""
        self.assertNotIn('content-header', self.content)

    # ── Context variables preserved ──

    def test_link_detail_preserves_link_variable(self):
        """link context variable and its attributes must be preserved."""
        self.assertIn('link.description', self.content)
        self.assertIn('link.amount', self.content)
        self.assertIn('link.active', self.content)
        self.assertIn('link.unique', self.content)

    def test_link_detail_preserves_payments_loop(self):
        """payments iteration must be preserved."""
        self.assertIn('{% for payment in payments %}', self.content)
        self.assertIn('payment.status', self.content)
        self.assertIn('payment.amount', self.content)
        self.assertIn('payment.transaction_id', self.content)

    def test_link_detail_preserves_copy_js(self):
        """copyToClipboard JS must be preserved."""
        self.assertIn('copyToClipboard', self.content)

    def test_link_detail_preserves_empty_state(self):
        """Empty payments message must be preserved."""
        self.assertIn('{% empty %}', self.content)
        self.assertIn('Aún no hay transacciones', self.content)


# ── T3.4: Payment List Template ──

class PaymentListTemplateTests(TestCase):
    """T3.4: Verify payments/payment_list.html uses design-system."""

    @property
    def content(self):
        return _read_template('payments', 'payments/payment_list.html')

    def test_payment_list_has_card_stat(self):
        """Stats must use .card-stat (replacing small-box)."""
        self.assertIn('card-stat', self.content,
                      'payment_list.html must contain card-stat component')

    def test_payment_list_has_table_modern(self):
        """Transactions table must use .table-modern."""
        self.assertIn('table-modern', self.content,
                      'payment_list.html must contain table-modern class')

    def test_payment_list_has_btn_secondary(self):
        """Export buttons must use .btn-secondary."""
        self.assertIn('btn-secondary', self.content,
                      'payment_list.html export buttons must use btn-secondary')

    # ── AdminLTE removed ──

    def test_payment_list_removes_small_box(self):
        """Stats must NOT use AdminLTE small-box."""
        self.assertNotIn('small-box', self.content,
                         'AdminLTE small-box must be removed from payment_list')

    def test_payment_list_removes_card_primary(self):
        """Must NOT use AdminLTE card-primary/card-outline."""
        self.assertNotIn('card-primary', self.content)
        self.assertNotIn('card-outline', self.content)

    def test_payment_list_removes_content_header(self):
        """Must NOT use AdminLTE content-header."""
        self.assertNotIn('content-header', self.content)

    # ── Context variables preserved ──

    def test_payment_list_preserves_total_collected(self):
        """total_collected context variable must be preserved."""
        self.assertIn('total_collected', self.content)

    def test_payment_list_preserves_payments_loop(self):
        """payments iteration must be preserved."""
        self.assertIn('{% for payment in payments %}', self.content)
        self.assertIn('payment.amount', self.content)
        self.assertIn('payment.status', self.content)
        self.assertIn('payment.transaction_id', self.content)

    def test_payment_list_preserves_export_urls(self):
        """CSV and Excel export URLs must be preserved."""
        self.assertIn("{% url 'payments:export_csv' %}", self.content)
        self.assertIn("{% url 'payments:export_excel' %}", self.content)

    # ── Empty state ──

    def test_payment_list_preserves_empty_message(self):
        """Empty state message must be preserved."""
        self.assertIn('{% empty %}', self.content)
        self.assertIn('No hay transacciones', self.content)


# ── T3.5: Payment Detail Template ──

class PaymentDetailTemplateTests(TestCase):
    """T3.5: Verify payments/payment_detail.html uses design-system."""

    @property
    def content(self):
        return _read_template('payments', 'payments/payment_detail.html')

    def test_payment_detail_has_card_modern(self):
        """Info cards must use .card-modern."""
        self.assertIn('card-modern', self.content,
                      'payment_detail.html must contain card-modern class')

    def test_payment_detail_has_badge_status(self):
        """Payment status must use .badge-status."""
        self.assertIn('badge-status', self.content,
                      'payment_detail.html must use badge-status for payment state')

    def test_payment_detail_has_two_column_layout(self):
        """Must show two-column card layout (grid/flex with two cards)."""
        cards = self.content.count('card-modern')
        self.assertGreaterEqual(cards, 2,
                                'payment_detail must have at least 2 cards (two-column layout)')

    # ── AdminLTE removed ──

    def test_payment_detail_removes_card_classes(self):
        """Must NOT use AdminLTE card-success/card-danger/card-primary."""
        self.assertNotIn('card-success', self.content)
        self.assertNotIn('card-danger', self.content)
        self.assertNotIn('card-primary', self.content)
        self.assertNotIn('card-outline', self.content)

    def test_payment_detail_removes_content_header(self):
        """Must NOT use AdminLTE content-header."""
        self.assertNotIn('content-header', self.content)

    # ── Context variables preserved ──

    def test_payment_detail_preserves_payment_vars(self):
        """All payment context variables must be preserved."""
        self.assertIn('payment.description', self.content)
        self.assertIn('payment.amount', self.content)
        self.assertIn('payment.transaction_id', self.content)
        self.assertIn('payment.first_name', self.content)
        self.assertIn('payment.last_name', self.content)
        self.assertIn('payment.email', self.content)
        self.assertIn('payment.identify', self.content)
        self.assertIn('payment.phone', self.content)
        self.assertIn('payment.state', self.content)
        self.assertIn('payment.refund', self.content)

    def test_payment_detail_preserves_refund_url(self):
        """Refund URL must be preserved."""
        self.assertIn("{% url 'payments:refund_request'", self.content)

    def test_payment_detail_preserves_empty_identify(self):
        """PAGADO/PENDIENTE status labels preserved."""
        self.assertIn('PAGADO', self.content)


# ── T3.6: Refund List + Form Templates ──

class RefundListTemplateTests(TestCase):
    """T3.6a: Verify payments/refund_list.html uses design-system."""

    @property
    def content(self):
        return _read_template('payments', 'payments/refund_list.html')

    def test_refund_list_has_table_modern(self):
        """Refund table must use .table-modern."""
        self.assertIn('table-modern', self.content,
                      'refund_list.html must contain table-modern class')

    def test_refund_list_has_badge_status(self):
        """Refund approval states must use .badge-status."""
        self.assertIn('badge-status', self.content,
                      'refund_list.html must use badge-status')

    def test_refund_list_removes_card_warning(self):
        """Must NOT use AdminLTE card-warning/card-outline."""
        self.assertNotIn('card-warning', self.content)
        self.assertNotIn('card-outline', self.content)

    def test_refund_list_removes_content_header(self):
        """Must NOT use AdminLTE content-header."""
        self.assertNotIn('content-header', self.content)

    def test_refund_list_preserves_refunds_loop(self):
        """refunds iteration must be preserved."""
        self.assertIn('{% for refund in refunds %}', self.content)
        self.assertIn('refund.created_at', self.content)
        self.assertIn('refund.amount', self.content)
        self.assertIn('refund.description', self.content)
        self.assertIn('refund.state', self.content)
        self.assertIn('refund.payment.first_name', self.content)
        self.assertIn('refund.ticket', self.content)

    def test_refund_list_preserves_empty_message(self):
        """Empty state message must be preserved."""
        self.assertIn('{% empty %}', self.content)
        self.assertIn('No tienes solicitudes', self.content)


class RefundFormTemplateTests(TestCase):
    """T3.6b: Verify payments/refund_form.html uses design-system."""

    @property
    def content(self):
        return _read_template('payments', 'payments/refund_form.html')

    def test_refund_form_has_card_modern(self):
        """Refund request card must use .card-modern."""
        self.assertIn('card-modern', self.content,
                      'refund_form.html must contain card-modern class')

    def test_refund_form_has_btn_primary_auth(self):
        """Submit button must use .btn-primary-auth."""
        self.assertIn('btn-primary-auth', self.content,
                      'refund_form.html submit must use btn-primary-auth')

    def test_refund_form_has_btn_secondary(self):
        """Cancel button must use .btn-secondary."""
        self.assertIn('btn-secondary', self.content,
                      'refund_form.html cancel must use btn-secondary')

    def test_refund_form_removes_card_danger(self):
        """Must NOT use AdminLTE card-danger."""
        self.assertNotIn('card-danger', self.content)

    def test_refund_form_removes_content_header(self):
        """Must NOT use AdminLTE content-header."""
        self.assertNotIn('content-header', self.content)

    def test_refund_form_preserves_csrf(self):
        """CSRF token must be preserved."""
        self.assertIn('{% csrf_token %}', self.content)

    def test_refund_form_preserves_payment_vars(self):
        """Payment context variables must be preserved."""
        self.assertIn('payment.first_name', self.content)
        self.assertIn('payment.last_name', self.content)
        self.assertIn('payment.amount', self.content)
        self.assertIn('payment.link.created_at', self.content)

    def test_refund_form_preserves_description_field(self):
        """Description textarea must be preserved."""
        self.assertIn('name="description"', self.content)

    def test_refund_form_preserves_url_tags(self):
        """URL references must be preserved."""
        self.assertIn("{% url 'payments:payment_history' %}", self.content)


# ── T3.7: Admin Refund List Template ──

class AdminRefundListTemplateTests(TestCase):
    """T3.7: Verify payments/admin/refund_list.html uses design-system."""

    @property
    def content(self):
        return _read_template('payments', 'payments/admin/refund_list.html')

    def test_admin_refund_list_has_table_modern(self):
        """Admin table must use .table-modern."""
        self.assertIn('table-modern', self.content,
                      'admin/refund_list.html must contain table-modern class')

    def test_admin_refund_list_has_btn_primary_auth(self):
        """Approve buttons must use .btn-primary-auth."""
        self.assertIn('btn-primary-auth', self.content,
                      'admin/refund_list.html approve buttons must use btn-primary-auth')

    def test_admin_refund_list_removes_card_warning(self):
        """Must NOT use AdminLTE card-warning/card-outline."""
        self.assertNotIn('card-warning', self.content)
        self.assertNotIn('card-outline', self.content)

    def test_admin_refund_list_removes_content_header(self):
        """Must NOT use AdminLTE content-header."""
        self.assertNotIn('content-header', self.content)

    def test_admin_refund_list_preserves_refunds_loop(self):
        """refunds iteration must be preserved."""
        self.assertIn('{% for refund in refunds %}', self.content)
        self.assertIn('refund.seller', self.content)
        self.assertIn('refund.amount', self.content)
        self.assertIn('refund.description', self.content)
        self.assertIn('refund.payment.transaction_id', self.content)

    def test_admin_refund_list_preserves_csrf(self):
        """CSRF tokens in approve forms must be preserved."""
        self.assertIn('{% csrf_token %}', self.content)

    def test_admin_refund_list_preserves_approve_url(self):
        """Admin approve URL must be preserved."""
        self.assertIn("{% url 'payments:admin_refund_approve'", self.content)

    def test_admin_refund_list_preserves_confirm_js(self):
        """Confirm dialog on approve must be preserved."""
        self.assertIn("confirm(", self.content)

    def test_admin_refund_list_preserves_empty_message(self):
        """Empty state message must be preserved."""
        self.assertIn('{% empty %}', self.content)
        self.assertIn('No hay reembolsos', self.content)


# ══════════════════════════════════════════════════════════════════════
# Phase 4: Buyer Experience Template Redesign (T4.1-T4.3)
# ══════════════════════════════════════════════════════════════════════


# ── T4.1: Checkout Template ──

class CheckoutTemplateTests(TestCase):
    """T4.1: Verify payments/checkout.html uses landing base + design-system."""

    @property
    def content(self):
        return _read_template('payments', 'payments/checkout.html')

    # ── Extends landing base ──

    def test_checkout_extends_landing_base(self):
        """Checkout must extend landing/layouts/base.html."""
        self.assertIn("{% extends 'landing/layouts/base.html' %}", self.content,
                      'checkout.html must extend landing base')

    def test_checkout_uses_content_block(self):
        """Checkout content must be in {% block content %}."""
        self.assertIn('{% block content %}', self.content,
                      'checkout.html must use content block')
        self.assertIn('{% endblock %}', self.content,
                      'checkout.html must close content block')

    # ── Standalone HTML removed ──

    def test_checkout_not_standalone_html(self):
        """Must NOT be a standalone HTML document."""
        self.assertNotIn('<!DOCTYPE html>', self.content,
                         'checkout.html must not be standalone HTML - extends base')

    # ── AdminLTE removed ──

    def test_checkout_removes_adminlte_cdn(self):
        """Must NOT load AdminLTE 3.2 from CDN."""
        self.assertNotIn('admin-lte', self.content.lower(),
                         'AdminLTE CDN links must be removed from checkout')
        self.assertNotIn('adminlte', self.content.lower(),
                         'AdminLTE references must be removed from checkout')

    # ── Design-system classes present ──

    def test_checkout_has_card_modern(self):
        """Payment summary card must use .card-modern."""
        self.assertIn('card-modern', self.content,
                      'checkout.html must contain card-modern class')

    def test_checkout_has_btn_primary_auth(self):
        """Submit button must use .btn-primary-auth."""
        self.assertIn('btn-primary-auth', self.content,
                      'checkout.html must use btn-primary-auth class')

    def test_checkout_has_input_modern(self):
        """Form fields must use .input-modern."""
        self.assertIn('input-modern', self.content,
                      'checkout.html must use input-modern for form fields')

    # ── Context variables preserved ──

    def test_checkout_preserves_link_context(self):
        """All link context variables must be preserved."""
        self.assertIn('link.description', self.content)
        self.assertIn('link.amount', self.content)
        self.assertIn('link.seller.user.get_full_name', self.content)

    def test_checkout_preserves_datafast_context(self):
        """Datafast context variables must be preserved."""
        self.assertIn('DATAFAST_BASE_URL', self.content)
        self.assertIn('checkout_id', self.content)
        self.assertIn('payment.id', self.content)

    # ── Form fields preserved ──

    def test_checkout_preserves_form_fields(self):
        """All buyer form fields must be preserved."""
        self.assertIn('name="first_name"', self.content)
        self.assertIn('name="last_name"', self.content)
        self.assertIn('name="email"', self.content)
        self.assertIn('name="identify"', self.content)
        self.assertIn('name="phone"', self.content)

    def test_checkout_preserves_csrf(self):
        """CSRF token must be preserved."""
        self.assertIn('{% csrf_token %}', self.content)

    # ── Step conditional logic preserved ──

    def test_checkout_preserves_step_conditional(self):
        """Step conditional logic must be preserved."""
        self.assertIn("{% if not step or step == 'info' %}", self.content)
        self.assertIn("{% elif step == 'payment' %}", self.content)

    # ── Datafast widget structure preserved ──

    def test_checkout_preserves_datafast_widget_options(self):
        """wpwlOptions script block must be preserved."""
        self.assertIn('wpwlOptions', self.content,
                      'Datafast wpwlOptions must be preserved')

    def test_checkout_preserves_datafast_widget_script(self):
        """Datafast paymentWidgets.js script must be preserved."""
        self.assertIn('paymentWidgets.js', self.content,
                      'Datafast paymentWidgets.js must be preserved')

    def test_checkout_preserves_datafast_validations(self):
        """Datafast additional validations script must be preserved."""
        self.assertIn('dfAdditionalValidations1.js', self.content,
                      'Datafast validations script must be preserved')

    # ── jQuery loaded ──

    def test_checkout_loads_jquery(self):
        """jQuery must be loaded for Datafast widget."""
        jquery_loaded = 'jquery' in self.content.lower()
        self.assertTrue(jquery_loaded,
                        'checkout.html must load jQuery for Datafast widget')

    # ── Landing aesthetic matching ──

    def test_checkout_uses_design_tokens(self):
        """Template must reference design-system tokens (navy/teal colors)."""
        content_lower = self.content.lower()
        uses_tokens = (
            'teal' in content_lower or
            'navy' in content_lower or
            'design-system' in content_lower
        )
        self.assertTrue(uses_tokens,
                        'checkout.html must use design-system color tokens')

    def test_checkout_has_amount_prominent(self):
        """Amount must be displayed in a prominent way."""
        self.assertIn('link.amount', self.content,
                      'Amount must be displayed prominently')


# ── T4.2: Payment Result Template ──

class PaymentResultTemplateTests(TestCase):
    """T4.2: Verify payments/payment_result.html uses landing base + design-system."""

    @property
    def content(self):
        return _read_template('payments', 'payments/payment_result.html')

    # ── Extends landing base ──

    def test_result_extends_landing_base(self):
        """Payment result must extend landing/layouts/base.html."""
        self.assertIn("{% extends 'landing/layouts/base.html' %}", self.content,
                      'payment_result.html must extend landing base')

    def test_result_uses_content_block(self):
        """Content must be in {% block content %}."""
        self.assertIn('{% block content %}', self.content)
        self.assertIn('{% endblock %}', self.content)

    # ── Standalone HTML removed ──

    def test_result_not_standalone_html(self):
        """Must NOT be a standalone HTML document."""
        self.assertNotIn('<!DOCTYPE html>', self.content,
                         'payment_result must not be standalone HTML')

    # ── AdminLTE removed ──

    def test_result_removes_adminlte_cdn(self):
        """Must NOT load AdminLTE 3.2 from CDN."""
        self.assertNotIn('admin-lte', self.content.lower(),
                         'AdminLTE CDN must be removed from payment_result')
        self.assertNotIn('adminlte', self.content.lower())

    # ── Design-system classes ──

    def test_result_has_card_modern(self):
        """Result container must use .card-modern."""
        self.assertIn('card-modern', self.content,
                      'payment_result.html must use card-modern class')

    # ── Success state ──

    def test_result_preserves_success_conditional(self):
        """Success conditional logic must be preserved."""
        self.assertIn('{% if success %}', self.content)

    def test_result_has_success_check_icon(self):
        """Must use check-circle icon for success."""
        self.assertIn('check-circle', self.content,
                      'Success state must use check-circle icon')

    def test_result_has_success_heading(self):
        """'¡Pago Exitoso!' heading must be preserved."""
        self.assertIn('Pago Exitoso', self.content)

    # ── Failure state ──

    def test_result_preserves_failure_conditional(self):
        """Failure conditional logic must be preserved (else or {% if not success %})."""
        self.assertTrue(
            '{% else %}' in self.content or '{% endif %}' in self.content,
            'Failure conditional must be preserved'
        )

    def test_result_has_error_icon(self):
        """Must use times-circle icon for failure."""
        self.assertIn('times-circle', self.content,
                      'Failure state must use times-circle icon')

    def test_result_has_failure_heading(self):
        """'Pago Fallido' heading must be preserved."""
        self.assertIn('Pago Fallido', self.content)

    # ── Context variables ──

    def test_result_preserves_payment_vars(self):
        """Payment context variables must be preserved."""
        self.assertIn('payment.description', self.content)
        self.assertIn('payment.amount', self.content)
        self.assertIn('payment.transaction_id', self.content)

    def test_result_preserves_error_msg(self):
        """error_msg context variable must be preserved."""
        self.assertIn('error_msg', self.content)

    # ── "Volver al inicio" button ──

    def test_result_has_btn_secondary(self):
        """Should have at least a secondary/home button."""
        self.assertIn('btn-secondary', self.content,
                      'payment_result should have btn-secondary style')


# ── T4.3: Link Inactive Template ──

class LinkInactiveTemplateTests(TestCase):
    """T4.3: Verify payments/link_inactive.html uses landing base with correct icons."""

    @property
    def content(self):
        return _read_template('payments', 'payments/link_inactive.html')

    # ── Extends landing base ──

    def test_inactive_extends_landing_base(self):
        """Must extend landing/layouts/base.html."""
        self.assertIn("{% extends 'landing/layouts/base.html' %}", self.content,
                      'link_inactive.html must extend landing base')

    # ── Design-system classes ──

    def test_inactive_has_card_modern(self):
        """Must use .card-modern for centered layout."""
        self.assertIn('card-modern', self.content,
                      'link_inactive.html must use card-modern class')

    # ── Icon classes compatible with FA5 (loaded by landing base) ──

    def test_inactive_has_fa_icon(self):
        """Must use font awesome icon classes."""
        has_fa_icon = 'fa-' in self.content
        self.assertTrue(has_fa_icon,
                        'link_inactive.html must use font awesome icons')

    # ── Context variables ──

    def test_inactive_preserves_link_context(self):
        """link.description context variable must be preserved."""
        self.assertIn('link.description', self.content)

    # ── URL references ──

    def test_inactive_preserves_home_url(self):
        """URL to landing index must be preserved."""
        self.assertIn("{% url 'landing:index' %}", self.content)

    # ── Message content ──

    def test_inactive_preserves_message(self):
        """The 'not available' message must be preserved."""
        self.assertIn('no está disponible', self.content)
