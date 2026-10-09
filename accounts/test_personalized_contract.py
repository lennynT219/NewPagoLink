"""Legal version identity, declared profile validation and immutable evidence."""

from hashlib import sha256
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.test import TestCase, override_settings

from accounts.contracts import has_current_acceptance, record_current_acceptance
from accounts.models import ContractAcceptance, CustomUser
from accounts.personalized_contract import PROVIDER_DEFAULTS, current_contract_version, personalized_contract


def populate_declared_profile(seller):
  """Explicit synthetic fixture declarations, never a production fallback."""
  seller.commerce_name = 'Comercio de Prueba'
  seller.commerce_ruc = '1791234567001'
  seller.commerce_identification = '0101234567'
  seller.commerce_address = 'Calle de Prueba 42, Cuenca'
  seller.legal_representative_name = 'Representante de Prueba'
  seller.phone = '0999999999'
  seller.user.email = 'registered@example.invalid'
  seller.user.save()
  seller.save()
  return seller


class PersonalizedIdentityTests(TestCase):
  def setUp(self):
    user = User.objects.create_user('seller', first_name='Personal', last_name='Identity')
    self.seller = populate_declared_profile(CustomUser.objects.create(user=user, identification=111))

  def test_distinct_sellers_share_legal_version_not_personalized_snapshot(self):
    first = personalized_contract(self.seller)
    other = populate_declared_profile(
      CustomUser.objects.create(user=User.objects.create_user('other'), identification=222)
    )
    other.commerce_name = 'Otro Comercio'
    other.legal_representative_name = 'Otra Representante'
    other.save()
    second = personalized_contract(other)
    self.assertEqual(first.version, second.version)
    self.assertNotEqual(first.text_hash, second.text_hash)
    self.assertNotIn('Personal Identity', first.text)
    self.assertLessEqual(len(first.version), 128)

  def test_configuration_order_does_not_change_identity_but_values_do(self):
    original = current_contract_version()
    provider = dict(reversed(list(PROVIDER_DEFAULTS.items())))
    with override_settings(PAGOLINK_CONTRACT_PROVIDER=provider):
      self.assertEqual(current_contract_version(), original)
      self.assertIn(PROVIDER_DEFAULTS['name'], personalized_contract(self.seller).text)
    provider['name'] = 'Prestador de Prueba'
    with override_settings(PAGOLINK_CONTRACT_PROVIDER=provider):
      self.assertNotEqual(current_contract_version(), original)
      self.assertIn('Prestador de Prueba', personalized_contract(self.seller).text)

  def test_missing_or_placeholder_party_and_contact_never_inferred(self):
    for field, invalid in (
      ('commerce_ruc', ''),
      ('commerce_name', '[NOMBRE DEL COMERCIO]'),
      ('legal_representative_name', '_____'),
      ('phone', ''),
      ('commerce_address', 'Calle\n\nFalsa'),
    ):
      original = getattr(self.seller, field)
      setattr(self.seller, field, invalid)
      with self.subTest(field=field), self.assertRaises(ValidationError):
        record_current_acceptance(self.seller)
      setattr(self.seller, field, original)
    self.seller.user.email = ''
    with self.assertRaisesMessage(ValidationError, 'Correo electrónico registrado'):
      personalized_contract(self.seller)
    self.assertFalse(ContractAcceptance.objects.exists())

  def test_invalid_provider_fails_closed_without_configuration_details(self):
    for provider in (
      None,
      {},
      {'token': 'must-not-leak'},
      dict(PROVIDER_DEFAULTS, ruc='invalid'),
      dict(PROVIDER_DEFAULTS, city='[CITY]'),
    ):
      with self.subTest(provider=provider), override_settings(PAGOLINK_CONTRACT_PROVIDER=provider):
        with self.assertRaises(ImproperlyConfigured):
          personalized_contract(self.seller)
        self.assertFalse(has_current_acceptance(self.seller))

  def test_predicate_checks_integrity_without_regenerating_after_profile_edit(self):
    evidence = record_current_acceptance(self.seller)
    self.seller.commerce_ruc = ''
    self.seller.save()
    with patch('accounts.contracts.personalized_contract', side_effect=AssertionError('No regeneration')):
      self.assertTrue(has_current_acceptance(self.seller))
    ContractAcceptance.objects.filter(pk=evidence.pk).update(text_snapshot=evidence.text_snapshot + 'changed')
    self.assertFalse(has_current_acceptance(self.seller))
    self.assertEqual(evidence.text_hash, sha256(evidence.text_snapshot.encode()).hexdigest())

  def test_legal_revision_requires_new_acceptance_and_preserves_old_evidence(self):
    evidence = record_current_acceptance(self.seller)
    saved = ContractAcceptance.objects.values().get(pk=evidence.pk)
    with override_settings(PAGOLINK_CONTRACT_PROVIDER=dict(PROVIDER_DEFAULTS, role='Representante Autorizado')):
      self.assertFalse(has_current_acceptance(self.seller))
      record_current_acceptance(self.seller)
      self.assertTrue(has_current_acceptance(self.seller))
    self.assertEqual(ContractAcceptance.objects.values().get(pk=evidence.pk), saved)
