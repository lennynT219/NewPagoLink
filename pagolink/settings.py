import os
from decimal import Decimal
from pathlib import Path

import environ

from pagolink.production import boolean, email_settings, invalid, required, secure_profile, validate_datafast

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

# Configuración Datafast
DATAFAST_BASE_URL = (
  required('DATAFAST_BASE_URL')
  if STRICT_PROFILE
  else os.environ.get('DATAFAST_BASE_URL', 'https://eu-test.oppwa.com/v1/')
)
DATAFAST_ENTITY_ID = required('DATAFAST_ENTITY_ID')
DATAFAST_AUTH_TOKEN = required('DATAFAST_AUTH_TOKEN')
DATAFAST_MID = required('DATAFAST_MID')
DATAFAST_TID = required('DATAFAST_TID')
DATAFAST_TEST_MODE = os.environ.get('DATAFAST_TEST_MODE')
TAX_IVA = Decimal(os.getenv('TAX_IVA', '0.12'))

if STRICT_PROFILE:
  globals().update(secure_profile(SECRET_KEY, DEBUG))
validate_datafast(STRICT_PROFILE, DATAFAST_BASE_URL, DATAFAST_TEST_MODE)
