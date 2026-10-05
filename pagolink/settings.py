import os
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import environ

from pagolink.production import (
  DATAFAST_ROOTS,
  boolean,
  datafast_environment,
  email_settings,
  invalid,
  required,
  secure_profile,
  validate_datafast,
)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize environ
env = environ.Env(DEBUG=(bool, False), TAX_IVA=(Decimal, Decimal('0.12')))

# Legacy local bootstrap only. Explicit profiles use exported environment variables;
# production must never accidentally inherit development .env credentials.
if 'DJANGO_ENV' not in os.environ:
  environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

DJANGO_ENV = os.environ.get('DJANGO_ENV', 'development')
if DJANGO_ENV not in ('development', 'staging', 'production'):
  invalid('DJANGO_ENV')
STRICT_PROFILE = DJANGO_ENV in ('staging', 'production')
SECRET_KEY = required('SECRET_KEY')
DEBUG = boolean('DEBUG')
DATAFAST_ALLOW_LOCALHOST = boolean('DATAFAST_ALLOW_LOCALHOST')
if STRICT_PROFILE and DATAFAST_ALLOW_LOCALHOST:
  invalid('DATAFAST_ALLOW_LOCALHOST')

ALLOWED_HOSTS = [host.strip() for host in os.environ.get('ALLOWED_HOSTS', '').split(',') if host.strip()]


# Application definition

INSTALLED_APPS = [
  'django.contrib.admin',
  'django.contrib.auth',
  'django.contrib.contenttypes',
  'django.contrib.sessions',
  'django.contrib.messages',
  'django.contrib.staticfiles',
  'landing',
  'dashboard',
  'accounts',
  'payments',
  'banking',
  'gateways',
]

MIDDLEWARE = [
  'django.middleware.security.SecurityMiddleware',
  'django.contrib.sessions.middleware.SessionMiddleware',
  'django.middleware.common.CommonMiddleware',
  'django.middleware.csrf.CsrfViewMiddleware',
  'django.contrib.auth.middleware.AuthenticationMiddleware',
  'django.contrib.messages.middleware.MessageMiddleware',
  'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'pagolink.urls'

TEMPLATES = [
  {
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {
      'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
      ],
    },
  },
]

WSGI_APPLICATION = 'pagolink.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
  'default': {
    'ENGINE': 'django.db.backends.sqlite3',
    'NAME': BASE_DIR / 'db.sqlite3',
  }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
  {
    'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
  },
  {
    'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
  },
  {
    'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
  },
  {
    'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
  },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
# STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Explicit SMTP/Resend in strict profiles; preserve legacy development defaults.
globals().update(email_settings(STRICT_PROFILE, DEBUG))

# Register anymail as an installed app (idempotent)
if 'anymail' not in INSTALLED_APPS:
  INSTALLED_APPS.append('anymail')

# The selector does not change profile, secret, email, database or HTTPS gates.
try:
  DATAFAST_ENVIRONMENT = datafast_environment(os.environ.get('DATAFAST_ENVIRONMENT'), DJANGO_ENV, STRICT_PROFILE, DEBUG)
except ValueError:
  invalid('DATAFAST_ENVIRONMENT')
DATAFAST_BASE_URL = (
  required('DATAFAST_BASE_URL')
  if STRICT_PROFILE
  else os.environ.get('DATAFAST_BASE_URL', DATAFAST_ROOTS[DATAFAST_ENVIRONMENT])
)
# Explicit host contradictions are never silently redirected to another mode.
_datafast_base = urlsplit(DATAFAST_BASE_URL)
if (
  _datafast_base.scheme != 'https'
  or _datafast_base.netloc != urlsplit(DATAFAST_ROOTS[DATAFAST_ENVIRONMENT]).netloc
  or _datafast_base.path not in ('', '/', '/v1', '/v1/')
  or _datafast_base.query
  or _datafast_base.fragment
  or '?' in DATAFAST_BASE_URL
  or '#' in DATAFAST_BASE_URL
  or any(char.isspace() for char in DATAFAST_BASE_URL)
):
  invalid('DATAFAST_BASE_URL')
DATAFAST_TEST_MODE = os.environ.get('DATAFAST_TEST_MODE', 'EXTERNAL' if DATAFAST_ENVIRONMENT == 'phase2' else '')
if DATAFAST_ENVIRONMENT == 'phase2':
  if DATAFAST_TEST_MODE != 'EXTERNAL':
    invalid('DATAFAST_TEST_MODE')
elif DATAFAST_TEST_MODE not in (None, ''):
  invalid('DATAFAST_TEST_MODE')
if DATAFAST_ENVIRONMENT == 'phase1':
  DATAFAST_PHASE1_ENTITY_ID = required('DATAFAST_PHASE1_ENTITY_ID')
  DATAFAST_PHASE1_AUTH_TOKEN = required('DATAFAST_PHASE1_AUTH_TOKEN')
  DATAFAST_ENTITY_ID = DATAFAST_PHASE1_ENTITY_ID
  DATAFAST_AUTH_TOKEN = DATAFAST_PHASE1_AUTH_TOKEN
  DATAFAST_MID = DATAFAST_TID = ''
else:
  DATAFAST_ENTITY_ID = required('DATAFAST_ENTITY_ID')
  DATAFAST_AUTH_TOKEN = required('DATAFAST_AUTH_TOKEN')
  DATAFAST_MID = required('DATAFAST_MID')
  DATAFAST_TID = required('DATAFAST_TID')
DATAFAST_ECI = os.environ.get('DATAFAST_ECI', '')
DATAFAST_PSERV = os.environ.get('DATAFAST_PSERV', '')
DATAFAST_MERCHANT_NAME = os.environ.get('DATAFAST_MERCHANT_NAME', '')
DATAFAST_CART_PRICE_BASIS = os.environ.get('DATAFAST_CART_PRICE_BASIS', '')
TAX_IVA = Decimal(os.getenv('TAX_IVA', '0.12'))

if STRICT_PROFILE:
  globals().update(secure_profile(SECRET_KEY, DEBUG))
validate_datafast(STRICT_PROFILE, DATAFAST_BASE_URL, DATAFAST_TEST_MODE)
