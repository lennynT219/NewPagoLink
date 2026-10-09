"""Personalized text and owner/session-bound preview acceptance."""

from hashlib import sha256

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.contract_terms import CONTRACT_PARAGRAPHS, CONTRACT_SHA256, CONTRACT_TEXT, CONTRACT_VERSION
from accounts.contracts import has_current_acceptance
from accounts.models import ContractAcceptance, CustomUser
from accounts.personalized_contract import PREVIEW_SESSION_KEY, PROVIDER_DEFAULTS
from dashboard.test_contract_terms import LegalTextParser


def declared_seller(user, identification=123):
  return CustomUser.objects.create(
    user=user,
    identification=identification,
    phone='0999999999',
    commerce_name='Comercio <Sur> & Asociados',
    commerce_ruc='1791234567001',
    commerce_identification='0101234567',
    legal_representative_name='Representante Declarado',
    commerce_address='Calle Declarada 42, Cuenca',
  )


class PersonalizedRequestTests(TestCase):
  def setUp(self):
    self.user = User.objects.create_user('owner', email='registered@example.invalid')
    self.seller = declared_seller(self.user)
    self.client.force_login(self.user)
    self.url = reverse('dashboard:contract')

  def preview(self, client=None):
    response = (client or self.client).get(self.url)
    parser = LegalTextParser()
    parser.feed(response.content.decode())
    return (
      response,
      '\n\n'.join(parser.paragraphs),
      {
        'consent': 'accept',
        'version': response.context['contract_version'],
        'text_hash': response.context['contract_hash'],
        'preview_token': response.context.get('preview_token', ''),
      },
    )

  def test_declared_party_contacts_complete_body_and_hidden_identity(self):
    response, text, _ = self.preview()
    for value in (
      'Comercio <Sur> & Asociados',
      '1791234567001',
      '0101234567',
      'Representante Declarado',
      'Calle Declarada 42, Cuenca',
      'Correo electrónico: registered@example.invalid',
      'Teléfono: 0999999999',
    ):
      self.assertIn(value, text)
    self.assertContains(response, 'Comercio &lt;Sur&gt; &amp; Asociados')
    self.assertNotIn('[__________]', text)
    self.assertNotContains(response, 'Versión:')
    self.assertNotContains(response, 'SHA-256:')
    paragraphs = text.split('\n\n')
    self.assertEqual(len(paragraphs), 173)
    for index, original in enumerate(CONTRACT_PARAGRAPHS):
      if index != 1 and original not in ('Correo electrónico:', 'Teléfono:', 'Dirección domicilio'):
        self.assertEqual(paragraphs[index], original)

  def test_get_text_is_exact_stored_snapshot_and_profile_edit_preserves_access(self):
    _, text, data = self.preview()
    self.assertEqual(self.client.post(self.url, dict(data, text_snapshot='forged', seller=999)).status_code, 302)
    evidence = ContractAcceptance.objects.get()
    self.assertEqual(evidence.text_snapshot, text)
    self.assertEqual(evidence.text_hash, sha256(text.encode()).hexdigest())
    self.assertNotEqual(evidence.version, CONTRACT_VERSION)
    saved = ContractAcceptance.objects.values().get()
    self.seller.commerce_name = 'Changed after acceptance'
    self.seller.save()
    self.assertTrue(has_current_acceptance(self.seller))
    self.assertEqual(self.client.post(self.url, data).status_code, 302)
    self.assertEqual(ContractAcceptance.objects.values().get(), saved)

  def test_profile_change_rejects_unseen_text_and_displays_fresh_preview(self):
    _, _, data = self.preview()
    self.seller.commerce_name = 'Nueva Declaración'
    self.seller.save()
    response = self.client.post(self.url, data)
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, 'Nueva Declaración')
    self.assertFalse(ContractAcceptance.objects.exists())

  def test_missing_forged_cross_user_and_cross_session_previews_rejected(self):
    for token in ('', 'forged', 'ñ' * 43, 'x' * 1000):
      _, _, data = self.preview()
      self.assertEqual(self.client.post(self.url, dict(data, preview_token=token)).status_code, 200)
      self.assertFalse(ContractAcceptance.objects.exists())
    _, _, data = self.preview()
    other_client = Client()
    other_client.force_login(self.user)
    self.assertEqual(other_client.post(self.url, data).status_code, 200)
    other = User.objects.create_user('other', email='other@example.invalid')
    declared_seller(other, 456)
    _, _, data = self.preview()
    self.client.force_login(other)
    self.assertEqual(self.client.post(self.url, data).status_code, 200)
    self.assertFalse(ContractAcceptance.objects.exists())

  def test_version_hash_and_notification_changes_reject_fresh_bound_forms(self):
    for field, value in (('version', 'old'), ('text_hash', '0' * 64)):
      _, _, data = self.preview()
      self.assertEqual(self.client.post(self.url, dict(data, **{field: value})).status_code, 200)
      self.assertFalse(ContractAcceptance.objects.exists())
    _, _, data = self.preview()
    self.seller.phone = '0888888888'
    self.seller.save()
    response = self.client.post(self.url, data)
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, 'Teléfono: 0888888888')
    _, _, data = self.preview()
    self.user.email = 'changed@example.invalid'
    self.user.save()
    response = self.client.post(self.url, data)
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, 'Correo electrónico: changed@example.invalid')
    self.assertFalse(ContractAcceptance.objects.exists())

  def test_expired_replaced_and_corrupted_server_draft_rejected(self):
    _, _, data = self.preview()
    self.preview()  # A second tab replaces the single bounded preview.
    self.assertEqual(self.client.post(self.url, data).status_code, 200)
    for change in ({'issued': 0}, {'text': 'altered'}, {'seller': 999}, {'user': 999}):
      _, _, data = self.preview()
      session = self.client.session
      session[PREVIEW_SESSION_KEY] = dict(session[PREVIEW_SESSION_KEY], **change)
      session.save()
      self.assertEqual(self.client.post(self.url, data).status_code, 200)
      self.assertFalse(ContractAcceptance.objects.exists())

  def test_provider_revision_rejects_stale_form_and_uses_all_configured_values(self):
    _, _, data = self.preview()
    provider = {
      'name': 'Proveedor Configurado',
      'ruc': '1797654321001',
      'city': 'CUENCA',
      'representative': 'Representante Configurada',
      'role': 'Presidenta',
    }
    with override_settings(PAGOLINK_CONTRACT_PROVIDER=provider):
      response = self.client.post(self.url, data)
      self.assertEqual(response.status_code, 200)
      self.assertFalse(ContractAcceptance.objects.exists())
      for value in provider.values():
        self.assertContains(response, value)
      for value in PROVIDER_DEFAULTS.values():
        self.assertNotContains(response, value)
      _, text, fresh = self.preview()
      self.assertEqual(self.client.post(self.url, fresh).status_code, 302)
      self.assertEqual(ContractAcceptance.objects.get().text_snapshot, text)

  def test_template_revision_rejects_stale_form(self):
    from unittest.mock import patch

    _, _, data = self.preview()
    with patch('accounts.personalized_contract.CONTRACT_SHA256', '0' * 64):
      response = self.client.post(self.url, data)
      self.assertEqual(response.status_code, 200)
      self.assertNotEqual(response.context['contract_version'], data['version'])
      self.assertFalse(ContractAcceptance.objects.exists())

  def test_invalid_provider_does_not_expose_configuration_or_prepare_preview(self):
    with override_settings(PAGOLINK_CONTRACT_PROVIDER={'token': 'must-not-leak'}):
      for response in (self.client.get(self.url), self.client.post(self.url, {'consent': 'accept'})):
        self.assertContains(response, 'El contrato no está disponible')
        self.assertNotContains(response, 'must-not-leak')
        self.assertNotContains(response, 'name="preview_token"')
      self.assertFalse(ContractAcceptance.objects.exists())

  def test_missing_registered_contacts_explains_completion_without_fabrication(self):
    self.seller.phone = ''
    self.seller.save()
    self.user.email = ''
    self.user.save()
    response = self.client.get(self.url)
    self.assertContains(response, 'Teléfono registrado de contacto')
    self.assertContains(response, 'solicitá su actualización al administrador')
    self.assertNotContains(response, 'name="preview_token"')

  def test_csrf_protected_preview_can_accept_only_with_csrf_token(self):
    client = Client(enforce_csrf_checks=True)
    client.force_login(self.user)
    _, _, data = self.preview(client)
    self.assertEqual(client.post(self.url, data).status_code, 403)
    data['csrfmiddlewaretoken'] = client.cookies['csrftoken'].value
    self.assertEqual(client.post(self.url, data).status_code, 302)
    self.assertEqual(ContractAcceptance.objects.count(), 1)

  def test_missing_profile_cannot_accept_and_can_reach_owner_profile(self):
    self.seller.commerce_ruc = ''
    self.seller.save()
    response = self.client.get(self.url)
    self.assertContains(response, reverse('dashboard:user-update'))
    self.assertNotContains(response, 'name="preview_token"')
    self.assertEqual(self.client.post(self.url, {'consent': 'accept'}).status_code, 200)
    self.assertFalse(ContractAcceptance.objects.exists())
    self.assertEqual(self.client.get(reverse('dashboard:user-update')).status_code, 200)

  def test_old_static_evidence_is_not_relabelled_or_accepted(self):
    row = ContractAcceptance.objects.create(
      seller=self.seller, version=CONTRACT_VERSION, text_snapshot=CONTRACT_TEXT, text_hash=CONTRACT_SHA256
    )
    old = ContractAcceptance.objects.values().get(pk=row.pk)
    self.assertFalse(has_current_acceptance(self.seller))
    _, _, data = self.preview()
    self.assertEqual(self.client.post(self.url, data).status_code, 302)
    self.assertEqual(ContractAcceptance.objects.values().get(pk=row.pk), old)
    self.assertEqual(ContractAcceptance.objects.count(), 2)
