"""Complete legal-copy publication, independent of acceptance persistence."""

import json
from dataclasses import replace
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import RequestFactory, SimpleTestCase
from django.utils.html import escape

from accounts import contract_terms
from accounts.models import CustomUser
from accounts.personalized_contract import personalized_contract
from dashboard.views import ContractAccept

AFFILIATION = 'a) Valor por afiliación o activación: USD 25 anuales, pagaderos al momento de la activación y en cada renovación anual.'
COMMISSION = 'b) Comisión por transacción procesada: USD 0,35.'


def approved_source():
  """Load frozen public copy, not a new legal approval or private DOCX check.

  The snapshot originated only from existing accounts/contract_terms.py.
  Never regenerate it during tests: the independent frozen hash below must
  continue to detect changes to either the fixture or the runtime legal copy.
  """
  fixture = Path(__file__).parent / 'test_fixtures' / 'approved_contract.json'
  return tuple(json.loads(fixture.read_text(encoding='utf-8'))['paragraphs'])


class LegalTextParser(HTMLParser):
  def __init__(self):
    super().__init__()
    self.active = False
    self.tag = None
    self.parts = []
    self.paragraphs = []
    self.headings = []

  def handle_starttag(self, tag, attrs):
    if tag == 'article' and dict(attrs).get('id') == 'contract-terms':
      self.active = True
    if self.active and tag in ('h2', 'h3', 'h4', 'p'):
      self.tag = tag
      self.parts = []

  def handle_data(self, data):
    if self.active and self.tag:
      self.parts.append(data)

  def handle_endtag(self, tag):
    if self.active and tag == self.tag:
      text = ''.join(self.parts)
      self.paragraphs.append(text)
      if tag == 'h3':
        self.headings.append(text)
      self.tag = None
    if tag == 'article':
      self.active = False


class ContractRenderingTests(SimpleTestCase):
  def render_contract(self):
    request: Any = RequestFactory().get('/contract/')
    request.user = User(username='test-commerce', email='registered@example.invalid')
    seller = CustomUser(
      user=request.user,
      phone='0999999999',
      identification=123,
      commerce_name='Comercio de Prueba',
      commerce_ruc='1791234567001',
      commerce_identification='0101234567',
      legal_representative_name='Representante de Prueba',
      commerce_address='Calle de Prueba, Cuenca',
    )
    request.session = {}
    return ContractAccept().render_terms(request, seller).content.decode()

  def test_copy_is_autoescaped_in_every_block_kind(self):
    payload = '<script>alert("legal")</script> & texto'
    for kind in ('title', 'section', 'subsection', 'paragraph'):
      original = personalized_contract

      def escaped_contract(seller, renderer=original, block_kind=kind):
        return replace(renderer(seller), blocks=((block_kind, payload),))

      with self.subTest(kind=kind), patch('dashboard.views.personalized_contract', side_effect=escaped_contract):
        html = self.render_contract()
        self.assertIn(escape(payload), html)
        self.assertNotIn(payload, html)

  def test_scrolling_region_is_keyboard_accessible(self):
    html = self.render_contract()
    self.assertIn('aria-labelledby="contract-title" tabindex="0"', html)
    self.assertIn('id="contract-title"', html)

  def test_complete_approved_source_is_rendered_in_order(self):
    parser = LegalTextParser()
    parser.feed(self.render_contract())
    self.assertEqual(len(parser.paragraphs), len(approved_source()))
    for index, source in enumerate(approved_source()):
      if index != 1 and source not in ('Correo electrónico:', 'Teléfono:', 'Dirección domicilio'):
        self.assertEqual(parser.paragraphs[index], source)
    self.assertIn('Comercio de Prueba', parser.paragraphs[1])
    self.assertIn('Correo electrónico: registered@example.invalid', parser.paragraphs)

  def test_all_twelve_headings_and_provider_identity(self):
    parser = LegalTextParser()
    html = self.render_contract()
    parser.feed(html)
    expected = tuple(text for text in approved_source() if '.- ' in text and text.split('.- ')[0].isupper())
    self.assertEqual(len(expected), 12)
    self.assertEqual(tuple(parser.headings), expected)
    for identity in (
      'ADREST DEL ECUADOR CÍA. LTDA.',
      '1792901286001',
      'Adriana Zenovia Vásquez Macías',
      'Comercio de Prueba',
      'Representante de Prueba',
    ):
      self.assertIn(identity, html)

  def test_approved_prices_without_previous_tariffs(self):
    html = self.render_contract()
    self.assertIn(AFFILIATION, html)
    self.assertIn(COMMISSION, html)
    for obsolete in (
      'USD 0,40',
      'USD 0.40',
      'USD 10',
      'por una sola ocasión',
      '3% +',
      '2.5% +',
      '1.5% +',
      'Monto de Venta',
    ):
      self.assertNotIn(obsolete, html)


class CanonicalContractTests(SimpleTestCase):
  def test_canonical_paragraphs_match_complete_public_snapshot(self):
    self.assertEqual(contract_terms.CONTRACT_PARAGRAPHS, approved_source())
    self.assertEqual(len(contract_terms.CONTRACT_PARAGRAPHS), 173)
    self.assertEqual(tuple(text for _, text in contract_terms.CONTRACT_BLOCKS), approved_source())

  def test_text_hash_and_version_identity_are_deterministic(self):
    expected_text = '\n\n'.join(approved_source())
    self.assertEqual(contract_terms.CONTRACT_TEXT, expected_text)
    digest = sha256(expected_text.encode('utf-8')).hexdigest()
    self.assertEqual(digest, '1e9833e8581502a75dd54fb3933af4a24ed52d83376d7163b89cbe161b5e0e46')
    self.assertEqual(contract_terms.CONTRACT_SHA256, digest)
    self.assertEqual(contract_terms.CONTRACT_VERSION, 'pagolink-initial-' + digest)

  def test_body_clauses_are_paragraphs_not_subheadings(self):
    blocks = {text: kind for kind, text in contract_terms.CONTRACT_BLOCKS}
    self.assertEqual(blocks['4.1. Licencia de uso'], 'subsection')
    self.assertEqual(blocks['8.2.- Confidencialidad'], 'subsection')
    self.assertEqual(blocks[contract_terms.CONTRACT_PARAGRAPHS[4]], 'paragraph')
