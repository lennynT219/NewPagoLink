from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.db import DataError, IntegrityError
from django.test import Client, TransactionTestCase, override_settings
from django.urls import resolve, reverse
from django.utils.http import urlsafe_base64_decode

from accounts.models import CustomUser
from accounts.services import create_user
from accounts.tokens import account_activation_token


@override_settings(ALLOWED_HOSTS=['testserver', 'pagolinks.com'])
class RegistrationIntegrityTests(TransactionTestCase):
  duplicate_message = 'Esta identificación ya está registrada.'
  persistence_message = 'No se pudo completar el registro con estos datos. Revisalos e intentá nuevamente.'

  def setUp(self):
    self.client = Client(raise_request_exception=False)
    self.data = {
      'firstname': 'Synthetic', 'lastname': 'Fixture', 'identification': '1234567890',
      'phone': '0999999999', 'email': 'new@example.com', 'password': 'synthetic-only',
    }

  def snapshot(self):
    return list(User.objects.order_by('pk').values()), list(CustomUser.objects.order_by('pk').values())

  def post(self, data=None):
    return self.client.post(reverse('dashboard:register'), data or self.data, secure=True, HTTP_HOST='pagolinks.com')

  def assert_rejected(self, data, field, message):
    before = self.snapshot()
    mail_count = len(mail.outbox)
    response = self.post(data)
    self.assertEqual(response.status_code, 200)
    self.assertEqual(dict(response.context['register_form'].errors), {field: [message]})
    self.assertContains(response, message)
    self.assertEqual(response.context['active_tab'], 'register')
    self.assertEqual(self.snapshot(), before)
    self.assertEqual(len(mail.outbox), mail_count)
    self.assertNotContains(response, self.data['password'])
    self.assertNotContains(response, 'UNIQUE constraint failed')
    self.assertNotContains(response, 'synthetic storage rejection')

  def existing_profile(self):
    user = User.objects.create_user('existing@example.com')
    return CustomUser.objects.create(user=user, identification=int(self.data['identification']), phone='0999999999')

  def test_duplicate_identification_is_a_field_error_without_partial_user_or_mail(self):
    self.existing_profile()
    self.assert_rejected(self.data, 'identification', self.duplicate_message)

  def test_existing_email_without_profile_is_not_silently_repaired(self):
    User.objects.create_user(self.data['email'], email=self.data['email'], is_active=False)
    self.assert_rejected(self.data, 'email', 'Este correo ya está en uso.')

  def test_phone_storage_limit_is_checked_before_persistence(self):
    self.assert_rejected(
      dict(self.data, phone='12345678901'), 'phone', 'El celular admite como máximo 10 caracteres.',
    )

  def test_identification_storage_bounds_are_form_errors(self):
    for index, number in enumerate((2**63, -(2**63) - 1)):
      with self.subTest(number=number):
        self.assert_rejected(
          dict(self.data, identification=str(number), email=f'overflow-{index}@example.com'), 'identification',
          'La identificación está fuera del rango permitido.',
        )

  def test_auth_name_and_username_storage_limits_are_checked(self):
    email = 'a' * 64 + '@' + 'b' * 60 + '.' + 'c' * 25
    self.assertEqual(len(email), 151)
    for index, (field, value) in enumerate((('firstname', 'N' * 151), ('lastname', 'L' * 151), ('email', email))):
      with self.subTest(field=field):
        data = dict(self.data, identification=str(1234567800 + index), email=f'storage-{index}@example.com')
        data[field] = value
        self.assert_rejected(data, field, 'Este campo admite como máximo 150 caracteres.')

  def test_profile_unique_conflict_after_form_validation_rolls_back_and_is_reported(self):
    self.existing_profile()
    # Reproduce a uniqueness check losing a race to another committed registration.
    with patch('dashboard.forms.RegisterForm.clean_identification', lambda form: form.cleaned_data['identification'], create=True):
      self.assert_rejected(self.data, '__all__', self.persistence_message)

  def test_username_conflict_at_insert_does_not_create_rows_or_send_mail(self):
    User.objects.create_user(self.data['email'], email='different@example.com')
    self.assert_rejected(self.data, '__all__', self.persistence_message)

  def test_profile_storage_error_rolls_back_and_does_not_expose_database_details(self):
    with patch('accounts.services.CustomUser.objects.create', side_effect=DataError('synthetic storage rejection')):
      self.assert_rejected(self.data, '__all__', self.persistence_message)

  def test_public_creation_service_rolls_back_user_when_profile_insert_fails(self):
    self.existing_profile()
    before = self.snapshot()
    with self.assertRaises(IntegrityError):
      create_user(self.data)
    self.assertEqual(self.snapshot(), before)
    self.assertEqual(len(mail.outbox), 0)

  def test_valid_registration_still_creates_inactive_user_profile_and_one_secure_email(self):
    response = self.post()
    self.assertRedirects(response, reverse('dashboard:login'))
    self.assertEqual(User.objects.count(), 1)
    self.assertEqual(CustomUser.objects.count(), 1)
    user = User.objects.get(email=self.data['email'])
    profile = CustomUser.objects.get(user=user)
    self.assertFalse(user.is_active)
    self.assertFalse(user.is_staff)
    self.assertFalse(user.is_superuser)
    self.assertTrue(user.check_password(self.data['password']))
    self.assertFalse(profile.email_active)
    self.assertFalse(profile.is_admin_role)
    self.assertEqual(profile.identification, int(self.data['identification']))
    # Keep the submitted contact text, including the leading zero needed by the contract.
    self.assertEqual(profile.phone, self.data['phone'])
    self.assertEqual(len(mail.outbox), 1)
    message = mail.outbox[0]
    assert isinstance(message.body, str)
    self.assertEqual(message.to, [self.data['email']])
    self.assertEqual(message.subject, 'Active su cuenta de PagoLink')
    self.assertIn('https://pagolinks.com/dashboard/activar/', message.body)
    self.assertNotIn('http://pagolinks.com', message.body)
    import re
    from urllib.parse import urlsplit
    match = re.search(r'https://pagolinks\.com/dashboard/activar/[^\s<]+', message.body)
    assert match is not None
    route = resolve(urlsplit(match.group(0)).path)
    self.assertEqual(urlsafe_base64_decode(route.kwargs['uidb64']).decode(), str(user.pk))
    self.assertTrue(account_activation_token.check_token(user, route.kwargs['token']))

  def test_supported_storage_boundaries_remain_accepted(self):
    email = 'a' * 64 + '@' + 'b' * 60 + '.' + 'c' * 24
    self.assertEqual(len(email), 150)
    for index, identification in enumerate((-(2**63), 2**63 - 1), start=1):
      data = dict(self.data, firstname='N' * 150, lastname='L' * 150, phone='9999999999',
                  identification=str(identification), email=email if index == 1 else 'boundary@example.com')
      with self.subTest(identification=identification):
        self.assertRedirects(self.post(data), reverse('dashboard:login'))
        self.assertEqual(User.objects.count(), index)
        self.assertEqual(CustomUser.objects.count(), index)
        self.assertEqual(len(mail.outbox), index)
        profile = CustomUser.objects.get(user__email=data['email'])
        self.assertEqual(profile.identification, identification)
        self.assertEqual(profile.phone, data['phone'])
        self.assertFalse(profile.user.is_active)
        self.assertFalse(profile.is_admin_role)
