"""Sender-domain regressions with synthetic configuration and no mail I/O."""

import os
import unittest
from unittest.mock import patch

from pagolink.production import email_settings


class EmailSenderDomainTests(unittest.TestCase):
  def environment(self, mode):
    return {
      'EMAIL_BACKEND_MODE': mode,
      'RESEND_API_KEY': 'fake-resend-key',
      'EMAIL_HOST': 'smtp.example.com',
      'EMAIL_HOST_USER': 'fake-user',
      'EMAIL_HOST_PASSWORD': 'fake-password',
    }

  def test_development_default_sender_uses_current_domain(self):
    for mode in ('console', 'smtp', 'resend'):
      with self.subTest(mode=mode), patch.dict(os.environ, self.environment(mode), clear=True):
        result = email_settings(strict=False, debug=True)
        self.assertEqual(result['DEFAULT_FROM_EMAIL'], 'PagoLink <noreply@pagolinks.com>')
        self.assertEqual(result['EMAIL_BACKEND_MODE'], mode)

  def test_explicit_sender_is_preserved_in_each_supported_profile(self):
    sender = 'Billing <billing@example.com>'
    for strict, mode in (
      (False, 'console'), (False, 'smtp'), (False, 'resend'),
      (True, 'smtp'), (True, 'resend'),
    ):
      env = {**self.environment(mode), 'DEFAULT_FROM_EMAIL': sender}
      with self.subTest(strict=strict, mode=mode), patch.dict(os.environ, env, clear=True):
        result = email_settings(strict=strict, debug=not strict)
        self.assertEqual(result['DEFAULT_FROM_EMAIL'], sender)
        self.assertEqual(result['EMAIL_BACKEND_MODE'], mode)
