import hashlib
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Contract, ContractAcceptance, CustomUser
from accounts.personalized_contract import personalized_contract
from accounts.services import login_redirect_url
from accounts.test_personalized_contract import populate_declared_profile


class ContractAcceptanceTests(TestCase):
  def setUp(self):
    self.user = User.objects.create_user('seller@example.com', password='secret')
    self.seller = populate_declared_profile(
      CustomUser.objects.create(user=self.user, identification=123, phone='0999999999')
    )
    self.contract = personalized_contract(self.seller)
    self.client.force_login(self.user)
    self.url = reverse('dashboard:contract')
    self.location = patch('dashboard.services.get_location_from_ip', return_value='Quito')
    self.location_mock = self.location.start()
    self.addCleanup(self.location.stop)

  def consent_payload(self, **overrides):
    response = self.client.get(self.url)
    token = response.context['preview_token'] if response.context else ''
    data = {
      'consent': 'accept',
      'version': self.contract.version,
      'text_hash': self.contract.text_hash,
      'preview_token': token,
    }
    data.update(overrides)
    return data

  def assert_rejected(self, data):
    response = self.client.post(self.url, data)
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, 'Debe aceptar explícitamente')
    self.assertContains(response, 'DÉCIMA SEGUNDA.- DISPOSICIONES GENERALES')
    self.assertEqual(Contract.objects.count(), 0)
    self.assertEqual(ContractAcceptance.objects.count(), 0)
    self.location_mock.assert_not_called()

  def test_unbound_legacy_post_is_rejected(self):
    self.assert_rejected({})

  def test_missing_or_nonexplicit_consent(self):
    for value in ('', 'false', 'on', 'true', '1', ' accept '):
      with self.subTest(value=value):
        self.assert_rejected(self.consent_payload(consent=value))

  def test_stale_or_missing_identity_is_rejected(self):
    for data in (
      self.consent_payload(version='old'),
      self.consent_payload(text_hash='0' * 64),
      {'consent': 'accept'},
      self.consent_payload(version=self.contract.version + ' '),
    ):
      with self.subTest(data=data):
        self.assert_rejected(data)

  def test_legacy_row_does_not_unlock_login_or_dashboard(self):
    Contract.objects.create(seller=self.seller, ip='127.0.0.1', city='Legacy')
    self.assertEqual(login_redirect_url(self.user), self.url)
    self.assertRedirects(self.client.get(reverse('dashboard:dashboard')), self.url)
    self.assertEqual(self.client.get(self.url).status_code, 200)

  def test_anonymous_post_cannot_accept(self):
    self.client.logout()
    response = self.client.post(self.url, self.consent_payload())
    self.assertEqual(response.status_code, 302)
    self.assertIn(reverse('dashboard:login'), response['Location'])
    self.assertEqual(Contract.objects.count(), 0)
    self.assertEqual(ContractAcceptance.objects.count(), 0)

  def test_get_displays_bound_identity_and_unchecked_required_checkbox(self):
    response = self.client.get(self.url)
    self.assertContains(response, f'name="version" value="{self.contract.version}"')
    self.assertContains(response, f'name="text_hash" value="{self.contract.text_hash}"')
    self.assertContains(response, 'type="checkbox" name="consent" value="accept" required')
    self.assertNotContains(response, 'checked')
    self.assertEqual(ContractAcceptance.objects.count(), 0)

  def test_acceptance_records_server_snapshot_and_is_idempotent(self):
    legacy = Contract.objects.create(seller=self.seller, ip='127.0.0.2', city='Original')
    old_row = Contract.objects.values().get(pk=legacy.pk)
    before = timezone.now()
    response = self.client.post(self.url, self.consent_payload(text_snapshot='FAKE'), REMOTE_ADDR='127.0.0.3')
    self.assertRedirects(response, reverse('dashboard:dashboard'))
    evidence = ContractAcceptance.objects.get(seller=self.seller)
    self.assertEqual(evidence.version, self.contract.version)
    self.assertEqual(evidence.text_snapshot, self.contract.text)
    self.assertEqual(evidence.text_hash, hashlib.sha256(evidence.text_snapshot.encode('utf-8')).hexdigest())
    self.assertLessEqual(before, evidence.accepted_at)
    self.assertLessEqual(evidence.accepted_at, timezone.now())
    self.assertEqual(evidence.ip, '127.0.0.3')
    self.assertEqual(evidence.city, '')
    saved = ContractAcceptance.objects.values().get(pk=evidence.pk)
    # Even a stale duplicate must leave the original evidence unchanged.
    self.assertRedirects(self.client.post(self.url, {}), reverse('dashboard:dashboard'))
    self.assertEqual(ContractAcceptance.objects.values().get(pk=evidence.pk), saved)
    self.assertEqual(ContractAcceptance.objects.count(), 1)
    self.assertEqual(Contract.objects.values().get(pk=legacy.pk), old_row)
    self.assertEqual(login_redirect_url(self.user), reverse('dashboard:dashboard'))
    self.assertRedirects(self.client.get(self.url), reverse('dashboard:dashboard'))
    self.location_mock.assert_not_called()

  def test_submitted_seller_cannot_accept_for_another_user(self):
    other = User.objects.create_user('other')
    other_seller = CustomUser.objects.create(user=other, identification=456)
    response = self.client.post(self.url, self.consent_payload(seller=other_seller.pk, user=other.pk))
    self.assertEqual(response.status_code, 302)
    self.assertTrue(ContractAcceptance.objects.filter(seller=self.seller).exists())
    self.assertFalse(ContractAcceptance.objects.filter(seller=other_seller).exists())
    self.client.force_login(other)
    self.assertRedirects(self.client.get(reverse('dashboard:dashboard')), self.url)

  def test_csrf_is_required(self):
    client = Client(enforce_csrf_checks=True)
    client.force_login(self.user)
    self.assertEqual(client.post(self.url, self.consent_payload()).status_code, 403)
    self.assertFalse(ContractAcceptance.objects.exists())

  def test_authenticated_user_without_seller_cannot_write(self):
    user = User.objects.create_user('no-seller')
    self.client.force_login(user)
    self.assertRedirects(
      self.client.post(self.url, self.consent_payload()), reverse('dashboard:login'), fetch_redirect_response=False
    )
    self.assertFalse(ContractAcceptance.objects.exists())

  def test_bad_ip_is_optional_and_does_not_block_acceptance(self):
    response = self.client.post(self.url, self.consent_payload(), HTTP_X_FORWARDED_FOR='invalid')
    self.assertEqual(response.status_code, 302)
    self.assertIsNone(ContractAcceptance.objects.get().ip)
    self.location_mock.assert_not_called()

  def test_real_login_consistently_routes_before_and_after_acceptance(self):
    self.client.logout()
    credentials = {'username': self.user.username, 'password': 'secret'}
    response = self.client.post(reverse('dashboard:login'), credentials)
    self.assertRedirects(response, self.url)
    self.client.post(self.url, self.consent_payload())
    self.client.logout()
    response = self.client.post(reverse('dashboard:login'), credentials)
    self.assertRedirects(response, reverse('dashboard:dashboard'))
