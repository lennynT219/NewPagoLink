from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.test import Client, TestCase

from accounts.models import CustomUser


class PlatformUserDirectoryTests(TestCase):
  home = '/dashboard/administracion/'
  url = '/dashboard/administracion/usuarios/'

  @classmethod
  def setUpTestData(cls):
    cls.admin = User.objects.create_user('admin-ui', email='admin@example.com')
    CustomUser.objects.create(user=cls.admin, identification=801, is_admin_role=True)
    cls.target = User.objects.create_user('seller-ui', email='seller@example.com', first_name='María', last_name='Paz')
    CustomUser.objects.create(user=cls.target, identification=802)
    cls.inactive = User.objects.create_user('inactive-ui', email='inactive@example.com', is_active=False)
    CustomUser.objects.create(user=cls.inactive, identification=803)
    cls.orphan = User.objects.create_user('orphan-ui', email='orphan@example.com')

  def setUp(self):
    self.client.force_login(self.admin)

  def snapshot(self):
    return list(User.objects.order_by('pk').values()), list(CustomUser.objects.order_by('pk').values()), list(LogEntry.objects.values())

  def test_home_is_an_overview_not_the_user_management_screen(self):
    before = self.snapshot()
    response = self.client.get(self.home)
    self.assertContains(response, 'Centro de administración')
    self.assertContains(response, f'href="{self.url}"')
    self.assertNotContains(response, 'name="email"')
    self.assertNotContains(response, 'Hacer administrador')
    self.assertEqual(self.snapshot(), before)

  def test_directory_uses_application_table_and_explicit_users_sidebar(self):
    before = self.snapshot()
    response = self.client.get(self.url)
    self.assertContains(response, '<title>PagoLink | Usuarios</title>', html=True)
    self.assertContains(response, 'class="table-modern"')
    self.assertContains(response, 'María Paz')
    self.assertContains(response, self.target.email)
    self.assertContains(response, 'Hacer administrador')
    self.assertContains(response, 'aria-current="page"')
    self.assertContains(response, 'Buscar usuarios')
    self.assertContains(response, 'Administrador')
    self.assertEqual(response.context['summary'], {'total': 4, 'active': 3, 'admins': 1})
    self.assertEqual(self.snapshot(), before)

  def test_only_eligible_rows_offer_a_confirmed_role_grant(self):
    body = self.client.get(self.url).content.decode()
    for user, eligible in ((self.target, True), (self.admin, False), (self.inactive, False), (self.orphan, False)):
      with self.subTest(user=user.pk):
        row = body.split(f'<tr id="user-{user.pk}">')[1].split('</tr>')[0]
        self.assertEqual('method="post"' in row, eligible)
        if eligible:
          self.assertIn(f'value="{user.email}"', row)
          self.assertIn('name="confirm"', row)
          self.assertIn('name="csrfmiddlewaretoken"', row)

  def test_search_pagination_and_empty_state_are_read_only(self):
    User.objects.bulk_create([
      User(username=f'list-{i}', email=f'list-{i}@example.com', first_name=f'List Example {i}') for i in range(25)
    ])
    before = self.snapshot()
    response = self.client.get(self.url, {'q': 'List Example', 'page': 2})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.context['page_obj'].paginator.count, 25)
    self.assertEqual(len(response.context['page_obj']), 5)
    self.assertContains(response, 'q=List%20Example')
    self.assertNotContains(response, self.target.email)
    empty = self.client.get(self.url, {'q': 'no-such-user'})
    self.assertContains(empty, 'No encontramos usuarios')
    self.assertEqual(self.snapshot(), before)

  def test_row_action_requires_csrf_and_changes_only_the_selected_app_role(self):
    client = Client(enforce_csrf_checks=True)
    client.force_login(self.admin)
    before = self.snapshot()
    self.assertEqual(client.post(self.url, {'email': self.target.email, 'user_id': self.target.pk, 'confirm': 'on'}).status_code, 403)
    self.assertEqual(self.snapshot(), before)
    self.assertEqual(client.get(self.url).status_code, 200)
    token = client.cookies['csrftoken'].value
    response = client.post(self.url, {'email': self.target.email, 'user_id': self.target.pk, 'confirm': 'on', 'csrfmiddlewaretoken': token})
    self.assertRedirects(response, self.url)
    expected_users, expected_profiles, _ = before
    for profile in expected_profiles:
      if profile['user_id'] == self.target.pk:
        profile['is_admin_role'] = True
    self.assertEqual(list(User.objects.order_by('pk').values()), expected_users)
    self.assertEqual(list(CustomUser.objects.order_by('pk').values()), expected_profiles)
    entry = LogEntry.objects.get()
    self.assertEqual(entry.user.pk, self.admin.pk)
    self.assertEqual(entry.object_id, str(self.target.customuser.pk))
    self.assertEqual(self.client.get(self.home).context['summary'], {'total': 4, 'active': 3, 'admins': 2})

  def test_directory_and_actions_remain_private_to_app_administrators(self):
    staff = User.objects.create_user('technical-ui', is_staff=True)
    CustomUser.objects.create(user=staff, identification=805)
    for user in (None, self.target, staff):
      self.client.logout()
      if user:
        self.client.force_login(user)
      before = self.snapshot()
      for method in (self.client.get, self.client.post):
        response = method(self.url, {'email': self.target.email, 'confirm': 'on'})
        self.assertEqual(response.status_code, 403 if user else 302)
        self.assertNotContains(response, self.target.email, status_code=403 if user else 302)
      self.assertEqual(self.snapshot(), before)

  def test_invalid_row_action_does_not_write_and_reports_error(self):
    for data in (
      {'email': self.target.email, 'user_id': self.target.pk},
      {'email': self.inactive.email, 'user_id': self.inactive.pk, 'confirm': 'on'},
    ):
      before = self.snapshot()
      response = self.client.post(self.url, data)
      self.assertContains(response, 'role="alert"')
      self.assertEqual(self.snapshot(), before)

  def test_row_identity_mismatch_is_rejected_without_granting_another_account(self):
    other = User.objects.create_user('other-row', email='other-row@example.com')
    CustomUser.objects.create(user=other, identification=804)
    before = self.snapshot()
    response = self.client.post(self.url, {'email': other.email, 'user_id': self.target.pk, 'confirm': 'on'})
    self.assertContains(response, 'role="alert"')
    self.assertEqual(list(response.context['form'].errors['email']), [
      'La cuenta seleccionada cambió. Actualizá el listado e intentá de nuevo.',
    ])
    self.assertEqual(self.snapshot(), before)

  def test_untrusted_display_names_are_escaped(self):
    self.target.first_name = '<script>alert(1)</script>'
    self.target.save(update_fields=['first_name'])
    response = self.client.get(self.url)
    self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
    self.assertNotContains(response, '<script>alert(1)</script>')
