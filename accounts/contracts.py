from hashlib import sha256

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_ipv46_address
from django.db import transaction

from .models import ContractAcceptance
from .personalized_contract import MAX_SNAPSHOT_BYTES, current_contract_version, personalized_contract


def has_current_acceptance(seller):
  """Current legal version and intact stored evidence, never a profile rebuild."""
  if getattr(seller, 'pk', None) is None:
    return False
  try:
    version = current_contract_version()
  except ImproperlyConfigured:
    return False
  evidence = ContractAcceptance.objects.filter(seller=seller, version=version).first()
  return bool(
    evidence
    and evidence.text_snapshot
    and evidence.text_hash == sha256(evidence.text_snapshot.encode('utf-8')).hexdigest()
  )


def record_current_acceptance(seller, ip=None, *, preview=None):
  """Persist validated server-held evidence; trusted callers require a valid profile."""
  if preview is None:
    contract = personalized_contract(seller)
    preview = {'version': contract.version, 'text': contract.text, 'text_hash': contract.text_hash}
  text = preview['text']
  if (
    preview['version'] != current_contract_version()
    or not isinstance(text, str)
    or not text
    or len(text.encode('utf-8')) > MAX_SNAPSHOT_BYTES
    or preview['text_hash'] != sha256(text.encode('utf-8')).hexdigest()
  ):
    raise ValidationError('Invalid contract preview')
  try:
    validate_ipv46_address(ip or '')
  except (ValidationError, TypeError):
    ip = None
  # Location is optional: acceptance must not depend on an external lookup.
  with transaction.atomic():
    return ContractAcceptance.objects.get_or_create(
      seller=seller,
      version=preview['version'],
      defaults={'text_hash': preview['text_hash'], 'text_snapshot': text, 'ip': ip},
    )[0]
