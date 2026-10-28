"""Shared CSS contracts and selected color-pair math, not browser rendering.

No Django setup or application state is needed. These checks deliberately cover
only the shared declarations below, not inline overrides or WCAG certification.
"""

import re
import unittest
from pathlib import Path

CSS = (Path(__file__).parent / 'static/css/design-system.css').read_text()
CSS = re.sub(r'/\*.*?\*/', '', CSS, flags=re.DOTALL)


def declarations(selector):
  """Read flat rule declarations; this is not a CSS cascade implementation."""
  result = {}
  for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', CSS):
    if selector in [part.strip() for part in selectors.split(',')]:
      for name, value in re.findall(r'([\w-]+)\s*:\s*([^;]+);', body):
        result[name] = value.strip()
  return result


TOKENS = declarations(':root')


def color(value):
  while value.startswith('var('):
    value = TOKENS[value[4:-1]]
  if not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
    raise AssertionError(f'Expected opaque RGB color, got {value}')
  return tuple(int(value[i : i + 2], 16) / 255 for i in (1, 3, 5))


def contrast(foreground, background):
  def luminance(value):
    channels = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in color(value)]
    return sum(c * weight for c, weight in zip(channels, (0.2126, 0.7152, 0.0722)))

  light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
  return (light + 0.05) / (dark + 0.05)


class VisualFoundationTests(unittest.TestCase):
  def assert_readable(self, foreground, background):
    self.assertGreaterEqual(contrast(foreground, background), 4.5)

  def test_primary_white_label_on_each_gradient_stop(self):
    rule = declarations('.btn-primary-auth')
    stops = re.findall(r'var\(--[\w-]+\)', rule['background'])
    self.assertEqual(len(stops), 2)
    for stop in stops:
      with self.subTest(stop=stop):
        self.assert_readable(rule['color'], stop)
    self.assertEqual(declarations('.btn-primary-auth:hover')['color'], rule['color'])

  def test_secondary_label_and_hover_on_light_surface(self):
    rule = declarations('.btn-secondary')
    hover = declarations('.btn-secondary:hover')
    self.assertEqual(rule['background'], 'transparent')
    self.assert_readable(rule['color'], 'var(--white)')
    self.assert_readable(hover['color'], hover['background'])

  def test_shared_link_normal_and_hover_on_light_surfaces(self):
    for selector in ('a', 'a:hover'):
      for background in ('var(--white)', 'var(--gray-50)'):
        with self.subTest(selector=selector, background=background):
          self.assert_readable(declarations(selector)['color'], background)

  def test_placeholder_is_legible_in_both_field_states(self):
    placeholder = declarations('.input-modern::placeholder')
    for selector in ('.input-modern', '.input-modern:focus'):
      with self.subTest(selector=selector):
        self.assert_readable(placeholder['color'], declarations(selector)['background'])
    self.assertEqual(placeholder.get('opacity'), '1')

  def test_keyboard_focus_has_two_tone_ring_for_shared_controls(self):
    for selector in (
      '.btn:focus-visible',
      '.btn-primary-auth:focus-visible',
      '.btn-secondary:focus-visible',
      '.input-modern:focus-visible',
    ):
      with self.subTest(selector=selector):
        rule = declarations(selector)
        self.assertEqual(rule.get('outline'), '3px solid var(--navy-900)')
        self.assertEqual(rule.get('outline-offset'), '3px')
        self.assertEqual(rule.get('box-shadow'), '0 0 0 3px var(--white)')
    self.assertGreaterEqual(contrast('var(--navy-900)', 'var(--white)'), 3)

  def test_noninteractive_cards_do_not_lift_or_change_shadow_on_hover(self):
    for selector in ('.card-modern', '.card-stat'):
      with self.subTest(selector=selector):
        base = declarations(selector)
        hover = declarations(selector + ':hover')
        self.assertNotIn('transform', base)
        self.assertNotIn('transition', base)
        self.assertIn(hover.get('transform', 'none'), ('none', 'translateY(0)'))
        self.assertEqual(hover.get('box-shadow', base['box-shadow']), base['box-shadow'])

  def test_existing_brand_typography_and_field_text_pairs_remain_readable(self):
    self.assertEqual(TOKENS['--teal'], '#00c9a7')
    self.assertEqual(TOKENS['--teal-dark'], '#00b392')
    for navy in ('--navy-900', '--navy-800', '--navy-700'):
      self.assert_readable('var(--teal)', f'var({navy})')
    self.assert_readable(declarations('body')['color'], declarations('body')['background-color'])
    self.assert_readable(declarations('h1')['color'], 'var(--white)')
    self.assert_readable(declarations('.card-stat-label')['color'], 'var(--white)')
    self.assert_readable(declarations('.input-modern')['color'], 'var(--gray-50)')

  def test_existing_component_geometry_and_action_states_are_preserved(self):
    expected = {
      '.btn-primary-auth': {'padding': '14px 32px', 'display': 'inline-flex'},
      '.btn-secondary': {'padding': '12px 28px', 'display': 'inline-flex'},
      '.input-modern': {'width': '100%', 'padding': '12px 16px'},
      '.card-modern': {'padding': 'var(--space-6)', 'background': 'var(--white)'},
      '.card-stat': {'padding': 'var(--space-5)', 'display': 'flex', 'gap': 'var(--space-4)'},
    }
    for selector, properties in expected.items():
      for name, value in properties.items():
        with self.subTest(selector=selector, property=name):
          self.assertEqual(declarations(selector)[name], value)
    self.assertEqual(declarations('.btn-primary-auth:active')['transform'], 'translateY(0)')
    self.assertEqual(declarations('.input-modern:focus')['background'], 'var(--white)')
    self.assertEqual(declarations('.grid-3')['grid-template-columns'], '1fr')
    self.assertEqual(declarations('.grid-2')['grid-template-columns'], '1fr')


if __name__ == '__main__':
  unittest.main()
