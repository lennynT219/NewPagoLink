"""Environment-only profile compilation; never connect to external services."""

import ipaddress
import os
import re
from email.utils import parseaddr
from typing import NoReturn
from urllib.parse import parse_qsl, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured


def invalid(key) -> NoReturn:
  raise ImproperlyConfigured(f'Invalid or missing {key} configuration') from None


def required(key):
  value = os.environ.get(key, '')
  if not value.strip():
    invalid(key)
  return value


def boolean(key, default=False):
  value = os.environ.get(key, str(default)).lower()
  if value not in ('true', 'false', '1', '0'):
    invalid(key)
  return value in ('true', '1')


def integer(key, default, minimum=0, maximum=None):
  try:
    value = int(os.environ.get(key, str(default)))
  except ValueError:
    invalid(key)
  if value < minimum or (maximum is not None and value > maximum):
    invalid(key)
  return value


def hostname(value):
  try:
    ipaddress.ip_address(value)
    return True
  except ValueError:
    return bool(
      re.fullmatch(
        r'(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*', value
      )
    )


def https_root(value, key):
  try:
    parsed = urlsplit(value)
    if (
      parsed.scheme != 'https'
      or not parsed.hostname
      or not hostname(parsed.hostname)
      or parsed.username is not None
      or parsed.password is not None
      or parsed.path not in ('', '/')
      or parsed.query
      or parsed.fragment
      or parsed.port not in (None, 443)
      or any(char.isspace() for char in value)
      or '?' in value
      or '#' in value
    ):
      invalid(key)
    return parsed.hostname
  except ValueError:
    invalid(key)


def postgres_database():
  key = 'DATABASE_URL'
  value = required(key)
  try:
    parsed = urlsplit(value)
    # Allow only explicit libpq TLS configuration, never arbitrary connection options.
    pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    options = dict(pairs)
    name = unquote(parsed.path[1:])
    decoded_fields = [name, unquote(parsed.username or ''), unquote(parsed.password or '')]
    if (
      re.search(r'%(?![0-9a-fA-F]{2})', value)
      or any(any(ord(char) < 32 for char in field) for field in decoded_fields)
      or parsed.scheme not in ('postgres', 'postgresql')
      or not parsed.hostname
      or not hostname(parsed.hostname)
      or not parsed.username
      or not parsed.password
      or not name
      or '/' in name
      or parsed.fragment
      or any(char.isspace() for char in value)
      or len(options) != len(pairs)
      or set(options) - {'sslmode', 'sslrootcert'}
      or options.get('sslmode') not in ('require', 'verify-ca', 'verify-full')
      or ('sslrootcert' in options and not options['sslrootcert'])
      or (options.get('sslmode') in ('verify-ca', 'verify-full') and not options.get('sslrootcert'))
      or (parsed.port is not None and not 1 <= parsed.port <= 65535)
    ):
      invalid(key)
    return {
      'ENGINE': 'django.db.backends.postgresql',
      'NAME': name,
      'USER': unquote(parsed.username or ''),
      'PASSWORD': unquote(parsed.password or ''),
      'HOST': parsed.hostname,
      'PORT': parsed.port or 5432,
      'OPTIONS': options,
    }
  except ValueError:
    invalid(key)


def email_settings(strict, debug):
  mode = os.environ.get('EMAIL_BACKEND_MODE')
  if mode is None and not strict:
    mode = 'console' if debug else 'resend'
  if mode not in ('smtp', 'resend', 'console') or (strict and mode == 'console'):
    invalid('EMAIL_BACKEND_MODE')
  sender = (
    required('DEFAULT_FROM_EMAIL') if strict else os.environ.get('DEFAULT_FROM_EMAIL', 'PagoLink <noreply@pagolink.ec>')
  )
  address = parseaddr(sender)[1]
  if strict and (not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', address) or '\n' in sender or '\r' in sender):
    invalid('DEFAULT_FROM_EMAIL')
  result: dict[str, str | int | bool | dict[str, str]] = {'EMAIL_BACKEND_MODE': mode, 'DEFAULT_FROM_EMAIL': sender}
  if mode == 'console':
    result['EMAIL_BACKEND'] = 'django.core.mail.backends.console.EmailBackend'
  elif mode == 'resend':
    result.update(
      EMAIL_BACKEND='anymail.backends.resend.EmailBackend', ANYMAIL={'RESEND_API_KEY': required('RESEND_API_KEY')}
    )
  else:
    tls, ssl = boolean('EMAIL_USE_TLS', True), boolean('EMAIL_USE_SSL')
    if (tls and ssl) or (strict and not (tls or ssl)):
      invalid('EMAIL_USE_TLS/EMAIL_USE_SSL')
    result.update(
      EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
      EMAIL_HOST=required('EMAIL_HOST'),
      EMAIL_HOST_USER=required('EMAIL_HOST_USER'),
      EMAIL_HOST_PASSWORD=required('EMAIL_HOST_PASSWORD'),
      EMAIL_PORT=integer('EMAIL_PORT', 465 if ssl else 587, 1, 65535),
      EMAIL_USE_TLS=tls,
      EMAIL_USE_SSL=ssl,
      EMAIL_TIMEOUT=30,
    )
  return result


def secure_profile(secret, debug):
  if debug:
    invalid('DEBUG')
  if len(secret) < 50 or len(set(secret)) < 5 or secret.startswith('django-insecure-'):
    invalid('SECRET_KEY')
  hosts = [host.strip() for host in required('ALLOWED_HOSTS').split(',')]
  if any(not hostname(host) for host in hosts):
    invalid('ALLOWED_HOSTS')
  origins = [origin.strip() for origin in required('CSRF_TRUSTED_ORIGINS').split(',')]
  for origin in origins:
    https_root(origin, 'CSRF_TRUSTED_ORIGINS')
  proxy = boolean('TRUST_CONTROLLED_PROXY')
  return {
    'ALLOWED_HOSTS': hosts,
    'CSRF_TRUSTED_ORIGINS': origins,
    'DATABASES': {'default': postgres_database()},
    'SESSION_COOKIE_SECURE': True,
    'CSRF_COOKIE_SECURE': True,
    'SESSION_COOKIE_HTTPONLY': True,
    'SESSION_COOKIE_SAMESITE': 'Lax',
    'CSRF_COOKIE_SAMESITE': 'Lax',
    'SECURE_SSL_REDIRECT': True,
    'SECURE_PROXY_SSL_HEADER': ('HTTP_X_FORWARDED_PROTO', 'https') if proxy else None,
    'SECURE_HSTS_SECONDS': integer('SECURE_HSTS_SECONDS', 0),
    'SECURE_HSTS_INCLUDE_SUBDOMAINS': boolean('SECURE_HSTS_INCLUDE_SUBDOMAINS'),
    'SECURE_HSTS_PRELOAD': boolean('SECURE_HSTS_PRELOAD'),
  }


def validate_checkout_metadata(eci, pserv, merchant_name, price_basis):
  """Shared startup/checkout gate; identifiers are opaque provider-confirmed text."""
  keys = ('DATAFAST_ECI', 'DATAFAST_PSERV', 'DATAFAST_MERCHANT_NAME', 'DATAFAST_CART_PRICE_BASIS')
  for key, value in zip(keys, (eci, pserv, merchant_name, price_basis), strict=True):
    if not isinstance(value, str) or not value.strip() or not value.isprintable():
      raise ValueError(f'Configuración de {key} incompleta o inválida. Contacte a soporte.')
  if len(merchant_name) > 30 or not all(char.isalnum() or char == ' ' for char in merchant_name):
    raise ValueError('Configuración de DATAFAST_MERCHANT_NAME inválida. Contacte a soporte.')
  if price_basis not in ('net', 'gross'):
    raise ValueError('Configuración de DATAFAST_CART_PRICE_BASIS inválida. Contacte a soporte.')


DATAFAST_ROOTS = {
  'phase1': 'https://test.oppwa.com/v1/',
  'phase2': 'https://eu-test.oppwa.com/v1/',
  'production': 'https://eu-prod.oppwa.com/v1/',
}


def datafast_environment(mode, profile, strict, debug):
  """One selector; it never upgrades a development profile into production."""
  if mode is None:
    mode = 'production' if strict else 'phase2'
  if mode not in DATAFAST_ROOTS or profile not in ('development', 'staging', 'production'):
    raise ValueError('Configuración de DATAFAST_ENVIRONMENT inválida.')
  if strict != (profile in ('staging', 'production')):
    raise ValueError('Configuración de DATAFAST_ENVIRONMENT incompatible con el perfil.')
  if mode == 'production':
    if not strict or debug:
      raise ValueError('DATAFAST_ENVIRONMENT=production requiere un perfil estricto sin DEBUG.')
  elif strict or profile != 'development' or (mode == 'phase1' and not debug):
    raise ValueError('Configuración de DATAFAST_ENVIRONMENT incompatible con el perfil.')
  return mode


def validate_datafast(strict, base_url, test_mode):
  if not strict:
    return
  host = https_root(base_url, 'DATAFAST_BASE_URL')
  # Canonical EU hosts match the existing T1 sandbox policy. Alias/payload work is T5b.
  if host != 'eu-prod.oppwa.com':
    invalid('DATAFAST_BASE_URL')
  if test_mode not in (None, ''):
    invalid('DATAFAST_TEST_MODE')
  for key in ('DATAFAST_ENTITY_ID', 'DATAFAST_AUTH_TOKEN', 'DATAFAST_MID', 'DATAFAST_TID'):
    value = required(key)
    if not value.isprintable():
      invalid(key)
  for key, sample in (('DATAFAST_MID', '1000000406'), ('DATAFAST_TID', 'PD100406')):
    if required(key).strip() == sample:
      invalid(key)
  keys = ('DATAFAST_ECI', 'DATAFAST_PSERV', 'DATAFAST_MERCHANT_NAME', 'DATAFAST_CART_PRICE_BASIS')
  values = [required(key) for key in keys]
  try:
    validate_checkout_metadata(*values)
  except ValueError:
    invalid('DATAFAST checkout metadata')
