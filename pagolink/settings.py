import os
import environ
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

from decimal import Decimal

# Initialize environ
env = environ.Env(
  DEBUG=(bool, False),
  TAX_IVA=(Decimal, Decimal('0.12'))
)

# Read .env file
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])


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

# ============================================================
# EMAIL CONFIGURATION (Resend via django-anymail)
# ============================================================
# Environment-aware backend selection:
#   EMAIL_BACKEND_MODE=resend  → Resend API (even with DEBUG=True)
#   EMAIL_BACKEND_MODE=console → console backend (prints to stdout)
#   (unset) + DEBUG=True       → console backend (safe local dev default)
#   (unset) + DEBUG=False      → Resend API (production default)

EMAIL_BACKEND_MODE = env('EMAIL_BACKEND_MODE', default=None)

if EMAIL_BACKEND_MODE == 'resend':
    EMAIL_BACKEND = 'anymail.backends.resend.EmailBackend'
    ANYMAIL = {
        'RESEND_API_KEY': env('RESEND_API_KEY'),
    }
elif EMAIL_BACKEND_MODE == 'console' or DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'anymail.backends.resend.EmailBackend'
    ANYMAIL = {
        'RESEND_API_KEY': env('RESEND_API_KEY'),
    }

DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='PagoLink <noreply@pagolink.ec>')

# Register anymail as an installed app (idempotent)
if 'anymail' not in INSTALLED_APPS:
    INSTALLED_APPS.append('anymail')

# Configuración Datafast
DATAFAST_BASE_URL = env('DATAFAST_BASE_URL', default='https://eu-test.oppwa.com/v1/')
DATAFAST_ENTITY_ID = env('DATAFAST_ENTITY_ID')
DATAFAST_AUTH_TOKEN = env('DATAFAST_AUTH_TOKEN')
DATAFAST_MID = env('DATAFAST_MID')
DATAFAST_TID = env('DATAFAST_TID')
DATAFAST_TEST_MODE = env('DATAFAST_TEST_MODE', default=None)
TAX_IVA = Decimal(os.getenv('TAX_IVA', '0.12'))
