from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.query import QuerySet
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse

from accounts.contracts import has_current_acceptance, record_current_acceptance
from accounts.models import ContractAcceptance, CustomUser
from accounts.personalized_contract import personalized_contract
from accounts.services import login_redirect_url
from accounts.test_personalized_contract import populate_declared_profile


class AcceptanceEvidenceTests(TestCase):
  def setUp(self):
    self.user = User.objects.create_user('seller')
    self.seller = populate_declared_profile(CustomUser.objects.create(user=self.user, identification=789))
    self.contract = personalized_contract(self.seller)

  def test_test_database_is_isolated_memory_sqlite(self):
    self.assertEqual(connection.vendor, 'sqlite')
    self.assertIn('memory', connection.settings_dict['NAME'])

  def test_predicate_requires_full_current_identity(self):
    self.assertFalse(has_current_acceptance(None))
    with self.assertNumQueries(0):
      self.assertFalse(has_current_acceptance(CustomUser()))
    for field, invalid in (('version', 'old'), ('text_hash', '0' * 64), ('text_snapshot', 'Other terms')):
      with self.subTest(field=field):
        evidence = record_current_acceptance(self.seller)
        ContractAcceptance.objects.filter(pk=evidence.pk).update(**{field: invalid})
        self.assertFalse(has_current_acceptance(self.seller))
        self.assertEqual(login_redirect_url(self.user), reverse('dashboard:contract'))
        ContractAcceptance.objects.filter(pk=evidence.pk).update(
          version=self.contract.version, text_hash=self.contract.text_hash, text_snapshot=self.contract.text
        )
        self.assertTrue(has_current_acceptance(self.seller))

  def test_database_uniqueness_and_race_retry_preserve_snapshot(self):
    evidence = record_current_acceptance(self.seller, '127.0.0.1')
    snapshot = ContractAcceptance.objects.values().get(pk=evidence.pk)
    with self.assertRaises(IntegrityError), transaction.atomic():
      ContractAcceptance.objects.create(
        seller=self.seller, version=self.contract.version, text_hash='0' * 64, text_snapshot='Replacement'
      )
    # Simulate a concurrent insert becoming visible between first get and create.
    # The real insert hits DB uniqueness; Django retries get after its savepoint.
    original_get = QuerySet.get
    first = True

    def concurrent_get(queryset, *args, **kwargs):
      nonlocal first
      if queryset.model is ContractAcceptance and first:
        first = False
        raise ContractAcceptance.DoesNotExist
      return original_get(queryset, *args, **kwargs)

    with patch.object(QuerySet, 'get', concurrent_get):
      retried = record_current_acceptance(self.seller, '127.0.0.2')
    self.assertEqual(retried.pk, evidence.pk)
    self.assertEqual(ContractAcceptance.objects.values().get(pk=evidence.pk), snapshot)
    self.assertEqual(ContractAcceptance.objects.count(), 1)

  def test_staff_login_still_uses_admin(self):
    self.user.is_staff = True
    self.assertEqual(login_redirect_url(self.user), reverse('admin:index'))


class AcceptanceAdminTests(TestCase):
  def setUp(self):
    self.admin_user = User.objects.create_superuser('admin', 'admin@example.com', 'secret')
    self.seller = populate_declared_profile(CustomUser.objects.create(user=self.admin_user, identification=987))
    self.contract = personalized_contract(self.seller)
    self.evidence = record_current_acceptance(self.seller)
    self.client.force_login(self.admin_user)

  def test_evidence_admin_is_read_only_even_for_superuser(self):
    presentation = admin.site._registry[ContractAcceptance]
    request = RequestFactory().get('/')
    request.user = self.admin_user
    self.assertTrue(presentation.has_view_permission(request, self.evidence))
    self.assertFalse(presentation.has_add_permission(request))
    self.assertFalse(presentation.has_change_permission(request, self.evidence))
    self.assertFalse(presentation.has_delete_permission(request, self.evidence))
    self.assertNotIn('delete_selected', presentation.get_actions(request))
    self.assertEqual(
      set(presentation.readonly_fields),
      {'seller', 'version', 'text_hash', 'text_snapshot', 'accepted_at', 'ip', 'city'},
    )
    url = reverse('admin:accounts_contractacceptance_change', args=[self.evidence.pk])
    self.assertContains(self.client.get(url), self.contract.version)
    self.assertEqual(self.client.post(url, {'text_snapshot': 'Changed'}).status_code, 403)
    self.assertEqual(self.client.post(reverse('admin:accounts_contractacceptance_add'), {}).status_code, 403)
    delete_url = reverse('admin:accounts_contractacceptance_delete', args=[self.evidence.pk])
    self.assertEqual(self.client.post(delete_url, {'post': 'yes'}).status_code, 403)
    self.evidence.refresh_from_db()
    self.assertEqual(self.evidence.text_snapshot, self.contract.text)


class AdditiveAcceptanceMigrationTests(TransactionTestCase):
  def test_0004_preserves_legacy_rows_without_backfill(self):
    self.assertEqual(connection.vendor, 'sqlite')
    self.assertIn('memory', connection.settings_dict['NAME'])
    before = [('accounts', '0003_customuser_is_admin_role')]
    after = [('accounts', '0004_contractacceptance')]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    try:
      old_apps = executor.loader.project_state(before).apps
      user = old_apps.get_model('auth', 'User').objects.create(username='legacy')
      seller = old_apps.get_model('accounts', 'CustomUser').objects.create(user_id=user.pk, identification=654)
      legacy_model = old_apps.get_model('accounts', 'Contract')
      legacy = legacy_model.objects.create(seller_id=seller.pk, ip='127.0.0.8', city='Legacy city')
      original = legacy_model.objects.values().get(pk=legacy.pk)
      executor = MigrationExecutor(connection)
      executor.migrate(after)
      new_apps = executor.loader.project_state(after).apps
      self.assertEqual(new_apps.get_model('accounts', 'Contract').objects.values().get(pk=legacy.pk), original)
      self.assertFalse(new_apps.get_model('accounts', 'ContractAcceptance').objects.exists())
    finally:
      executor = MigrationExecutor(connection)
      executor.migrate(executor.loader.graph.leaf_nodes())
