"""Compiled profile tests: fake credentials, blocked sockets, no database I/O."""

import json
import os
import subprocess
import sys
import unittest

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
  'DATAFAST_ECI': 'fixture-eci',
  'DATAFAST_PSERV': 'fixture-pserv',
  'DATAFAST_MERCHANT_NAME': 'FixtureMerchant',
  'DATAFAST_CART_PRICE_BASIS': 'gross',
  'SECURE_HSTS_SECONDS': '31536000',
  'SECURE_HSTS_INCLUDE_SUBDOMAINS': 'True',
  'SECURE_HSTS_PRELOAD': 'True',
}

FAKE_DEVELOPMENT = {
  'DJANGO_ENV': 'development',
  'DEBUG': 'True',
  'EMAIL_BACKEND_MODE': 'console',
  'DATAFAST_BASE_URL': 'https://eu-test.oppwa.com',
  'DATAFAST_TEST_MODE': 'EXTERNAL',
}

SCRIPT = r"""
import builtins, io, json, os, socket, sys
from types import ModuleType, SimpleNamespace
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch

# Audit before importing settings or drivers. Only public Python/package code
# may be read; no writes, dotenv, backups, database files or arbitrary data.
root = Path.cwd().resolve()
public_roots = (root, Path(sys.base_prefix).resolve())
counters = {'private_reads': 0, 'network': 0, 'database': 0, 'app_setup': 0}

def audit(event, args):
    if event == 'open':
        path, mode, flags = args
        allowed = False
        if isinstance(path, (str, bytes, os.PathLike)):
            candidate = Path(os.fsdecode(path)).resolve()
            allowed = (
                any(candidate.is_relative_to(base) for base in public_roots)
                and candidate.suffix in ('.py', '.pyc', '.so')
                and not any(part.startswith('.env') or part in ('.pi', '.codegraph', 'odd') for part in candidate.parts)
                and not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
            )
        if not allowed:
            counters['private_reads'] += 1
            # Only reveal paths proven inside public installed packages.
            detail = str(candidate) if isinstance(path, str) and candidate.is_relative_to(root / '.venv/lib') else 'redacted'
            raise RuntimeError('Private/data access blocked: ' + detail)
    elif event == 'import' and args[0].startswith(('psycopg', 'sqlite3', '_sqlite3', 'django.db.backends.')):
        counters['database'] += 1
        raise RuntimeError('Database driver/backend import blocked')
    elif event.startswith('socket.') and event != 'socket.__new__':
        counters['network'] += 1
        raise RuntimeError('Network blocked')
    elif event.startswith('sqlite3.connect'):
        counters['database'] += 1
        raise RuntimeError('Database blocked')
sys.addaudithook(audit)

import django, environ
from django.conf import Settings

def deny(kind):
    def blocked(*args, **kwargs):
        counters[kind] += 1
        raise RuntimeError('External operation blocked')
    return blocked

# Settings-only compilation needs no real drivers. Fake modules expose only
# blocked entry points, never connection success; their imports cannot inspect
# machine configuration or load native database libraries.
psycopg = ModuleType('psycopg')
psycopg.connect = deny('database')
psycopg.Connection = SimpleNamespace(connect=deny('database'))
psycopg.AsyncConnection = SimpleNamespace(connect=deny('database'))
sqlite3 = ModuleType('sqlite3')
sqlite3.connect = deny('database')
sqlite3.dbapi2 = SimpleNamespace(connect=deny('database'))
sys.modules.update(psycopg=psycopg, sqlite3=sqlite3)

with ExitStack() as stack:
    for target, kind in (
        ('socket.socket.connect', 'network'),
        ('socket.socket.connect_ex', 'network'),
        ('socket.create_connection', 'network'),
        ('socket.getaddrinfo', 'network'),
        ('socket.gethostbyname', 'network'),
        ('socket.gethostbyname_ex', 'network'),
        ('psycopg.connect', 'database'),
        ('psycopg.Connection.connect', 'database'),
        ('psycopg.AsyncConnection.connect', 'database'),
        ('sqlite3.connect', 'database'),
        ('sqlite3.dbapi2.connect', 'database'),
        ('django.setup', 'app_setup'),
    ):
        stack.enter_context(patch(target, side_effect=deny(kind)))
    import_guards = dict(counters)
    for key in counters:
        counters[key] = 0
    # Fake sentinel probes fail before filesystem/network/driver access.
    for probe in (
        lambda: builtins.open(root / '.env.guard-sentinel'),
        lambda: io.open(root / '.env.guard-sentinel.bak'),
        lambda: os.open(root / 'fake-guard.sqlite3', os.O_RDONLY),
        lambda: socket.getaddrinfo('guard.invalid', 5432),
        lambda: socket.create_connection(('guard.invalid', 5432)),
        lambda: psycopg.connect(''),
        lambda: sqlite3.connect(':memory:'),
        lambda: django.setup(),
    ):
        try:
            probe()
        except RuntimeError:
            pass
        else:
            raise AssertionError('Guard did not block sentinel')
    probes = dict(counters)
    for key in counters:
        counters[key] = 0
    original_environment = dict(os.environ)
    with patch.object(environ.Env, 'read_env') as env_reader:
        try:
            settings = Settings('pagolink.settings')
        except Exception:
            print(json.dumps({'guards': counters, 'import_guards': import_guards, 'guard_probes': probes,
                              'environment_unchanged': dict(os.environ) == original_environment}))
            raise
    database = settings.DATABASES['default']
    print(json.dumps({
        'environment_unchanged': dict(os.environ) == original_environment,
        'legacy_env_reads': env_reader.call_count,
        'engine': database['ENGINE'],
        'name': str(database['NAME']),
        'host': database.get('HOST'),
        'port': database.get('PORT'),
        'user': database.get('USER'),
        'password': database.get('PASSWORD'),
        'options': database.get('OPTIONS'),
        'guards': counters,
        'import_guards': import_guards,
        'guard_probes': probes,
        'checkout_metadata': [settings.DATAFAST_ECI, settings.DATAFAST_PSERV, settings.DATAFAST_MERCHANT_NAME, settings.DATAFAST_CART_PRICE_BASIS],
        'environment': getattr(settings, 'DATAFAST_ENVIRONMENT', None),
        'base': settings.DATAFAST_BASE_URL,
        'entity': settings.DATAFAST_ENTITY_ID,
        'test_mode': settings.DATAFAST_TEST_MODE,
        'backend': settings.EMAIL_BACKEND,
        'debug': settings.DEBUG,
        'secure_cookie': settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE,
        'httponly': settings.SESSION_COOKIE_HTTPONLY,
        'samesite': settings.SESSION_COOKIE_SAMESITE,
        'redirect': settings.SECURE_SSL_REDIRECT,
        'proxy_configured': settings.SECURE_PROXY_SSL_HEADER == ('HTTP_X_FORWARDED_PROTO', 'https'),
        'hsts_seconds': settings.SECURE_HSTS_SECONDS,
        'hsts_subdomains': settings.SECURE_HSTS_INCLUDE_SUBDOMAINS,
        'hsts_preload': settings.SECURE_HSTS_PRELOAD,
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
  # Django Settings copies TIME_ZONE into TZ; preseed that existing UTC value
  # so the snapshot detects parser mutations, not framework timezone setup.
  environment['TZ'] = 'UTC'
  return subprocess.run(
    [sys.executable, '-B', '-c', SCRIPT], env=environment, capture_output=True, text=True, timeout=30, check=False
  )


class ProductionSettingsTests(unittest.TestCase):
  def assert_guards(self, compiled):
    self.assertEqual(compiled['guards'], {'private_reads': 0, 'network': 0, 'database': 0, 'app_setup': 0})
    self.assertEqual(compiled['import_guards'], {'private_reads': 0, 'network': 0, 'database': 0, 'app_setup': 0})
    self.assertEqual(compiled['guard_probes'], {'private_reads': 3, 'network': 2, 'database': 2, 'app_setup': 1})
    self.assertTrue(compiled['environment_unchanged'])

  def assert_valid(self, overrides=None, remove=()):
    result = profile_result(overrides, remove)
    self.assertEqual(result.returncode, 0, result.stderr)
    compiled = json.loads(result.stdout)
    self.assert_guards(compiled)
    return compiled

  def test_real_postgres_backend_compiles_without_connecting(self):
    result = self.assert_valid()
    self.assertEqual(result['engine'], 'django.db.backends.postgresql')
    self.assertEqual(result['password'], 'p@ss')
    self.assertEqual(result['options']['sslmode'], 'verify-full')
    self.assertFalse(result['debug'])
    self.assertTrue(result['secure_cookie'])
    self.assertTrue(result['httponly'])
    self.assertEqual(result['samesite'], 'Lax')
    self.assertTrue(result['redirect'])
    self.assertFalse(result['proxy_configured'])
    self.assertTrue(result['hsts_subdomains'])
    self.assertTrue(result['hsts_preload'])

  @unittest.skip(
    'Runtime deployment checks require prohibited django.setup/app registry; pending independent verification'
  )
  def test_runtime_deployment_checks(self):
    # Preserve the runtime expectations explicitly, never report invented results.
    from django.core.checks import run_checks

    self.assertEqual(run_checks(include_deployment_checks=True), [])

  @unittest.skip('HttpRequest proxy behavior requires global Django settings; pending independent runtime verification')
  def test_runtime_proxy_request(self):
    from django.http import HttpRequest

    request = HttpRequest()
    request.META['HTTP_X_FORWARDED_PROTO'] = 'https'
    self.assertFalse(request.is_secure())

  def test_alternate_profiles_and_explicit_proxy(self):
    for overrides in (
      {'DJANGO_ENV': 'staging'},
      {'DATAFAST_CART_PRICE_BASIS': 'net'},
      {'TRUST_CONTROLLED_PROXY': 'True'},
      {'EMAIL_BACKEND_MODE': 'resend', 'RESEND_API_KEY': 'fake-key'},
      {'EMAIL_USE_TLS': 'False', 'EMAIL_USE_SSL': 'True', 'EMAIL_PORT': '465'},
      {'DATABASE_URL': 'postgres://fake:fake@db.example.com/fake?sslmode=require'},
      {'DATABASE_URL': 'postgresql://fake:fake@db.example.com/fake?sslmode=verify-ca&sslrootcert=/fake/ca.pem'},
    ):
      with self.subTest(overrides=overrides):
        result = self.assert_valid(overrides)
        self.assertEqual(result['proxy_configured'], overrides.get('TRUST_CONTROLLED_PROXY') == 'True')

  def test_progressive_hsts_defaults_are_not_irreversible(self):
    result = self.assert_valid(remove=('SECURE_HSTS_SECONDS', 'SECURE_HSTS_INCLUDE_SUBDOMAINS', 'SECURE_HSTS_PRELOAD'))
    self.assertFalse(result['hsts_subdomains'])
    self.assertFalse(result['hsts_preload'])
    self.assertEqual(result['hsts_seconds'], 0)

  @unittest.skip(
    'Progressive HSTS deployment warning requires prohibited app registry setup; pending runtime verification'
  )
  def test_runtime_progressive_hsts_warning(self):
    from django.core.checks import run_checks

    self.assertEqual({check.id for check in run_checks(include_deployment_checks=True)}, {'security.W004'})

  def test_development_database_defaults(self):
    for url in (None, ''):
      with self.subTest(url=url):
        overrides = dict(FAKE_DEVELOPMENT)
        if url is not None:
          overrides['DATABASE_URL'] = url
        result = self.assert_valid(overrides, remove=('DATABASE_URL',) if url is None else ())
        self.assertEqual(result['engine'], 'django.db.backends.sqlite3')
        self.assertTrue(result['name'].endswith('/db.sqlite3'))

  def test_development_loopback_postgres(self):
    for host, address in (
      ('localhost', '127.0.0.1'),
      ('127.0.0.1', '127.0.0.1'),
      ('127.0.0.2', '127.0.0.2'),
      ('[::1]', '::1'),
    ):
      for tls in (
        '',
        '?sslmode=disable',
        '?sslmode=require',
        '?sslmode=verify-ca&sslrootcert=/fake/ca.pem',
        '?sslmode=verify-full&sslrootcert=/fake/ca.pem',
      ):
        with self.subTest(host=host, tls=tls):
          result = self.assert_valid(
            dict(
              FAKE_DEVELOPMENT,
              DATABASE_URL=f'postgresql://pagolink:p%40ss@{host}:5433/pagolink{tls}',
            )
          )
          self.assertEqual(result['engine'], 'django.db.backends.postgresql')
          self.assertEqual(result['name'], 'pagolink')
          self.assertEqual(result['user'], 'pagolink')
          self.assertEqual(result['password'], 'p@ss')
          self.assertEqual(result['port'], 5433)
          self.assertEqual(result['host'], host.strip('[]'))
          self.assertEqual(result['options']['hostaddr'], address)
          self.assertEqual(result['options']['sslmode'], 'disable' if not tls else tls.split('=')[1].split('&')[0])
          self.assertEqual(result['environment'], 'phase2')
          self.assertEqual(result['entity'], 'fake-entity')
          self.assertEqual(result['base'], 'https://eu-test.oppwa.com')
          self.assertEqual(result['test_mode'], 'EXTERNAL')

  def test_local_postgres_does_not_select_payment_credentials(self):
    result = self.assert_valid(
      dict(
        FAKE_DEVELOPMENT,
        DATABASE_URL='postgres://fake%40user:p%3Ass@localhost/fake%20db',
        DATAFAST_ENVIRONMENT='phase1',
        DATAFAST_BASE_URL='https://test.oppwa.com/v1/',
        DATAFAST_TEST_MODE='',
        DATAFAST_PHASE1_ENTITY_ID='fake-phase1',
        DATAFAST_PHASE1_AUTH_TOKEN='fake-phase1-token',
      ),
      remove=('DATAFAST_ENTITY_ID', 'DATAFAST_AUTH_TOKEN', 'DATAFAST_MID', 'DATAFAST_TID'),
    )
    self.assertEqual(result['engine'], 'django.db.backends.postgresql')
    self.assertEqual(result['port'], 5432)
    self.assertEqual(result['user'], 'fake@user')
    self.assertEqual(result['password'], 'p:ss')
    self.assertEqual(result['name'], 'fake db')
    self.assertEqual(result['environment'], 'phase1')
    self.assertEqual(result['entity'], 'fake-phase1')
    self.assertEqual(result['base'], 'https://test.oppwa.com/v1/')
    self.assertEqual(result['test_mode'], '')

  def test_development_invalid_database_never_falls_back(self):
    urls = [
      ' ',
      'sqlite:///private-db',
      'postgresql://u:p@db.example.com/db',
      'postgresql://u:p@localhost.evil/db',
      'postgresql://u:p@192.168.1.2/db',
      'postgresql://u:private-fake-password@remote.example/db',
      'postgresql://u:p@[::]/db',
      'postgresql://u:p@[::1%25fake]/db',
      'postgresql://u:p@localhost,127.0.0.1/db',
      'postgresql://u:p@%2Ftmp/db',
      'postgresql:///db',
      'postgresql://u@localhost/db',
      'postgresql://u:p@localhost:bad/db',
      'postgresql://u:p@localhost:0/db',
      'postgresql://u:p@localhost/db/extra',
      'postgresql://u:p%ZZ@localhost/db',
      'postgresql://u:p%00@localhost/db',
      'postgresql://u:p@localhost/db#fragment',
      'postgresql://u:p@localhost/db?sslmode=allow',
      'postgresql://u:p@localhost/db?sslmode=verify-full',
      'postgresql://u:p@localhost/db?sslmode=require&sslrootcert=',
      'postgresql://u:p@localhost/db?%68ost=remote',
      'postgresql://u:p@localhost/db?sslmode=disable&sslmode=require',
    ]
    for option in ('host=remote', 'hostaddr=192.168.1.2', 'service=fake', 'options=fake', 'port=5434'):
      urls.append('postgresql://u:p@localhost/db?' + option)
    for url in urls:
      with self.subTest(url=url):
        result = profile_result(dict(FAKE_DEVELOPMENT, DATABASE_URL=url))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Invalid or missing DATABASE_URL configuration', result.stderr)
        if url.strip():
          self.assertNotIn(url, result.stderr)
        self.assertNotIn('private-fake-password', result.stderr)
        self.assert_guards(json.loads(result.stdout))

  def test_development_inherited_libpq_destination_rejected(self):
    for key in (
      'PGHOST',
      'PGHOSTADDR',
      'PGPORT',
      'PGDATABASE',
      'PGUSER',
      'PGPASSWORD',
      'PGSERVICE',
      'PGSERVICEFILE',
      'PGSYSCONFDIR',
      'PGOPTIONS',
      'PGPASSFILE',
    ):
      with self.subTest(key=key):
        result = profile_result(
          dict(
            FAKE_DEVELOPMENT,
            DATABASE_URL='postgresql://u:p@localhost/db',
            **{key: 'fake-private-override'},
          )
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Invalid or missing DATABASE_URL configuration', result.stderr)
        self.assertNotIn('fake-private-override', result.stderr)
        self.assert_guards(json.loads(result.stdout))

  def test_strict_loopback_still_requires_tls(self):
    for profile in ('staging', 'production'):
      for tls in ('', '?sslmode=disable'):
        with self.subTest(profile=profile, tls=tls):
          result = profile_result({'DJANGO_ENV': profile, 'DATABASE_URL': 'postgresql://u:p@localhost/db' + tls})
          self.assertNotEqual(result.returncode, 0)
          self.assertIn('DATABASE_URL', result.stderr)
      result = self.assert_valid(
        {'DJANGO_ENV': profile, 'DATABASE_URL': 'postgresql://u:p@localhost/db?sslmode=require'}
      )
      self.assertEqual(result['options'], {'sslmode': 'require'})

  def test_development_sqlite_and_console(self):
    result = self.assert_valid(
      {
        'DATABASE_URL': '',
        'DJANGO_ENV': 'development',
        'DEBUG': 'True',
        'EMAIL_BACKEND_MODE': 'console',
        'DATAFAST_TEST_MODE': 'EXTERNAL',
        'DATAFAST_BASE_URL': 'https://eu-test.oppwa.com',
      }
    )
    self.assertEqual(result['engine'], 'django.db.backends.sqlite3')
    self.assertIn('console', result['backend'])

  def test_development_metadata_defaults_empty_not_invented(self):
    result = self.assert_valid(
      {
        'DATABASE_URL': '',
        'DJANGO_ENV': 'development',
        'DEBUG': 'True',
        'EMAIL_BACKEND_MODE': 'console',
        'DATAFAST_BASE_URL': 'https://eu-test.oppwa.com',
      },
      remove=('DATAFAST_ECI', 'DATAFAST_PSERV', 'DATAFAST_MERCHANT_NAME', 'DATAFAST_CART_PRICE_BASIS'),
    )
    self.assertEqual(result['checkout_metadata'], ['', '', '', ''])

  def test_legacy_env_bootstrap_without_reading_private_file(self):
    result = self.assert_valid(
      {'DEBUG': 'True', 'EMAIL_BACKEND_MODE': 'console', 'DATAFAST_BASE_URL': 'https://eu-test.oppwa.com'},
      remove=('DJANGO_ENV', 'DATABASE_URL'),
    )
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
      'DATAFAST_ECI': ['', ' ', 'bad\nvalue'],
      'DATAFAST_PSERV': ['', 'bad\rvalue'],
      'DATAFAST_MERCHANT_NAME': ['', 'x' * 31, 'Merchant&Co'],
      'DATAFAST_CART_PRICE_BASIS': ['', 'other'],
      'DATAFAST_MID': ['1000000406'],
      'DATAFAST_TID': ['PD100406'],
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

  def test_localhost_opt_in_rejected_at_strict_startup(self):
    for profile in ('staging', 'production'):
      for debug in ('False', 'True'):
        with self.subTest(profile=profile, debug=debug):
          result = profile_result({'DJANGO_ENV': profile, 'DEBUG': debug, 'DATAFAST_ALLOW_LOCALHOST': 'True'})
          self.assertNotEqual(result.returncode, 0)
          self.assertIn('DATAFAST_ALLOW_LOCALHOST', result.stderr)

  def test_localhost_flag_boolean_validation(self):
    result = profile_result({'DATAFAST_ALLOW_LOCALHOST': 'perhaps'})
    self.assertNotEqual(result.returncode, 0)
    self.assertIn('DATAFAST_ALLOW_LOCALHOST', result.stderr)

  def test_environment_defaults_and_explicit_modes(self):
    self.assertEqual(self.assert_valid()['environment'], 'production')
    development = {
      'DJANGO_ENV': 'development',
      'DATABASE_URL': '',
      'DEBUG': 'True',
      'EMAIL_BACKEND_MODE': 'console',
      'DATAFAST_BASE_URL': 'https://eu-test.oppwa.com',
      'DATAFAST_TEST_MODE': 'EXTERNAL',
    }
    self.assertEqual(self.assert_valid(development)['environment'], 'phase2')
    phase1 = dict(
      development,
      DATAFAST_ENVIRONMENT='phase1',
      DATAFAST_BASE_URL='https://test.oppwa.com/v1/',
      DATAFAST_TEST_MODE='',
      DATAFAST_PHASE1_ENTITY_ID='fake-phase1',
      DATAFAST_PHASE1_AUTH_TOKEN='fake-phase1-token',
    )
    result = self.assert_valid(
      phase1, remove=('DATAFAST_ENTITY_ID', 'DATAFAST_AUTH_TOKEN', 'DATAFAST_MID', 'DATAFAST_TID')
    )
    self.assertEqual(result['environment'], 'phase1')
    self.assertEqual(result['entity'], 'fake-phase1')
    self.assertEqual(result['base'], 'https://test.oppwa.com/v1/')
    for key in ('DATAFAST_PHASE1_ENTITY_ID', 'DATAFAST_PHASE1_AUTH_TOKEN'):
      self.assertNotEqual(profile_result(phase1, remove=(key,)).returncode, 0)
    for overrides in (
      {'DATAFAST_ENVIRONMENT': ''},
      {'DATAFAST_ENVIRONMENT': 'invalid'},
      {'DATAFAST_ENVIRONMENT': 'phase1'},
      {'DATAFAST_ENVIRONMENT': 'phase2'},
      dict(development, DATAFAST_ENVIRONMENT='production'),
      dict(phase1, DEBUG='False'),
      dict(phase1, DATAFAST_TEST_MODE='EXTERNAL'),
      dict(phase1, DATAFAST_BASE_URL='https://eu-test.oppwa.com'),
      dict(phase1, DJANGO_ENV='staging'),
    ):
      with self.subTest(overrides=overrides):
        self.assertNotEqual(profile_result(overrides).returncode, 0)

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
      'DATAFAST_ECI',
      'DATAFAST_PSERV',
      'DATAFAST_MERCHANT_NAME',
      'DATAFAST_CART_PRICE_BASIS',
    ):
      with self.subTest(key=key):
        result = profile_result(remove=(key,))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ImproperlyConfigured', result.stderr)
    result = profile_result({'EMAIL_BACKEND_MODE': 'resend'})
    self.assertNotEqual(result.returncode, 0)
    self.assertIn('ImproperlyConfigured', result.stderr)
