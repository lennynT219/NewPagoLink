"""Keep the existing readable secondary-button override on the dark hero."""

import unittest
from pathlib import Path


class HeroButtonOverrideTests(unittest.TestCase):
  def test_actual_dark_hero_retains_explicit_white_secondary(self):
    markup = Path('landing/templates/landing/index.html').read_text()
    self.assertIn(
      'class="btn-secondary" style="color: var(--white); border-color: rgba(255,255,255,0.4);"',
      markup,
    )
