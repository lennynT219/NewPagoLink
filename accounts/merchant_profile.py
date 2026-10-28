"""Declared merchant identity for contract preparation, without account inference."""

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

CONTRACT_PROFILE_FIELDS = {
  'commerce_name': 'Nombre del comercio o razón social',
  'commerce_ruc': 'RUC del comercio',
  'commerce_address': 'Domicilio principal del comercio (incluí la ciudad)',
  'legal_representative_name': 'Nombre completo del representante legal',
  'commerce_identification': 'Cédula de identidad declarada para el contrato',
}

validate_commerce_ruc = RegexValidator(
  regex=r'\A[0-9]{13}\Z', message='Ingresá un RUC de 13 dígitos. No se verifica su validez oficial.'
)
validate_commerce_identification = RegexValidator(
  regex=r'\A[0-9]{10}\Z', message='Ingresá una cédula de 10 dígitos. No se verifica su validez oficial.'
)


validate_contact_phone = RegexValidator(regex=r'\A[0-9]{10}\Z', message='Ingresá un teléfono de 10 dígitos.')


def contract_profile_data(seller):
  """Return trimmed declared values only; never substitute personal identity."""
  return {
    name: value.strip() if isinstance(value := getattr(seller, name, None), str) else ''
    for name in CONTRACT_PROFILE_FIELDS
  }


def missing_contract_profile_fields(seller):
  """Return absent or invalid field names in contract order for the future gate."""
  data = contract_profile_data(seller)
  missing = []
  for name, value in data.items():
    if not value:
      missing.append(name)
      continue
    try:
      seller._meta.get_field(name).clean(value, seller)
    except ValidationError:
      missing.append(name)
  return tuple(missing)
