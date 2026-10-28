"""Boundary and immutable-evidence regressions from independent onboarding verification."""

from hashlib import sha256

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import ContractAcceptance, CustomUser
from dashboard import test_onboarding_phone as fixtures


@override_settings(
  ALLOWED_HOSTS=['testserver'],
  EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
  PAGOLINK_CONTRACT_PROVIDER=fixtures.PROVIDER_DEFAULTS,
)
class OnboardingBoundaryTests(TestCase):
  user: User
  profile: CustomUser
  registration_data: dict[str, str]

  setUp = fixtures.OnboardingPhoneTests.setUp
  snapshot = fixtures.OnboardingPhoneTests.snapshot
  payload = fixtures.OnboardingPhoneTests.payload

  def test_rejected_phone_boundaries(self):
    cases = [('', 'This field is required.')]
    cases += [(value, fixtures.PHONE_ERROR) for value in (
      '0', '099999999', '09999999a9', '０９９９９９９９９９', '+999999999', '-999999999', '09 9999999',
    )]
    for route in ('register', 'user-update'):
      if route == 'user-update':
        self.client.force_login(self.user)
      long_error = (
        'El celular admite como máximo 10 caracteres.' if route == 'register'
        else 'Ensure this value has at most 10 characters (it has 11).'
      )
      for phone, error in cases + [('00000000000', long_error)]:
        with self.subTest(route=route, phone=phone):
          before = self.snapshot()
          data = (
            dict(self.registration_data, phone=phone) if route == 'register'
            else dict(self.payload(phone), firstname='Must not persist')
          )
          response = self.client.post(reverse('dashboard:' + route), data)
          self.assertEqual(response.status_code, 200)
          form = response.context['register_form' if route == 'register' else 'form']
          self.assertEqual(dict(form.errors), {'phone': [error]})
          self.assertNotContains(response, 'Tus datos han sido actualizados correctamente.')
          self.assertFalse(response.wsgi_request.session.get('contract_preview'))
          self.assertEqual(self.snapshot(), before)

  def test_zero_and_text_registration_boundaries(self):
    for index, phone in enumerate(('0000000000', '0999999999', '9999999999')):
      data = dict(
        self.registration_data, phone=phone, email=f'b{index}@example.invalid',
        identification=str(1000000000 + index),
      )
      self.assertEqual(self.client.post(reverse('dashboard:register'), data).status_code, 302)
      seller = CustomUser.objects.get(user__email=data['email'])
      self.assertEqual(seller.phone, phone)
      self.assertFalse(
        seller.user.is_active or seller.user.is_staff or seller.user.is_superuser
        or seller.email_active or seller.is_admin_role
      )
    self.assertFalse(ContractAcceptance.objects.exists())
    self.assertEqual(self.snapshot()[-1], 3)

  def test_correction_keeps_frozen_evidence_and_readonly_identity(self):
    evidence = ContractAcceptance.objects.create(
      seller=self.profile, version='historic', text_snapshot='Frozen synthetic evidence',
      text_hash=sha256(b'Frozen synthetic evidence').hexdigest(),
    )
    before = ContractAcceptance.objects.values().get(pk=evidence.pk)
    self.client.force_login(self.user)
    blocked = self.client.get(reverse('dashboard:contract'))
    self.assertEqual(blocked.context['profile_error'], fixtures.CONTRACT_ERROR)
    response = self.client.post(
      reverse('dashboard:user-update'),
      dict(self.payload('0999999999'), email='ignored@example.invalid', identification=2000000001),
      follow=True,
    )
    self.assertEqual(response.status_code, 200)
    self.assertTrue(response.context['contract_blocks'])
    self.assertTrue(response.context['preview_token'])
    self.profile.refresh_from_db()
    self.user.refresh_from_db()
    self.assertEqual(self.profile.phone, '0999999999')
    self.assertEqual(self.user.email, 'legacy@example.invalid')
    self.assertEqual(self.profile.identification, 2000000000)
    self.assertEqual(ContractAcceptance.objects.values().get(pk=evidence.pk), before)
    self.assertEqual(ContractAcceptance.objects.count(), 1)
    self.assertEqual(self.snapshot()[-1], 0)
