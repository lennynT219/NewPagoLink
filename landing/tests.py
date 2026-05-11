"""Tests for landing page templates and design system."""

from django.conf import settings
from django.template import engines
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from pathlib import Path


class DesignSystemCSSTests(TestCase):
    """T1.1: Verify design-system.css exists and contains required design tokens."""

    def test_css_file_exists_and_is_discoverable(self):
        """CSS file must exist in landing/static/css/ and be loadable."""
        css_path = Path(settings.BASE_DIR) / 'landing' / 'static' / 'css' / 'design-system.css'
        self.assertTrue(css_path.exists(), f'design-system.css not found at {css_path}')

        content = css_path.read_text()
        self.assertIn(':root', content, 'Missing :root CSS custom properties block')

    def test_css_contains_required_custom_properties(self):
        """All required navy/teal design tokens must be defined."""
        css_path = Path(settings.BASE_DIR) / 'landing' / 'static' / 'css' / 'design-system.css'
        content = css_path.read_text()

        required_props = [
            '--navy-900', '--navy-800', '--navy-700', '--navy-600',
            '--teal', '--teal-dark', '--teal-glow',
        ]
        for prop in required_props:
            self.assertIn(prop, content, f'Missing CSS property: {prop}')

    def test_css_contains_component_classes(self):
        """Required component classes must be defined."""
        css_path = Path(settings.BASE_DIR) / 'landing' / 'static' / 'css' / 'design-system.css'
        content = css_path.read_text()

        required_classes = [
            '.card-modern', '.btn-primary-auth', '.btn-secondary',
            '.input-modern', '.badge-status', '.table-modern',
            '.page-hero', '.section-container', '.empty-state',
        ]
        for cls in required_classes:
            self.assertIn(cls, content, f'Missing component class: {cls}')


class LandingBaseTemplateTests(TestCase):
    """T1.2: Verify base.html redesign preserves Django blocks and context."""

    def test_base_template_renders_with_all_blocks(self):
        """Base template must define title and content blocks."""
        rendered = render_to_string('landing/layouts/base.html', {'request': None})
        self.assertIn('{% block title %}', open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'layouts' / 'base.html'
        ).read())
        self.assertIn('{% block content %}', open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'layouts' / 'base.html'
        ).read())

    def test_base_template_loads_design_system_css(self):
        """Base template must load the unified design system CSS."""
        base_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'layouts' / 'base.html'
        ).read()
        self.assertIn(
            "design-system.css",
            base_content,
            'Base template must reference design-system.css'
        )

    def test_base_template_loads_font_awesome_5(self):
        """Base template must load Font Awesome 5 Free from local plugins."""
        base_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'layouts' / 'base.html'
        ).read()
        self.assertIn(
            'fontawesome-free',
            base_content,
            'Base template must load Font Awesome 5 Free'
        )

    def test_base_template_removes_legacy_style_css(self):
        """Base template must NOT reference the old style.css."""
        base_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'layouts' / 'base.html'
        ).read()
        # Only check for the old style.css reference from landing
        self.assertNotIn(
            "{% static 'css/style.css' %}",
            base_content,
            'Old style.css reference must be removed'
        )

    def test_base_template_keeps_navbar_links(self):
        """Navbar must keep Inicio, Precios, Contactenos, and CTA links."""
        base_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'layouts' / 'base.html'
        ).read()
        self.assertIn('Inicio', base_content)
        self.assertIn('Precios', base_content)
        self.assertIn('Contáctenos', base_content)
        self.assertIn('Iniciar sesión', base_content)

    def test_base_template_has_footer_copyright(self):
        """Footer must preserve PagoLink copyright."""
        base_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'layouts' / 'base.html'
        ).read()
        self.assertIn('PagoLink', base_content)


class LandingIndexTemplateTests(TestCase):
    """T1.3: Verify index.html redesign preserves content and context."""

    def test_index_extends_base_template(self):
        """Index must extend landing/layouts/base.html."""
        index_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'index.html'
        ).read()
        self.assertIn("'landing/layouts/base.html'", index_content)

    def test_index_title_block(self):
        """Index must define the title block."""
        index_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'index.html'
        ).read()
        self.assertIn('{% block title %}', index_content)

    def test_index_hero_heading_preserved(self):
        """Hero must preserve the main heading text."""
        index_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'index.html'
        ).read()
        self.assertIn('Vende por redes sociales', index_content)

    def test_index_has_cta_button_to_register(self):
        """CTA button must link to dashboard:register."""
        index_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'index.html'
        ).read()
        self.assertIn("dashboard:register", index_content)

    def test_index_hero_cta_uses_nueva_text(self):
        """Hero CTA must use 'Comenzar ahora' text per redesign spec."""
        index_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'index.html'
        ).read()
        self.assertIn('Comenzar ahora', index_content,
                      'Hero must have a "Comenzar ahora" CTA button')

    def test_index_feature_steps_preserved(self):
        """3-step feature section must preserve content."""
        index_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'index.html'
        ).read()
        self.assertIn('Registra', index_content)
        self.assertIn('link de cobro', index_content)
        self.assertIn('recibes', index_content)

    def test_index_payment_methods_section_preserved(self):
        """Payment methods section must preserve card logos."""
        index_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'index.html'
        ).read()
        self.assertIn('fa-cc-visa', index_content)
        self.assertIn('fa-cc-mastercard', index_content)

    def test_index_cta_section_preserved(self):
        """Bottom CTA section must preserve heading and buttons."""
        index_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'index.html'
        ).read()
        self.assertIn('¿Listo empezar a cobrar', index_content)


class LandingPricingTemplateTests(TestCase):
    """T1.4: Verify pricing.html redesign preserves content with modern cards."""

    def test_pricing_extends_base_template(self):
        """Pricing must extend landing/layouts/base.html."""
        pricing_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'pricing.html'
        ).read()
        self.assertIn("'landing/layouts/base.html'", pricing_content)

    def test_pricing_title_block(self):
        """Pricing must define the title block."""
        pricing_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'pricing.html'
        ).read()
        self.assertIn('{% block title %}Precios', pricing_content)

    def test_pricing_heading_preserved(self):
        """Pricing heading text must be preserved."""
        pricing_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'pricing.html'
        ).read()
        self.assertIn('Precios', pricing_content)

    def test_pricing_tariff_info_preserved(self):
        """Tariff description text must be preserved."""
        pricing_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'pricing.html'
        ).read()
        self.assertIn('cuadro de tarifas', pricing_content)

    def test_pricing_replaces_table_with_cards(self):
        """Table-striped must be replaced with modern pricing cards."""
        pricing_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'pricing.html'
        ).read()
        self.assertNotIn('table-striped', pricing_content,
                         'Bootstrap table-striped must be removed')
        self.assertIn('card-modern', pricing_content,
                      'Pricing must use card-modern')


class LandingContactTemplateTests(TestCase):
    """T1.5: Verify contact.html redesign removes external endpoint."""

    def test_contact_extends_base_template(self):
        """Contact must extend landing/layouts/base.html."""
        contact_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'contact.html'
        ).read()
        self.assertIn("'landing/layouts/base.html'", contact_content)

    def test_contact_heading_preserved(self):
        """Contact heading must be preserved."""
        contact_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'contact.html'
        ).read()
        self.assertIn('Contáctenos', contact_content)

    def test_contact_info_preserved(self):
        """Contact info (address, email, phone) must be preserved."""
        contact_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'contact.html'
        ).read()
        self.assertIn('Quito', contact_content)
        self.assertIn('pagolink', contact_content)

    def test_contact_removes_external_form_endpoint(self):
        """External sendmail.w3layouts.com form action must be removed."""
        contact_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'contact.html'
        ).read()
        self.assertNotIn('sendmail.w3layouts.com', contact_content,
                         'External form endpoint must be removed')

    def test_contact_uses_card_styling(self):
        """Contact info should use card-modern styling."""
        contact_content = open(
            Path(settings.BASE_DIR) / 'landing' / 'templates' / 'landing' / 'contact.html'
        ).read()
        self.assertIn('card-modern', contact_content,
                      'Contact page must use card-modern styling')
