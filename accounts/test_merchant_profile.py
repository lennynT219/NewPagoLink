from importlib import import_module

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from accounts.forms import UserProfileForm
from accounts.models import ContractAcceptance, CustomUser

LEGAL_DATA = {
  'commerce_name': 'Comercio de Prueba S.A.',
  'commerce_ruc': '1799999999001',
  'commerce_address': 'Calle de Prueba 123, Quito',
  'legal_representative_name': 'Representante de Prueba',
  'commerce_identification': '1234567890',
}


class MerchantProfileTests(TestCase):
  def setUp(self):
    self.user = User.objects.create_user(
      username='merchant', email='merchant@example.com', first_name='Personal', last_name='Name'
    )
    self.seller = CustomUser.objects.create(user=self.user, phone='0999999999', identification=1111111111)
    self.other = User.objects.create_user(username='other', email='other@example.com')
    self.other_seller = CustomUser.objects.create(user=self.other, phone='0888888888', identification=2222222222)
    self.url = reverse('dashboard:user-update')

  def payload(self, **overrides):
    data = dict(
      firstname='Personal',
      lastname='Updated',
      email=self.user.email,
      identification=self.seller.identification,
      phone='0999999999',
      **LEGAL_DATA,
    )
    data.update(overrides)
    return data

  def helper(self):
    # Import at execution time so missing behavior is not a discovery failure.
    return import_module('accounts.merchant_profile')

  def test_declared_values_persist_separately(self):
    form = UserProfileForm(self.payload(), instance=self.user)
    self.assertTrue(form.is_valid(), form.errors)
    form.save()
    self.seller.refresh_from_db()
    self.user.refresh_from_db()
    self.assertEqual(self.seller.identification, 1111111111)
    self.assertEqual(self.user.last_name, 'Updated')
    for field, value in LEGAL_DATA.items():
      self.assertEqual(getattr(self.seller, field, None), value)

  def test_no_inference_from_personal_fields(self):
    helper = self.helper()
    self.assertEqual(helper.missing_contract_profile_fields(self.seller), tuple(LEGAL_DATA))
    self.assertEqual(helper.contract_profile_data(self.seller), dict.fromkeys(LEGAL_DATA, ''))

  def test_owner_can_edit_before_acceptance_without_granting_acceptance(self):
    self.client.force_login(self.user)
    response = self.client.get(self.url)
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, 'Datos del comercio')
    response = self.client.post(self.url, self.payload(sellerID=self.other_seller.pk, user=self.other.pk))
    self.assertEqual(response.status_code, 302)
    self.seller.refresh_from_db()
    self.other_seller.refresh_from_db()
    self.assertEqual(getattr(self.seller, 'commerce_name', None), LEGAL_DATA['commerce_name'])
    self.assertEqual(getattr(self.other_seller, 'commerce_name', None), '')
    self.assertFalse(ContractAcceptance.objects.exists())

  def test_anonymous_cannot_read_or_save(self):
    for method in (self.client.get, self.client.post):
      response = method(self.url, self.payload())
      self.assertEqual(response.status_code, 302)
      self.assertIn('login', response['Location'])

  def test_readonly_identity_cannot_be_changed_by_post(self):
    form = UserProfileForm(self.payload(email='attacker@example.com', identification=2222222222), instance=self.user)
    self.assertTrue(form.is_valid(), form.errors)
    form.save()
    self.user.refresh_from_db()
    self.seller.refresh_from_db()
    self.assertEqual(self.user.email, 'merchant@example.com')
    self.assertEqual(self.seller.identification, 1111111111)

  def test_partial_or_whitespace_profile_can_be_saved_but_is_incomplete(self):
    form = UserProfileForm(self.payload(**dict.fromkeys(LEGAL_DATA, '  ')), instance=self.user)
    self.assertTrue(form.is_valid(), form.errors)
    form.save()
    self.seller.refresh_from_db()
    self.assertEqual(self.helper().missing_contract_profile_fields(self.seller), tuple(LEGAL_DATA))
    for field in LEGAL_DATA:
      self.assertEqual(getattr(self.seller, field), '')

  def test_invalid_formats_and_lengths_rejected(self):
    invalid_values = {
      'commerce_ruc': ['abc', '123', '1' * 14, '１' * 13],
      'commerce_identification': ['abc', '123', '1' * 11],
      'commerce_name': ['x' * 256],
      'commerce_address': ['x' * 501],
      'legal_representative_name': ['x' * 301],
    }
    for field, values in invalid_values.items():
      for value in values:
        with self.subTest(field=field, value=value):
          form = UserProfileForm(self.payload(**{field: value}), instance=self.user)
          self.assertFalse(form.is_valid())
          self.assertIn(field, form.errors)

  def test_completeness_checks_validity_not_only_presence(self):
    helper = self.helper()
    for field, value in LEGAL_DATA.items():
      setattr(self.seller, field, ' ' + value + ' ')
    self.assertEqual(helper.missing_contract_profile_fields(self.seller), ())
    self.assertEqual(helper.contract_profile_data(self.seller), LEGAL_DATA)
    self.seller.commerce_ruc = 'invalid'
    self.seller.commerce_address = '   '
    self.assertEqual(helper.missing_contract_profile_fields(self.seller), ('commerce_ruc', 'commerce_address'))

  def test_missing_business_values_do_not_block_personal_edits(self):
    data = self.payload()
    for field in LEGAL_DATA:
      data.pop(field)
    form = UserProfileForm(data, instance=self.user)
    self.assertTrue(form.is_valid(), form.errors)
    form.save()
    self.user.refresh_from_db()
    self.assertEqual(self.user.last_name, 'Updated')
    self.assertEqual(self.helper().missing_contract_profile_fields(self.seller), tuple(LEGAL_DATA))

  def test_profile_edits_preserve_existing_evidence(self):
    evidence = ContractAcceptance.objects.create(
      seller=self.seller, version='preserved', text_hash='a' * 64, text_snapshot='Accepted original text'
    )
    original_timestamp = evidence.accepted_at
    form = UserProfileForm(self.payload(), instance=self.user)
    self.assertTrue(form.is_valid(), form.errors)
    form.save()
    evidence.refresh_from_db()
    self.assertEqual(evidence.text_snapshot, 'Accepted original text')
    self.assertEqual(evidence.text_hash, 'a' * 64)
    self.assertEqual(evidence.accepted_at, original_timestamp)

  def test_invalid_stored_metadata_is_incomplete(self):
    helper = self.helper()
    for field, value in LEGAL_DATA.items():
      setattr(self.seller, field, value)
    self.seller.commerce_name = 'x' * 256
    self.seller.commerce_identification = None
    self.assertEqual(helper.missing_contract_profile_fields(self.seller), ('commerce_name', 'commerce_identification'))

  def test_model_validation_matches_form(self):
    self.seller.commerce_ruc = 'not-a-ruc'
    with self.assertRaises(ValidationError):
      self.seller.full_clean()


class MerchantProfileMigrationTests(TransactionTestCase):
  def test_existing_accounts_and_evidence_survive_additive_migration(self):
    self.assertIn('memory', connection.settings_dict['NAME'])
    executor = MigrationExecutor(connection)
    executor.migrate([('accounts', '0004_contractacceptance')])
    try:
      apps = executor.loader.project_state([('accounts', '0004_contractacceptance')]).apps
      user = apps.get_model('auth', 'User').objects.create(username='existing')
      seller = apps.get_model('accounts', 'CustomUser').objects.create(
        user_id=user.pk, phone='0999999999', identification=3333333333
      )
      evidence = apps.get_model('accounts', 'ContractAcceptance').objects.create(
        seller_id=seller.pk, version='preserved', text_hash='a' * 64, text_snapshot='Original snapshot'
      )
      legacy = apps.get_model('accounts', 'Contract').objects.create(
        seller_id=seller.pk, ip='127.0.0.1', city='Original city'
      )
      MigrationExecutor(connection).migrate([('accounts', '0005_merchant_contract_profile')])
      updated = CustomUser.objects.get(pk=seller.pk)
      for field in LEGAL_DATA:
        self.assertEqual(getattr(updated, field), '')
      self.assertEqual(updated.identification, 3333333333)
      self.assertEqual(ContractAcceptance.objects.get(pk=evidence.pk).text_snapshot, 'Original snapshot')
      self.assertEqual(import_module('accounts.models').Contract.objects.get(pk=legacy.pk).city, 'Original city')
    finally:
      executor = MigrationExecutor(connection)
      executor.migrate(executor.loader.graph.leaf_nodes())
