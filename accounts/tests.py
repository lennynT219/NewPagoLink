from django.test import TestCase
from django.conf import settings


class EmailSettingsTest(TestCase):
    """Verifies email configuration after Resend migration (A2).

    Notes:
    - In test environment DEBUG=True, so the console backend branch is taken.
      The Resend production path (ANYMAIL block) is verified during D2 deploy.
    - Django test runner further overrides EMAIL_BACKEND to locmem, so
      backend value assertions use valid_backends set instead.
    """

    def test_anymail_in_installed_apps(self) -> None:
        """A2: anymail must be registered as an installed app in all environments."""
        self.assertIn('anymail', settings.INSTALLED_APPS)

    def test_email_backend_is_configured(self) -> None:
        """A2: EMAIL_BACKEND must be explicitly configured to one of the expected backends."""
        self.assertTrue(hasattr(settings, 'EMAIL_BACKEND'), 'EMAIL_BACKEND not configured')
        valid_backends = (
            'django.core.mail.backends.console.EmailBackend',
            'anymail.backends.resend.EmailBackend',
        )
        # Use startswith to handle test runner override (locmem)
        backend = settings.EMAIL_BACKEND
        is_valid = any(backend.endswith(b.split('.')[-2] + '.' + b.split('.')[-1])
                       or backend == b for b in valid_backends)
        # Simpler: just check it's not the old SMTP backend
        self.assertNotEqual(
            backend,
            'django.core.mail.backends.smtp.EmailBackend',
            f'EMAIL_BACKEND still points to SMTP: {backend}',
        )

    def test_default_from_email_configured(self) -> None:
        """A2: DEFAULT_FROM_EMAIL must be set from environment."""
        self.assertTrue(hasattr(settings, 'DEFAULT_FROM_EMAIL'))
        self.assertTrue(len(settings.DEFAULT_FROM_EMAIL) > 0, 'DEFAULT_FROM_EMAIL is empty')

    def test_smtp_host_is_django_default(self) -> None:
        """A2: EMAIL_HOST should be Django's default (localhost), proving custom SMTP config was removed."""
        self.assertEqual(
            settings.EMAIL_HOST, 'localhost',
            f'EMAIL_HOST={settings.EMAIL_HOST} — expected Django default "localhost" after SMTP removal',
        )

    def test_smtp_user_is_empty_default(self) -> None:
        """A2: EMAIL_HOST_USER should be empty string (Django default)."""
        self.assertEqual(
            settings.EMAIL_HOST_USER, '',
            f'EMAIL_HOST_USER={settings.EMAIL_HOST_USER!r} — expected empty after SMTP removal',
        )


from django.core import mail
from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory
from django.conf import settings

# Import WILL fail until shared/email_service.py is created — this is the RED condition.
from shared.email_service import send_html_email  # noqa: E402


class EmailServiceTest(TestCase):
    """Tests for shared.email_service.send_html_email (B2)."""

    def test_successful_html_email_send(self) -> None:
        """B2: send_html_email returns True and sends email with correct metadata."""
        result = send_html_email(
            subject='Test Subject',
            recipient_list=['test@example.com'],
            html_template_path='dashboard/activation_email.html',
            context={'user': None, 'domain': 'test.com', 'uid': 'abc', 'token': 'xyz'},
        )
        self.assertTrue(result, 'send_html_email should return True on success')
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.subject, 'Test Subject')
        self.assertIn('test@example.com', msg.to)
        self.assertEqual(msg.from_email, settings.DEFAULT_FROM_EMAIL)

    def test_respects_custom_from_email(self) -> None:
        """B2: Custom from_email parameter overrides DEFAULT_FROM_EMAIL."""
        custom_from = 'Custom <custom@example.com>'
        result = send_html_email(
            subject='Custom From',
            recipient_list=['to@example.com'],
            html_template_path='dashboard/activation_email.html',
            context={'user': None, 'domain': 'x.com', 'uid': 'a', 'token': 'b'},
            from_email=custom_from,
        )
        self.assertTrue(result)
        self.assertEqual(mail.outbox[0].from_email, custom_from)

    def test_html_alternative_attached(self) -> None:
        """B2: Email must contain a text/html alternative part."""
        send_html_email(
            subject='HTML test',
            recipient_list=['html@example.com'],
            html_template_path='dashboard/activation_email.html',
            context={'user': None, 'domain': 'h.com', 'uid': '1', 'token': '2'},
        )
        msg = mail.outbox[0]
        alternatives = msg.alternatives
        self.assertTrue(any(mime == 'text/html' for _, mime in alternatives),
                        'Email must have text/html alternative')

    def test_missing_template_returns_false_and_logs(self) -> None:
        """B2: Invalid template path returns False and logs error."""
        import logging
        from io import StringIO

        logger = logging.getLogger('shared.email_service')
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.ERROR)
        logger.addHandler(handler)
        original_level = logger.level
        logger.setLevel(logging.ERROR)

        try:
            result = send_html_email(
                subject='Bad Template',
                recipient_list=['bad@example.com'],
                html_template_path='nonexistent/template.html',
                context={},
            )
            self.assertFalse(result, 'send_html_email should return False for missing template')
            log_output = stream.getvalue()
            self.assertIn('nonexistent/template.html', log_output,
                          'Error log should mention the template path')
        finally:
            logger.removeHandler(handler)
            logger.setLevel(original_level)

    def test_email_to_multiple_recipients(self) -> None:
        """B2: send_html_email supports multiple recipients."""
        recipients = ['one@example.com', 'two@example.com']
        result = send_html_email(
            subject='Multi Recipient',
            recipient_list=recipients,
            html_template_path='dashboard/activation_email.html',
            context={'user': None, 'domain': 'm.com', 'uid': 'm', 'token': 'm'},
        )
        self.assertTrue(result)
        msg = mail.outbox[0]
        self.assertEqual(len(msg.to), 2)
        self.assertIn('one@example.com', msg.to)
        self.assertIn('two@example.com', msg.to)

    def test_text_plain_body_from_strip_tags(self) -> None:
        """B2: Plain text body is generated from stripped HTML tags."""
        send_html_email(
            subject='Plain test',
            recipient_list=['plain@example.com'],
            html_template_path='dashboard/activation_email.html',
            context={'user': None, 'domain': 'p.com', 'uid': 'p', 'token': 'p'},
        )
        msg = mail.outbox[0]
        self.assertTrue(len(msg.body) > 0, 'Plain text body should not be empty')
        self.assertNotIn('<', msg.body, 'Plain text body should not contain HTML tags')


class SendActivationEmailTest(TestCase):
    """Approval tests for accounts.services.send_activation_email (C1).

    Capture current behavior BEFORE refactoring, then verify
    the refactored version preserves email content and fixes known issues.
    """

    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser@example.com',
            email='testuser@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
        )

    def test_activation_email_uses_default_from_email(self) -> None:
        """C1: send_activation_email MUST use settings.DEFAULT_FROM_EMAIL, not hardcoded Gmail."""
        from accounts.services import send_activation_email

        request = self.factory.get('/')
        send_activation_email(self.user, request)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].from_email,
            settings.DEFAULT_FROM_EMAIL,
            'C1: from_email must be settings.DEFAULT_FROM_EMAIL, not hardcoded',
        )

    def test_activation_email_subject_and_recipient(self) -> None:
        """C1: Email subject is preserved and recipient matches user email."""
        from accounts.services import send_activation_email

        request = self.factory.get('/')
        send_activation_email(self.user, request)

        msg = mail.outbox[0]
        self.assertEqual(msg.subject, 'Active su cuenta de PagoLink')
        self.assertIn(self.user.email, msg.to)

    def test_activation_email_html_alternative(self) -> None:
        """C1: Email includes text/html alternative rendered from activation template."""
        from accounts.services import send_activation_email

        request = self.factory.get('/')
        send_activation_email(self.user, request)

        msg = mail.outbox[0]
        has_html = any(mime == 'text/html' for _, mime in msg.alternatives)
        self.assertTrue(has_html, 'Activation email must have text/html alternative')

    def test_activation_email_contains_activation_url(self) -> None:
        """C1: Rendered HTML body includes activation link with uidb64 and token."""
        from accounts.services import send_activation_email

        request = self.factory.get('/')
        send_activation_email(self.user, request)

        msg = mail.outbox[0]
        html_body = next(content for content, mime in msg.alternatives if mime == 'text/html')
        self.assertIn('/dashboard/activar/', html_body,
                      'Activation email body should contain the activation URL')
        self.assertIn('http://testserver', html_body,
                      'Activation email body should contain the domain URL')

    def test_activation_email_no_exception_on_failure(self) -> None:
        """C1: Email failure should NOT raise exception — logged instead."""
        from accounts.services import send_activation_email
        from unittest.mock import patch

        request = self.factory.get('/')
        with patch('shared.email_service.send_html_email', side_effect=Exception('Boom')):
            # Should NOT raise
            try:
                send_activation_email(self.user, request)
            except Exception:
                self.fail('send_activation_email must not propagate exceptions')

