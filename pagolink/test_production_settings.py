"""Compiled profile tests: fake credentials, blocked sockets, no database I/O."""

import json
import os
import subprocess
import sys

from django.test import SimpleTestCase

FAKE_PRODUCTION = {
  'DJANGO_ENV': 'production',
  'DEBUG': 'False',
  'SECRET_KEY': 'fake-profile-only-' + 'abcdefghijk0123456789' * 4,
  'ALLOWED_HOSTS': 'app.example.com',
  'CSRF_TRUSTED_ORIGINS': 'https://app.example.com',
  'DATABASE_URL': 'postgresql://fake:p%40ss@db.example.com:5432/fake?sslmode=verify-full&sslrootcert=/fake/ca.pem',
  'EMAIL_BACKEND_MODE': 'smtp',
  'EMAIL_HOST': 'smtp.example.com',
  'EMAIL_HOST_USER': 'fake-user',
  'EMAIL_HOST_PASSWORD': 'fake-password',
  'EMAIL_PORT': '587',
  'EMAIL_USE_TLS': 'True',
  'DEFAULT_FROM_EMAIL': 'PagoLink <noreply@example.com>',
  'DATAFAST_BASE_URL': 'https://eu-prod.oppwa.com',
  'DATAFAST_ENTITY_ID': 'fake-entity',
  'DATAFAST_AUTH_TOKEN': 'fake-token',
  'DATAFAST_MID': 'fake-mid',
  'DATAFAST_TID': 'fake-tid',
  'SECURE_HSTS_SECONDS': '31536000',
  'SECURE_HSTS_INCLUDE_SUBDOMAINS': 'True',
  'SECURE_HSTS_PRELOAD': 'True',
}

SCRIPT = r"""
import json, socket
from unittest.mock import patch
with patch('socket.socket.connect', side_effect=RuntimeError('Network blocked')), patch('socket.socket.connect_ex', side_effect=RuntimeError('Network blocked')), patch('socket.create_connection', side_effect=RuntimeError('Network blocked')):
    import environ
    with patch.object(environ.Env, 'read_env') as env_reader:
        import django
        django.setup()
    from django.conf import settings
    from django.db import connections
    from django.core.checks import run_checks
    from django.http import HttpRequest
    connection = connections['default']
    request = HttpRequest()
    request.META['HTTP_X_FORWARDED_PROTO'] = 'https'
    print(json.dumps({
        'legacy_env_reads': env_reader.call_count,
        'engine': connection.settings_dict['ENGINE'],
        'password': connection.settings_dict.get('PASSWORD'),
        'options': connection.settings_dict.get('OPTIONS'),
        'connection_none': connection.connection is None,
        'backend': settings.EMAIL_BACKEND,
        'debug': settings.DEBUG,
        'secure_cookie': settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE,
        'httponly': settings.SESSION_COOKIE_HTTPONLY,
        'samesite': settings.SESSION_COOKIE_SAMESITE,
        'redirect': settings.SECURE_SSL_REDIRECT,
        'proxy_secure': request.is_secure(),
        'hsts_subdomains': settings.SECURE_HSTS_INCLUDE_SUBDOMAINS,
        'hsts_preload': settings.SECURE_HSTS_PRELOAD,
        'checks': [check.id for check in run_checks(include_deployment_checks=True)],
    }))
"""


def profile_result(overrides=None, remove=()):
  # Do not inherit private environment configuration or read the real .env.
  environment = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT') if key in os.environ}
  environment.update(FAKE_PRODUCTION)
  environment.update(overrides or {})
  for key in remove:
    environment.pop(key, None)
  environment['DJANGO_SETTINGS_MODULE'] = 'pagolink.settings'
  return subprocess.run(
    [sys.executable, '-B', '-c', SCRIPT], env=environment, capture_output=True, text=True, timeout=30, check=False
  )


class ProductionSettingsTests(SimpleTestCase):
  def assert_valid(self, overrides=None, remove=()):
    result = profile_result(overrides, remove)
    self.assertEqual(result.returncode, 0, result.stderr)
    return json.loads(result.stdout)

  def test_real_postgres_backend_compiles_without_connecting(self):
    result = self.assert_valid()
    self.assertEqual(result['engine'], 'django.db.backends.postgresql')
    self.assertEqual(result['password'], 'p@ss')
    self.assertEqual(result['options']['sslmode'], 'verify-full')
    self.assertTrue(result['connection_none'])
    self.assertFalse(result['debug'])
    self.assertTrue(result['secure_cookie'])
    self.assertTrue(result['httponly'])
    self.assertEqual(result['samesite'], 'Lax')
    self.assertTrue(result['redirect'])
    self.assertFalse(result['proxy_secure'])
    self.assertTrue(result['hsts_subdomains'])
    self.assertTrue(result['hsts_preload'])
    self.assertEqual(result['checks'], [])

  def test_alternate_profiles_and_explicit_proxy(self):
    for overrides in (
      {'DJANGO_ENV': 'staging'},
      {'TRUST_CONTROLLED_PROXY': 'True'},
      {'EMAIL_BACKEND_MODE': 'resend', 'RESEND_API_KEY': 'fake-key'},
      {'EMAIL_USE_TLS': 'False', 'EMAIL_USE_SSL': 'True', 'EMAIL_PORT': '465'},
      {'DATABASE_URL': 'postgres://fake:fake@db.example.com/fake?sslmode=require'},
      {'DATABASE_URL': 'postgresql://fake:fake@db.example.com/fake?sslmode=verify-ca&sslrootcert=/fake/ca.pem'},
    ):
      with self.subTest(overrides=overrides):
        result = self.assert_valid(overrides)
        self.assertTrue(result['connection_none'])
        self.assertEqual(result['proxy_secure'], overrides.get('TRUST_CONTROLLED_PROXY') == 'True')

  def test_progressive_hsts_defaults_are_not_irreversible(self):
    result = self.assert_valid(remove=('SECURE_HSTS_SECONDS', 'SECURE_HSTS_INCLUDE_SUBDOMAINS', 'SECURE_HSTS_PRELOAD'))
    self.assertFalse(result['hsts_subdomains'])
    self.assertFalse(result['hsts_preload'])
    self.assertEqual(set(result['checks']), {'security.W004'})

  def test_development_sqlite_and_console(self):
    result = self.assert_valid(
      {
        'DJANGO_ENV': 'development',
        'DEBUG': 'True',
        'EMAIL_BACKEND_MODE': 'console',
        'DATAFAST_TEST_MODE': 'EXTERNAL',
        'DATAFAST_BASE_URL': 'https://eu-test.oppwa.com',
      }
    )
    self.assertEqual(result['engine'], 'django.db.backends.sqlite3')
    self.assertIn('console', result['backend'])

  def test_legacy_env_bootstrap_without_reading_private_file(self):
    result = self.assert_valid({'DEBUG': 'True', 'EMAIL_BACKEND_MODE': 'console'}, remove=('DJANGO_ENV',))
    self.assertEqual(result['legacy_env_reads'], 1)
    self.assertEqual(result['engine'], 'django.db.backends.sqlite3')

  def test_invalid_profiles_fail_closed_without_echoing_values(self):
    bad_values = {
      'DJANGO_ENV': ['prod', ''],
      'DEBUG': ['True', 'perhaps'],
      'SECRET_KEY': ['short-private-value', 'django-insecure-' + 'x' * 70, 'x' * 70],
      'ALLOWED_HOSTS': ['', '*', '.example.com', 'https://app.example.com'],
      'CSRF_TRUSTED_ORIGINS': ['', 'http://app.example.com', 'https://*.example.com'],
      'DATABASE_URL': [
        '',
        'sqlite:///private-db',
        'postgres://u:p@db/fake',
        'postgres://u:p@db/fake?sslmode=disable',
        'postgres://u:p@db/fake?sslmode=require&sslmode=disable',
        'postgres://u:p@db:bad/fake?sslmode=require',
        'postgres://u:p@db/fake?sslmode=require&options=private-value',
        'postgres://u:p@db/fake?sslmode=verify-full',
        'postgres://u:p%ZZ@db/fake?sslmode=require',
        'postgres://u:p%00@db/fake?sslmode=require',
      ],
      'EMAIL_BACKEND_MODE': ['', 'console', 'unknown'],
      'EMAIL_USE_SSL': ['True'],
      'EMAIL_USE_TLS': ['False', 'perhaps'],
      'EMAIL_PORT': ['bad', '0'],
      'DEFAULT_FROM_EMAIL': ['', 'invalid'],
      'DATAFAST_BASE_URL': [
        'http://eu-prod.oppwa.com',
        'https://evil.example',
        'https://u:p@eu-prod.oppwa.com',
        'https://eu-prod.oppwa.com/v1/',
        'https://eu-prod.oppwa.com?redirect=x',
        'https://eu-test.oppwa.com',
        'https://eu-prod.oppwa.com:444',
      ],
      'DATAFAST_TEST_MODE': ['EXTERNAL', 'INTERNAL'],
      'TRUST_CONTROLLED_PROXY': ['perhaps'],
      'SECURE_HSTS_SECONDS': ['-1', 'bad'],
    }
    for key, values in bad_values.items():
      for value in values:
        with self.subTest(key=key, value=value):
          result = profile_result({key: value})
          self.assertNotEqual(result.returncode, 0)
          self.assertIn('ImproperlyConfigured', result.stderr)
          if value and len(value) > 12:
            self.assertNotIn(value, result.stderr)

  def test_required_credentials_and_explicit_email(self):
    for key in (
      'SECRET_KEY',
      'DATABASE_URL',
      'ALLOWED_HOSTS',
      'CSRF_TRUSTED_ORIGINS',
      'EMAIL_BACKEND_MODE',
      'EMAIL_HOST',
      'EMAIL_HOST_USER',
      'EMAIL_HOST_PASSWORD',
      'DEFAULT_FROM_EMAIL',
      'DATAFAST_ENTITY_ID',
      'DATAFAST_AUTH_TOKEN',
      'DATAFAST_MID',
      'DATAFAST_TID',
      'DATAFAST_BASE_URL',
    ):
      with self.subTest(key=key):
        result = profile_result(remove=(key,))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ImproperlyConfigured', result.stderr)
    result = profile_result({'EMAIL_BACKEND_MODE': 'resend'})
    self.assertNotEqual(result.returncode, 0)
    self.assertIn('ImproperlyConfigured', result.stderr)
