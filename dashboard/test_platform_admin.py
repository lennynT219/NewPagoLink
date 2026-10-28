from unittest.mock import patch

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import ContractAcceptance, CustomUser
from accounts.services import login_redirect_url


class PlatformAdministrationTests(TestCase):
  url = '/dashboard/administracion/'

  @classmethod
  def setUpTestData(cls):
    cls.operator = User.objects.create_user('operator@example.com', email='operator@example.com', password='secret')
    cls.admin_profile = CustomUser.objects.create(user=cls.operator, identification=701, is_admin_role=True)
    cls.target = User.objects.create_user('merchant', email='merchant@example.com', password='secret')
    cls.target_profile = CustomUser.objects.create(user=cls.target, identification=702)
    cls.staff = User.objects.create_user('technical', is_staff=True)
    CustomUser.objects.create(user=cls.staff, identification=703)

  def setUp(self):
    self.client.force_login(self.operator)

  def snapshot(self):
    return (
      list(User.objects.order_by('pk').values()),
      list(CustomUser.objects.order_by('pk').values()),
      list(LogEntry.objects.order_by('pk').values()),
      list(ContractAcceptance.objects.order_by('pk').values()),
    )

  def promote(self, **overrides):
    data = {'email': self.target.email, 'confirm': 'on'}
    data.update(overrides)
    return self.client.post(self.url, data)

  def test_admin_login_and_existing_session_use_platform_panel(self):
    self.assertEqual(str(login_redirect_url(self.operator)), self.url)
    self.assertRedirects(self.client.get(reverse('dashboard:login')), self.url)
    self.assertRedirects(self.client.get(reverse('dashboard:dashboard')), self.url)
    self.client.logout()
    response = self.client.post(reverse('dashboard:login'), {'username': self.operator.username, 'password': 'secret'})
    self.assertRedirects(response, self.url)

  def test_panel_needs_no_commerce_or_contract_and_does_not_write(self):
    before = self.snapshot()
    response = self.client.get(self.url)
    self.assertContains(response, 'Administración de PagoLink')
    self.assertContains(response, 'Otorgar rol administrativo')
    self.assertContains(response, 'name="csrfmiddlewaretoken"')
    self.assertNotContains(response, 'Generar Nuevo Link')
    self.assertNotContains(response, 'Mis Retiros')
    self.assertNotContains(response, 'Contrato Legal')
    self.assertEqual(self.snapshot(), before)

  def test_confirmed_promotion_changes_only_app_role_and_records_actor(self):
    before_user = User.objects.values().get(pk=self.target.pk)
    before_profile = CustomUser.objects.values().get(pk=self.target_profile.pk)
    user_count = User.objects.count()
    response = self.promote(is_staff='on', is_superuser='on')
    self.assertRedirects(response, self.url, fetch_redirect_response=False)
    self.assertContains(self.client.get(self.url), 'El usuario ahora es administrador de la plataforma.')
    self.assertEqual(User.objects.values().get(pk=self.target.pk), before_user)
    before_profile['is_admin_role'] = True
    self.assertEqual(CustomUser.objects.values().get(pk=self.target_profile.pk), before_profile)
    self.assertEqual(User.objects.count(), user_count)
    self.assertEqual(ContractAcceptance.objects.count(), 0)
    entry = LogEntry.objects.get()
    self.assertEqual(entry.user.pk, self.operator.pk)
    self.assertEqual(entry.object_id, str(self.target_profile.pk))
    self.assertEqual(entry.action_flag, CHANGE)
    self.assertIn('is_admin_role', entry.change_message)

  def test_promoted_admin_can_promote_another_existing_user(self):
    self.promote()
    other = User.objects.create_user('other', email='other@example.com')
    profile = CustomUser.objects.create(user=other, identification=704)
    self.client.force_login(self.target)
    self.assertRedirects(self.promote(email=other.email), self.url)
    profile.refresh_from_db()
    self.assertTrue(profile.is_admin_role)
    last_entry = LogEntry.objects.order_by('pk').last()
    assert last_entry is not None
    self.assertEqual(last_entry.user.pk, self.target.pk)

  def test_repeating_or_self_promotion_does_not_duplicate_audit(self):
    self.assertRedirects(self.promote(), self.url)
    before = self.snapshot()
    self.assertRedirects(self.promote(), self.url)
    self.assertEqual(self.snapshot(), before)
    self.assertRedirects(self.promote(email=self.operator.email), self.url)
    self.assertEqual(self.snapshot(), before)

  def test_anonymous_and_ordinary_users_cannot_access_or_promote(self):
    for user in (None, self.target, self.staff):
      with self.subTest(user=user):
        self.client.logout()
        if user:
          self.client.force_login(user)
        before = self.snapshot()
        for method in (self.client.get, self.client.post):
          response = method(self.url, {'email': self.target.email, 'confirm': 'on'})
          self.assertEqual(response.status_code, 403 if user else 302)
        self.assertEqual(self.snapshot(), before)

  def test_role_cannot_be_injected_through_merchant_profile(self):
    self.client.force_login(self.target)
    before = CustomUser.objects.values().get(pk=self.target_profile.pk)
    self.client.post(reverse('dashboard:user-update'), {'is_admin_role': 'on', 'is_staff': 'on'})
    self.assertEqual(CustomUser.objects.values().get(pk=self.target_profile.pk), before)
    self.target.refresh_from_db()
    self.assertFalse(self.target.is_staff)

  def test_missing_confirmation_invalid_unknown_inactive_and_ambiguous_users_do_not_write(self):
    inactive = User.objects.create_user('inactive', email='inactive@example.com', is_active=False)
    CustomUser.objects.create(user=inactive, identification=705)
    orphan = User.objects.create_user('orphan', email='orphan@example.com')
    duplicate = User.objects.create_user('duplicate', email=self.target.email.upper())
    CustomUser.objects.create(user=duplicate, identification=706)
    for email, confirm in (
      (self.operator.email, ''), ('invalid', 'on'), ('unknown@example.com', 'on'),
      (inactive.email, 'on'), (orphan.email, 'on'), (self.target.email, 'on'),
    ):
      with self.subTest(email=email, confirm=confirm):
        before = self.snapshot()
        response = self.promote(email=email, confirm=confirm)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'role="alert"')
        self.assertEqual(self.snapshot(), before)

  def test_get_and_missing_csrf_never_promote(self):
    before = self.snapshot()
    self.assertEqual(self.client.get(self.url, {'email': self.target.email, 'confirm': 'on'}).status_code, 200)
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(self.operator)
    before = self.snapshot()
    self.assertEqual(csrf_client.post(self.url, {'email': self.target.email, 'confirm': 'on'}).status_code, 403)
    self.assertEqual(self.snapshot(), before)
    response = csrf_client.get(self.url)
    self.assertEqual(response.status_code, 200)
    token = csrf_client.cookies['csrftoken'].value
    response = csrf_client.post(self.url, {'email': self.target.email, 'confirm': 'on', 'csrfmiddlewaretoken': token})
    self.assertRedirects(response, self.url)
    self.target_profile.refresh_from_db()
    self.assertTrue(self.target_profile.is_admin_role)

  def test_audit_failure_rolls_back_role_grant(self):
    before = self.snapshot()
    with (
      patch('django.contrib.admin.models.LogEntry.objects.create', side_effect=RuntimeError('audit unavailable')),
      self.assertRaises(RuntimeError),
    ):
      self.promote()
    self.assertEqual(self.snapshot(), before)

  def test_role_does_not_bypass_merchant_contract_or_unlock_django_admin(self):
    before = self.snapshot()
    self.assertRedirects(self.client.get(reverse('payments:link_create')), reverse('dashboard:contract'))
    response = self.client.get(reverse('admin:index'))
    self.assertEqual(response.status_code, 302)
    self.assertIn('/admin/login/', response['Location'])
    self.assertEqual(self.snapshot(), before)

  def test_staff_and_merchant_login_destinations_remain_unchanged(self):
    self.assertEqual(str(login_redirect_url(self.staff)), reverse('admin:index'))
    self.assertEqual(str(login_redirect_url(self.target)), reverse('dashboard:contract'))
    self.client.force_login(self.target)
    self.assertRedirects(self.client.get(reverse('dashboard:dashboard')), reverse('dashboard:contract'))
    self.assertRedirects(
      self.client.get(reverse('dashboard:login')), reverse('dashboard:dashboard'), fetch_redirect_response=False
    )
