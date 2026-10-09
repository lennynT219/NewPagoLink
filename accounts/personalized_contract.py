"""Declared-party rendering and bounded, session-held contract previews."""

import json
import re
import secrets
import time
from dataclasses import dataclass
from hashlib import sha256

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_email

from .contract_terms import CONTRACT_PARAGRAPHS, CONTRACT_SHA256, _paragraph_kind
from .merchant_profile import CONTRACT_PROFILE_FIELDS, contract_profile_data, missing_contract_profile_fields

PROVIDER_DEFAULTS = {
  'name': 'ADREST DEL ECUADOR CÍA. LTDA.',
  'ruc': '1792901286001',
  'city': 'QUITO',
  'representative': 'Adriana Zenovia Vásquez Macías',
  'role': 'Gerente General',
}
PREVIEW_SESSION_KEY = 'contract_preview'
PREVIEW_MAX_AGE = 1800
MAX_SNAPSHOT_BYTES = 65536


def usable_text(value, limit):
  """Reject blank/placeholder and paragraph-breaking declared party values."""
  return (
    isinstance(value, str)
    and bool(value.strip())
    and len(value) <= limit
    and not any(character in value for character in ('[', ']', '\n', '\r', '\x00'))
    and not re.fullmatch(r'[\s_\-]+', value)
  )


def provider_data():
  """Only this structured legal setting may override approved DOCX defaults."""
  configured = getattr(settings, 'PAGOLINK_CONTRACT_PROVIDER', PROVIDER_DEFAULTS)
  if not isinstance(configured, dict) or set(configured) != set(PROVIDER_DEFAULTS):
    raise ImproperlyConfigured('Invalid contract provider configuration')
  if not all(usable_text(value, 300) for value in configured.values()):
    raise ImproperlyConfigured('Invalid contract provider configuration')
  provider = {key: value.strip() for key, value in configured.items()}
  if not re.fullmatch(r'[0-9]{13}', provider['ruc']):
    raise ImproperlyConfigured('Invalid contract provider configuration')
  return provider


def current_contract_version():
  """Legal identity excludes all mutable merchant data; v1 identifies slot rules."""
  identity = json.dumps(
    {'base': CONTRACT_SHA256, 'slots': 'v1', 'provider': provider_data()},
    ensure_ascii=False,
    sort_keys=True,
    separators=(',', ':'),
  )
  return 'pagolink-personalized-v1-' + sha256(identity.encode('utf-8')).hexdigest()


class IncompleteContractProfile(ValidationError):
  pass


@dataclass(frozen=True)
class PersonalizedContract:
  version: str
  text: str
  text_hash: str
  blocks: tuple


def personalized_contract(seller):
  provider = provider_data()
  data = contract_profile_data(seller)
  missing = list(missing_contract_profile_fields(seller))
  for field, value in data.items():
    if not usable_text(value, seller._meta.get_field(field).max_length) and field not in missing:
      missing.append(field)
  labels = [CONTRACT_PROFILE_FIELDS[field] for field in missing]
  email = seller.user.email.strip()
  phone = seller.phone.strip()
  try:
    validate_email(email)
    if not usable_text(email, 254):
      raise ValidationError('Invalid contact')
  except ValidationError:
    labels.append('Correo electrónico registrado (solicitá su actualización al administrador de la cuenta)')
  if not re.fullmatch(r'[0-9]{10}', phone):
    labels.append('Teléfono registrado de contacto')
  if labels:
    raise IncompleteContractProfile('Completá o corregí tu perfil antes de aceptar: ' + '; '.join(labels) + '.')
  paragraphs: list[str] = list(CONTRACT_PARAGRAPHS)
  # Substitute only the opening's declared slots in a single pass. Declared text
  # is never interpreted as another replacement token or as template markup.
  opening = paragraphs[1]
  replacements = {default: provider[key] for key, default in PROVIDER_DEFAULTS.items()}
  replacements.update(
    {
      '[NOMBRE DEL COMERCIO]': data['commerce_name'],
      'con Registro Único de Contribuyentes No. [__________]': 'con Registro Único de Contribuyentes No. '
      + data['commerce_ruc'],
      'cédula de identidad No.       ': 'cédula de identidad No. ' + data['commerce_identification'],
      '[NOMBRE DEL REPRESENTANTE LEGAL]': data['legal_representative_name'],
      'con domicilio principal en [__________]': 'con domicilio principal en ' + data['commerce_address'],
    }
  )
  paragraphs[1] = re.sub(
    '|'.join(re.escape(key) for key in replacements), lambda match: replacements[match.group()], opening
  )
  notices = {
    'Correo electrónico:': 'Correo electrónico: ' + email,
    'Teléfono:': 'Teléfono: ' + phone,
    'Dirección domicilio': 'Dirección domicilio ' + data['commerce_address'],
  }
  paragraphs = [notices.get(text, text) for text in paragraphs]
  text = '\n\n'.join(paragraphs)
  if len(text.encode('utf-8')) > MAX_SNAPSHOT_BYTES:
    raise IncompleteContractProfile('Los datos declarados exceden el tamaño permitido. Revisá tu perfil.')
  return PersonalizedContract(
    current_contract_version(),
    text,
    sha256(text.encode('utf-8')).hexdigest(),
    tuple((_paragraph_kind(index, value), value) for index, value in enumerate(paragraphs)),
  )


def prepare_preview(request, seller, contract):
  """One draft per session: subsequent previews replace it, never accumulate."""
  token = secrets.token_urlsafe(32)
  request.session[PREVIEW_SESSION_KEY] = {
    'token': token,
    'user': request.user.pk,
    'seller': seller.pk,
    'issued': time.time(),
    'version': contract.version,
    'text_hash': contract.text_hash,
    'text': contract.text,
  }
  return token


def validated_preview(request, seller, contract, data):
  """Compare fresh terms to the server-held draft, but persist the draft itself."""
  draft = request.session.get(PREVIEW_SESSION_KEY)
  token = data.get('preview_token', '')
  if not isinstance(draft, dict) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
    return None
  if (
    draft.get('user') != request.user.pk
    or draft.get('seller') != seller.pk
    or not isinstance(draft.get('issued'), (float, int))
    or not 0 <= time.time() - draft['issued'] <= PREVIEW_MAX_AGE
    or not secrets.compare_digest(str(draft.get('token', '')), token)
    or draft.get('version') != data.get('version')
    or draft.get('text_hash') != data.get('text_hash')
    or draft.get('version') != contract.version
    or draft.get('text_hash') != contract.text_hash
    or draft.get('text') != contract.text
  ):
    return None
  return draft
