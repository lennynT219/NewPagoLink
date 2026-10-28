"""Public onboarding round trips with synthetic accounts and declared merchant data."""

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import ContractAcceptance, CustomUser
from accounts.personalized_contract import PROVIDER_DEFAULTS

LEGAL_DATA = {
  'commerce_name': 'Comercio de Prueba S.A.',
  'commerce_ruc': '1799999999001',
  'commerce_address': 'Calle de Prueba 123, Quito',
  'legal_representative_name': 'Representante de Prueba',
  'commerce_identification': '1234567890',
}
PHONE_ERROR = 'Ingresá un teléfono de 10 dígitos.'
CONTRACT_ERROR = 'Completá o corregí tu perfil antes de aceptar: Teléfono registrado de contacto.'


@override_settings(
  ALLOWED_HOSTS=['testserver', 'pagolinks.com'],
  EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
  PAGOLINK_CONTRACT_PROVIDER=PROVIDER_DEFAULTS,
)
class OnboardingPhoneTests(TestCase):
  def setUp(self):
    self.user = User.objects.create_user(
      'legacy',
      email='legacy@example.invalid',
      first_name='Synthetic',
      last_name='Merchant',
      password='synthetic-password',
    )
    self.profile = CustomUser.objects.create(user=self.user, identification=2000000000, phone='999999999', **LEGAL_DATA)
    self.registration_data = {
      'firstname': 'Synthetic',
      'lastname': 'New Merchant',
      'email': 'signup@example.invalid',
      'identification': '1234567890',
      'phone': '0999999999',
      'password': 'synthetic-password',
    }

  def snapshot(self):
    return (
      list(User.objects.order_by('pk').values()),
      list(CustomUser.objects.order_by('pk').values()),
      list(ContractAcceptance.objects.order_by('pk').values()),
      len(mail.outbox),
    )

  def payload(self, phone):
    return {
      'firstname': self.user.first_name,
      'lastname': self.user.last_name,
      'email': self.user.email,
      'identification': str(self.profile.identification),
      'phone': phone,
      **LEGAL_DATA,
    }

  def assert_preview(self, response):
    self.assertEqual(response.status_code, 200)
    self.assertNotIn(CONTRACT_ERROR, response.content.decode())
    self.assertTrue(bool(response.context.get('contract_blocks')), 'Contract text was not rendered')
    self.assertTrue(bool(response.context.get('preview_token')), 'Contract preview token missing')
    self.assertEqual(ContractAcceptance.objects.count(), 0)

  def test_registration_preserves_zero_before_profile_and_contract(self):
    data = self.registration_data
    response = self.client.post(reverse('dashboard:register'), data, secure=True, HTTP_HOST='pagolinks.com')
    self.assertEqual(response.status_code, 302)
    user = User.objects.get(email=data['email'])
    profile = CustomUser.objects.get(user=user)
    self.assertEqual(profile.phone, data['phone'])
    self.assertFalse(user.is_active or user.is_staff or user.is_superuser or profile.is_admin_role)
    self.assertEqual(len(mail.outbox), 1)
    # Test-only activation, never a production recovery or an implicit application action.
    user.is_active = True
    user.save(update_fields=['is_active'])
    self.client.force_login(user)
    response = self.client.post(
      reverse('dashboard:user-update'),
      {
        'firstname': data['firstname'],
        'lastname': data['lastname'],
        'email': user.email,
        'identification': data['identification'],
        'phone': data['phone'],
        **LEGAL_DATA,
      },
      follow=True,
    )
    self.assert_preview(response)
    profile.refresh_from_db()
    self.assertEqual(profile.phone, data['phone'])
    self.assertEqual(len(mail.outbox), 1)

  def test_invalid_registration_contact_leaves_rows_and_mail_unchanged(self):
    before = self.snapshot()
    for phone in ('999999999', '09abc54321'):
      with self.subTest(phone=phone):
        response = self.client.post(reverse('dashboard:register'), dict(self.registration_data, phone=phone))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['register_form'].errors['phone']), [PHONE_ERROR])
        self.assertContains(response, PHONE_ERROR)
        self.assertTrue(self.snapshot() == before, 'Rejected signup changed stored rows or mail')

  def test_invalid_phone_cannot_report_a_successful_profile_save(self):
    self.client.force_login(self.user)
    before = self.snapshot()
    contract = self.client.get(reverse('dashboard:contract'))
    self.assertContains(contract, CONTRACT_ERROR)
    self.assertFalse(contract.context.get('contract_blocks'))
    self.assertEqual(self.snapshot(), before)
    profile = self.client.get(reverse('dashboard:user-update'))
    self.assertContains(profile, 'value="999999999"')
    for phone in ('999999999', '09abc54321'):
      with self.subTest(phone=phone):
        response = self.client.post(reverse('dashboard:user-update'), self.payload(phone))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['form'].errors['phone']), [PHONE_ERROR])
        self.assertContains(response, PHONE_ERROR)
        self.assertNotContains(response, 'Tus datos han sido actualizados correctamente.')
        self.assertTrue(self.client.session.get('contract_preview') is None, 'Invalid profile prepared a preview')
        self.assertTrue(self.snapshot() == before, 'Rejected contact data changed stored rows or mail')
        self.assertFalse(ContractAcceptance.objects.exists())

  def test_owner_can_correct_legacy_phone_and_preview_without_accepting(self):
    self.client.force_login(self.user)
    response = self.client.post(reverse('dashboard:user-update'), self.payload('0999999999'), follow=True)
    self.assert_preview(response)
    self.profile.refresh_from_db()
    self.user.refresh_from_db()
    self.assertEqual(self.profile.phone, '0999999999')
    self.assertEqual({name: getattr(self.profile, name) for name in LEGAL_DATA}, LEGAL_DATA)
    self.assertFalse(self.profile.is_admin_role or self.user.is_staff or self.user.is_superuser)
    self.assertEqual(self.user.email, 'legacy@example.invalid')
    self.assertEqual(self.profile.identification, 2000000000)
    self.assertEqual(len(mail.outbox), 0)
