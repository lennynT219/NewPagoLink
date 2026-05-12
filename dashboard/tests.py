"""Phase 2 tests: Dashboard core layout redesign (T2.1-T2.5)."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase


def _read_template(app_name, template_path):
    """Read a template file from an app's templates directory."""
    return (Path(settings.BASE_DIR) / app_name / 'templates' / template_path).read_text()


def _template_exists(app_name, template_path):
    """Check if a template file exists."""
    return (Path(settings.BASE_DIR) / app_name / 'templates' / template_path).exists()


# ══════════════════════════════════════════════════════════════════════
# T2.1: Dashboard Base Layout Redesign
# ══════════════════════════════════════════════════════════════════════


class DashboardBaseTemplateTests(TestCase):
    """T2.1: Verify dashboard/layouts/base.html complete redesign."""

    @property
    def content(self):
        return _read_template('dashboard', 'dashboard/layouts/base.html')

    # --- RED: Preserved blocks ---

    def test_base_has_doctype_and_html_lang_es(self):
        """Base must have DOCTYPE html and html lang='es'."""
        self.assertIn('<!DOCTYPE html>', self.content)
        self.assertIn('lang="es"', self.content)

    def test_base_preserves_title_block(self):
        """{% block title %} must be preserved."""
        self.assertIn('{% block title %}', self.content)

    def test_base_preserves_css_block(self):
        """{% block css %} must be preserved."""
        self.assertIn('{% block css %}', self.content)

    def test_base_preserves_content_block(self):
        """{% block content %} must be preserved."""
        self.assertIn('{% block content %}', self.content)

    def test_base_preserves_javascript_block(self):
        """{% block javascript %} must be preserved."""
        self.assertIn('{% block javascript %}', self.content)

    # --- RED: New design system CSS loaded ---

    def test_base_loads_design_system_css(self):
        """Must load design-system.css via static tag."""
        self.assertIn('design-system.css', self.content,
                      'Dashboard base must load unified design system CSS')

    # --- RED: Font Awesome 5 from local plugins ---

    def test_base_loads_font_awesome_5_local(self):
        """Must load Font Awesome 5 Free from local plugins directory."""
        self.assertIn('fontawesome-free', self.content,
                      'Must load FA5 from plugins/fontawesome-free')

    # --- RED: Legacy CSS REMOVED ---

    def test_base_removes_adminlte_css(self):
        """Must NOT load adminlte.min.css."""
        self.assertNotIn('adminlte.min.css', self.content,
                         'AdminLTE CSS must be removed from dashboard base')

    def test_base_removes_ionicons_cdn(self):
        """Must NOT reference Ionicons CDN."""
        self.assertNotIn('ionicons', self.content,
                         'Ionicons CDN must be removed')

    def test_base_removes_source_sans_pro(self):
        """Must NOT load Source Sans Pro font (replaced by Inter)."""
        self.assertNotIn('Source+Sans+Pro', self.content,
                         'Source Sans Pro font must be removed')

    def test_base_removes_icheck_bootstrap(self):
        """Must NOT load icheck-bootstrap.min.css."""
        self.assertNotIn('icheck', self.content,
                         'iCheck Bootstrap must be removed')

    # --- RED: Inter font loaded ---

    def test_base_loads_inter_font(self):
        """Must load Inter font from Google Fonts."""
        self.assertIn('Inter', self.content,
                      'Dashboard base must load Inter font')

    # --- RED: Navbar brand and structure ---

    def test_base_has_brand_pagolink(self):
        """Top navbar must have brand text 'PagoLink'."""
        self.assertIn('PagoLink', self.content)

    def test_base_has_user_dropdown(self):
        """User dropdown with edit profile and logout URLs preserved."""
        self.assertIn('dashboard:user-update', self.content)
        self.assertIn('dashboard:logout', self.content)

    # --- RED: Footer ---

    def test_base_has_footer_copyright(self):
        """Footer must preserve copyright with PagoLink and version."""
        self.assertIn('Copyright', self.content)
        self.assertIn('PagoLink', self.content)

    # --- RED: Scripts retained ---

    def test_base_keeps_jquery(self):
        """jQuery must be preserved for sidebar toggle and dropdowns."""
        self.assertIn('jquery', self.content.lower())

    def test_base_keeps_bootstrap_js(self):
        """Bootstrap JS bundle must be preserved."""
        self.assertIn('bootstrap.bundle', self.content)

    # --- RED: AdminLTE-specific removals ---

    def test_base_removes_adminlte_wrapper(self):
        """Must NOT have AdminLTE 'wrapper' class div."""
        self.assertNotIn('class="wrapper"', self.content,
                         'AdminLTE wrapper div must be removed')

    def test_base_removes_main_header_navbar(self):
        """Must NOT use AdminLTE main-header navbar."""
        self.assertNotIn('main-header', self.content,
                         'AdminLTE main-header must be removed')

    def test_base_removes_content_wrapper_div(self):
        """Must NOT have AdminLTE content-wrapper div."""
        self.assertNotIn('content-wrapper', self.content,
                         'AdminLTE content-wrapper must be removed')

    def test_base_removes_control_sidebar(self):
        """Must NOT have control-sidebar (unused)."""
        self.assertNotIn('control-sidebar', self.content,
                         'AdminLTE control-sidebar must be removed')

    def test_base_removes_sidebar_mini_body_class(self):
        """Must NOT use hold-transition sidebar-mini body class."""
        self.assertNotIn('sidebar-mini', self.content,
                         'AdminLTE sidebar-mini body class must be removed')

    def test_base_removes_adminlte_js(self):
        """Must NOT load adminlte.min.js."""
        self.assertNotIn('adminlte.min.js', self.content,
                         'AdminLTE JS must be removed')

    def test_base_removes_adminlte_logo_image(self):
        """Must NOT reference AdminLTELogo.png."""
        self.assertNotIn('AdminLTELogo', self.content,
                         'AdminLTE logo image must be removed')

    # --- RED: Sidebar include ---

    def test_base_includes_sidebar(self):
        """Must include dashboard/sidebar.html."""
        self.assertIn("dashboard/sidebar.html", self.content,
                      'Sidebar include must reference dashboard/sidebar.html')

    # --- TRIANGULATE: Navbar structure verification ---

    def test_base_navbar_has_fixed_positioning(self):
        """Top navbar must be fixed with navy background."""
        self.assertIn('position: fixed', self.content,
                      'Navbar must have fixed positioning')
        self.assertIn('navy-900', self.content,
                      'Navbar must use navy-900 background')

    def test_base_dropdown_preserves_bootstrap_data_attrs(self):
        """Dropdown must use Bootstrap data-toggle for JS functionality."""
        self.assertIn('data-toggle="dropdown"', self.content,
                      'Dropdown must preserve Bootstrap data attributes')

    def test_base_sidebar_container_has_dashboard_sidebar_class(self):
        """Sidebar must be wrapped in dashboard-sidebar container class."""
        self.assertIn('dashboard-sidebar', self.content,
                      'Sidebar container must use dashboard-sidebar class')

    def test_base_content_area_has_dashboard_content_class(self):
        """Content area must use dashboard-content wrapper class."""
        self.assertIn('dashboard-content', self.content,
                      'Content area must use dashboard-content class')


# ══════════════════════════════════════════════════════════════════════
# T2.2: Sidebar Redesign
# ══════════════════════════════════════════════════════════════════════


class DashboardSidebarTemplateTests(TestCase):
    """T2.2: Verify dashboard/sidebar.html redesign."""

    @property
    def content(self):
        return _read_template('dashboard', 'dashboard/sidebar.html')

    # --- RED: Brand consistency ---

    def test_sidebar_brand_is_pagolink_not_express(self):
        """Brand text must be 'PagoLink', NOT 'PagoLink Express'."""
        self.assertNotIn('PagoLink Express', self.content,
                         'Brand must NOT say "PagoLink Express"')
        self.assertIn('PagoLink', self.content)

    # --- RED: All navigation links preserved ---

    def test_sidebar_has_dashboard_link(self):
        self.assertIn('dashboard:dashboard', self.content)

    def test_sidebar_has_link_list(self):
        self.assertIn('payments:link_list', self.content)

    def test_sidebar_has_link_create(self):
        self.assertIn('payments:link_create', self.content)

    def test_sidebar_has_payment_history(self):
        self.assertIn('payments:payment_history', self.content)

    def test_sidebar_has_refund_list(self):
        self.assertIn('payments:refund_list', self.content)

    def test_sidebar_has_disbursement_list(self):
        self.assertIn('banking:disbursement_list', self.content)

    def test_sidebar_has_disbursement_create(self):
        self.assertIn('banking:disbursement_create', self.content)

    def test_sidebar_has_bank_config(self):
        self.assertIn('banking:config', self.content)

    def test_sidebar_has_contract(self):
        self.assertIn('dashboard:contract', self.content)

    def test_sidebar_has_logout(self):
        self.assertIn('dashboard:logout', self.content)

    # --- RED: Navigation sections preserved ---

    def test_sidebar_has_principal_section(self):
        self.assertIn('PRINCIPAL', self.content)

    def test_sidebar_has_ventas_section(self):
        self.assertIn('VENTAS Y COBROS', self.content)

    def test_sidebar_has_finanzas_section(self):
        self.assertIn('FINANZAS Y RETIROS', self.content)

    def test_sidebar_has_configuracion_section(self):
        self.assertIn('CONFIGURACIÓN', self.content)

    def test_sidebar_has_cuenta_section(self):
        self.assertIn('CUENTA', self.content)

    def test_sidebar_has_admin_section(self):
        self.assertIn('ADMINISTRACIÓN', self.content)

    # --- RED: Admin role conditional preserved ---

    def test_sidebar_preserves_admin_conditional(self):
        """Admin section must remain conditional on is_admin_role."""
        self.assertIn('is_admin_role', self.content)

    # --- RED: AdminLTE sidebar classes removed ---

    def test_sidebar_removes_main_sidebar_class(self):
        """Must NOT use AdminLTE main-sidebar class."""
        self.assertNotIn('main-sidebar', self.content,
                         'AdminLTE main-sidebar class must be removed')

    def test_sidebar_removes_nav_sidebar_class(self):
        """Must NOT use AdminLTE nav-sidebar class."""
        self.assertNotIn('nav-sidebar', self.content,
                         'AdminLTE nav-sidebar class must be removed')

    # --- RED: Icons preserved as FA5 ---

    def test_sidebar_has_icons(self):
        """Navigation must have FA5 icon classes."""
        self.assertIn('fas fa-', self.content,
                      'Sidebar must use Font Awesome 5 icons')

    # --- TRIANGULATE: Special link styles ---

    def test_sidebar_link_create_has_teal_accent(self):
        """Link create item must use teal accent class."""
        self.assertIn('sidebar-link-teal', self.content,
                      'Link create must have teal accent styling')

    def test_sidebar_logout_has_danger_accent(self):
        """Logout item must use danger/red accent class."""
        self.assertIn('sidebar-link-danger', self.content,
                      'Logout must have danger accent styling')

    def test_sidebar_admin_conditional_uses_customuser_path(self):
        """Admin role check must use request.user.customuser.is_admin_role."""
        self.assertIn('customuser.is_admin_role', self.content,
                      'Admin conditional must check via customuser relation')

    def test_sidebar_brand_uses_sidebar_brand_class(self):
        """Brand section must use sidebar-brand class (not AdminLTE brand-link)."""
        self.assertIn('sidebar-brand', self.content,
                      'Brand must use sidebar-brand class')
        self.assertNotIn('brand-link', self.content,
                         'AdminLTE brand-link class must be removed')

    def test_sidebar_links_use_sidebar_link_class(self):
        """Navigation links must use sidebar-link class (not AdminLTE nav-link)."""
        self.assertIn('sidebar-link', self.content,
                      'Links must use sidebar-link class')


# ══════════════════════════════════════════════════════════════════════
# T2.3: Dashboard Home Redesign + Duplicate Deletion
# ══════════════════════════════════════════════════════════════════════


class DashboardHomeTemplateTests(TestCase):
    """T2.3: Verify dashboard.html redesign and duplicate cleanup."""

    @property
    def content(self):
        return _read_template('dashboard', 'dashboard/dashboard.html')

    # --- RED: Extends correct base ---

    def test_dashboard_extends_base(self):
        """Must extend dashboard/layouts/base.html."""
        self.assertIn("dashboard/layouts/base.html", self.content)

    # --- RED: Title block ---

    def test_dashboard_title_block(self):
        """Must define title block."""
        self.assertIn('{% block title %}', self.content)

    # --- RED: Stat cards use card-stat ---

    def test_dashboard_uses_card_stat(self):
        """Stats must use card-stat class, not small-box."""
        self.assertIn('card-stat', self.content,
                      'Dashboard must use card-stat components')
        self.assertNotIn('small-box', self.content,
                         'AdminLTE small-box must be removed')

    # --- RED: Context variables preserved ---

    def test_dashboard_has_total_sales(self):
        self.assertIn('total_sales', self.content)

    def test_dashboard_has_daily_sales(self):
        self.assertIn('daily_sales', self.content)

    def test_dashboard_has_links_count(self):
        self.assertIn('links_count', self.content)

    def test_dashboard_has_available_balance(self):
        self.assertIn('available_balance', self.content)

    def test_dashboard_has_total_refunds(self):
        self.assertIn('total_refunds', self.content)

    # --- RED: Welcome message and security checklist ---

    def test_dashboard_welcome_message_preserved(self):
        """Welcome message must be preserved."""
        self.assertIn('Bienvenido', self.content)

    def test_dashboard_security_checklist_preserved(self):
        """Security checklist with email_active check must be preserved."""
        self.assertIn('email_active', self.content)
        self.assertIn('Seguridad', self.content)

    # --- RED: CTA buttons preserved ---

    def test_dashboard_cta_buttons_preserved(self):
        """Crear Link de Pago and Ver Mis Links / banking config preserved."""
        self.assertIn('payments:link_create', self.content)
        self.assertIn('banking:config', self.content)

    # --- RED: Uses card-modern ---

    def test_dashboard_uses_card_modern(self):
        """Welcome card must use card-modern styling."""
        self.assertIn('card-modern', self.content,
                      'Dashboard must use card-modern for cards')

    # --- TRIANGULATE: Layout structure ---

    def test_dashboard_stats_grid_uses_auto_fill(self):
        """Stat cards grid must use responsive auto-fill layout."""
        self.assertIn('auto-fill', self.content,
                      'Stats grid must use auto-fill for responsive layout')

    def test_dashboard_welcome_card_uses_card_modern(self):
        """Welcome message must be wrapped in card-modern (not AdminLTE card)."""
        self.assertIn('card-modern', self.content)
        self.assertNotIn('card-primary', self.content,
                         'AdminLTE card-primary must be removed from dashboard')
        self.assertNotIn('card-outline', self.content,
                         'AdminLTE card-outline must be removed from dashboard')

    def test_dashboard_button_uses_btn_primary_auth(self):
        """CTA button must use btn-primary-auth from design system."""
        self.assertIn('btn-primary-auth', self.content,
                      'CTA must use btn-primary-auth')

    def test_dashboard_has_five_stat_cards(self):
        """Dashboard must render all 5 stat cards (balance, daily, total, links, refunds)."""
        # Each card-stat div represents one metric card
        occurrences = self.content.count('class="card-stat"')
        self.assertEqual(occurrences, 5,
                         f'Expected 5 card-stat components, found {occurrences}')

    def test_dashboard_email_conditional_has_branches(self):
        """email_active conditional must have both if and else branches."""
        self.assertIn('{% if email_active %}', self.content,
                      'Missing email_active if branch')
        self.assertIn('{% else %}', self.content,
                      'Missing email_active else branch')


class DuplicateDashboardDeletionTests(TestCase):
    """T2.3: Verify duplicate dashboard.html is deleted."""

    def test_duplicate_dashboard_html_does_not_exist(self):
        """The duplicate at dashboard/templates/dashboard.html must be DELETED."""
        duplicate_path = (
            Path(settings.BASE_DIR) / 'dashboard' / 'templates' / 'dashboard.html'
        )
        self.assertFalse(
            duplicate_path.exists(),
            'Duplicate dashboard.html at dashboard/templates/dashboard.html '
            'must be deleted. Only dashboard/templates/dashboard/dashboard.html '
            'should remain.'
        )

    def test_canonical_dashboard_html_exists(self):
        """The canonical dashboard.html must still exist."""
        canonical_path = (
            Path(settings.BASE_DIR) / 'dashboard' / 'templates' / 'dashboard' / 'dashboard.html'
        )
        self.assertTrue(
            canonical_path.exists(),
            'Canonical dashboard.html must still exist'
        )


# ══════════════════════════════════════════════════════════════════════
# T2.4: Contract Page Redesign
# ══════════════════════════════════════════════════════════════════════


class DashboardContractTemplateTests(TestCase):
    """T2.4: Verify dashboard/contract.html redesign."""

    @property
    def content(self):
        return _read_template('dashboard', 'dashboard/contract.html')

    # --- RED: Extends correct base ---

    def test_contract_extends_base(self):
        self.assertIn("dashboard/layouts/base.html", self.content)

    # --- RED: Uses card-modern ---

    def test_contract_uses_card_modern(self):
        """Must use card-modern for the contract card."""
        self.assertIn('card-modern', self.content,
                      'Contract page must use card-modern')

    # --- RED: Form preserved ---

    def test_contract_has_form_with_csrf(self):
        """Form with CSRF token and submit button must be preserved."""
        self.assertIn('{% csrf_token %}', self.content)
        self.assertIn('<form', self.content.lower())
        self.assertIn('submit', self.content.lower())

    def test_contract_accept_button_preserved(self):
        """Accept button text must be preserved."""
        self.assertIn('Acepto', self.content)

    # --- RED: Legal content preserved ---

    def test_contract_clausulas_preserved(self):
        """CLÁUSULAS heading must be preserved."""
        self.assertIn('CLÁUSULAS', self.content)

    def test_contract_adrest_preserved(self):
        """ADREST company name must be preserved."""
        self.assertIn('ADREST', self.content)

    def test_contract_vendedor_preserved(self):
        """VENDEDOR reference must be preserved."""
        self.assertIn('VENDEDOR', self.content)

    # --- RED: Removes AdminLTE classes ---

    def test_contract_removes_adminlte_card_classes(self):
        """Must NOT use AdminLTE card classes like card-primary."""
        self.assertNotIn('card-primary', self.content,
                         'AdminLTE card classes must be removed')

    # --- TRIANGULATE: Layout features ---

    def test_contract_has_scrollable_legal_text(self):
        """Legal text area must have scrollable overflow with max-height."""
        self.assertIn('overflow-y', self.content,
                      'Legal text must have overflow-y for scrolling')
        self.assertIn('max-height', self.content,
                      'Legal text must have max-height constraint')

    def test_contract_form_uses_post_method(self):
        """Accept form must use POST method."""
        self.assertIn('method="post"', self.content,
                      'Form must use POST method')

    def test_contract_accept_button_uses_btn_primary_auth(self):
        """Accept button must use btn-primary-auth."""
        self.assertIn('btn-primary-auth', self.content,
                      'Accept button must use btn-primary-auth')

    def test_contract_has_warning_alert(self):
        """Contract must have a warning/attention alert before legal text."""
        self.assertIn('exclamation-triangle', self.content,
                      'Must have warning icon')
        self.assertIn('Atención', self.content,
                      'Must have attention heading')

    def test_contract_tariff_table_uses_table_modern(self):
        """Tariff table must use table-modern class."""
        self.assertIn('table-modern', self.content,
                      'Tariff table must use table-modern')

    def test_contract_title_block_preserved(self):
        """Title block must be preserved."""
        self.assertIn('{% block title %}', self.content)


# ══════════════════════════════════════════════════════════════════════
# T2.5: Profile Form Redesign
# ══════════════════════════════════════════════════════════════════════


class AccountsProfileFormTemplateTests(TestCase):
    """T2.5: Verify accounts/profile_form.html redesign."""

    @property
    def content(self):
        return _read_template('accounts', 'accounts/profile_form.html')

    # --- RED: Extends correct base ---

    def test_profile_extends_dashboard_base(self):
        self.assertIn("dashboard/layouts/base.html", self.content)

    # --- RED: Uses card-modern ---

    def test_profile_uses_card_modern(self):
        """Profile form must use card-modern wrapper."""
        self.assertIn('card-modern', self.content,
                      'Profile form must use card-modern')

    # --- RED: Form fields preserved ---

    def test_profile_has_firstname_field(self):
        self.assertIn('firstname', self.content)

    def test_profile_has_lastname_field(self):
        self.assertIn('lastname', self.content)

    def test_profile_has_email_field(self):
        self.assertIn('form.email', self.content)

    def test_profile_has_identification_field(self):
        self.assertIn('form.identification', self.content)

    def test_profile_has_phone_field(self):
        self.assertIn('form.phone', self.content)

    # --- RED: CSRF and submit ---

    def test_profile_has_csrf(self):
        self.assertIn('{% csrf_token %}', self.content)

    def test_profile_submit_button_preserved(self):
        """Submit button with 'Actualizar' text must be preserved."""
        self.assertIn('Actualizar', self.content)

    def test_profile_cancel_button_preserved(self):
        """Cancel button linking to dashboard must be preserved."""
        self.assertIn('dashboard:dashboard', self.content)

    # --- RED: Removes AdminLTE classes ---

    def test_profile_removes_content_header(self):
        """Must NOT use AdminLTE content-header class."""
        self.assertNotIn('content-header', self.content,
                         'AdminLTE content-header must be removed')

    def test_profile_removes_adminlte_card_classes(self):
        """Must NOT use AdminLTE card-primary, card-outline classes."""
        self.assertNotIn('card-primary', self.content,
                         'AdminLTE card-primary must be removed')
        self.assertNotIn('card-outline', self.content,
                         'AdminLTE card-outline must be removed')

    # --- RED: Uses btn-primary-auth ---

    def test_profile_uses_btn_primary_auth(self):
        """Submit button must use btn-primary-auth."""
        self.assertIn('btn-primary-auth', self.content,
                      'Profile form must use btn-primary-auth')

    # --- TRIANGULATE: Form structure and field labels ---

    def test_profile_form_uses_post_method(self):
        """Form must use POST method."""
        self.assertIn('method="post"', self.content,
                      'Form must use POST method')

    def test_profile_form_has_field_labels(self):
        """All form field labels must be preserved."""
        labels = ['Nombres', 'Apellidos', 'Correo Electrónico', 'Identificación', 'Teléfono']
        for label in labels:
            self.assertIn(label, self.content,
                          f'Missing field label: {label}')

    def test_profile_cancel_uses_btn_secondary(self):
        """Cancel button must use btn-secondary for consistency."""
        self.assertIn('btn-secondary', self.content,
                      'Cancel button must use btn-secondary')

    def test_profile_title_block_preserved(self):
        """Title block must be preserved."""
        self.assertIn('{% block title %}', self.content)

    def test_profile_form_has_exactly_five_fields(self):
        """Profile form must render exactly 5 Django form fields (firstname, lastname, email, identification, phone)."""
        form_field_refs = [
            'form.firstname', 'form.lastname', 'form.email',
            'form.identification', 'form.phone'
        ]
        for ref in form_field_refs:
            self.assertIn(ref, self.content,
                          f'Missing form field: {ref}')


# ══════════════════════════════════════════════════════════════════════
# Phase 6: Bug Fixes and Cleanup
# ══════════════════════════════════════════════════════════════════════

# ── T6.1: Delete legacy auth templates (login.html, register.html) ──


class LegacyAuthTemplateCleanupTests(TestCase):
    """T6.1: Verify legacy login.html and register.html are deleted."""

    def test_legacy_login_template_does_not_exist(self):
        self.assertFalse(
            _template_exists('dashboard', 'dashboard/login.html'),
            'Legacy login.html must be deleted; auth.html replaces it'
        )

    def test_legacy_register_template_does_not_exist(self):
        self.assertFalse(
            _template_exists('dashboard', 'dashboard/register.html'),
            'Legacy register.html must be deleted; auth.html replaces it'
        )

    def test_auth_template_still_exists(self):
        self.assertTrue(
            _template_exists('dashboard', 'dashboard/auth.html'),
            'auth.html must be preserved as the sole auth template'
        )

    def test_auth_has_login_context(self):
        content = _read_template('dashboard', 'dashboard/auth.html')
        self.assertIn('login_form', content)
        self.assertIn("url 'dashboard:login'", content)

    def test_auth_has_register_context(self):
        content = _read_template('dashboard', 'dashboard/auth.html')
        self.assertIn('register_form', content)
        self.assertIn("url 'dashboard:register'", content)


# ── T6.2: Fix reset_password.html ──


class ResetPasswordFixTests(TestCase):
    """T6.2: Verify reset_password.html is fixed with design-system styling."""

    @property
    def content(self):
        return _read_template('dashboard', 'dashboard/reset_password.html')

    def test_reset_extends_landing_base(self):
        self.assertIn('landing/layouts/base.html', self.content)

    def test_reset_uses_card_modern(self):
        self.assertIn('card-modern', self.content)

    def test_reset_uses_btn_primary_auth(self):
        self.assertIn('btn-primary-auth', self.content)

    def test_reset_uses_btn_primary_auth_link(self):
        """ResetPassword view has no form/post — template is a link-only page."""
        self.assertIn('btn-primary-auth', self.content)
        self.assertIn('dashboard:password_reset', self.content)

    def test_reset_removes_adminlte(self):
        self.assertNotIn('adminlte', self.content)

    def test_reset_removes_broken_static_path(self):
        self.assertNotIn('dashboard/plugins/', self.content)
        self.assertNotIn('dashboard/css/', self.content)
        self.assertNotIn('dashboard/js/', self.content)

    def test_reset_links_to_actual_password_reset(self):
        """ResetPassword view has no form/post — template links to real password_reset."""
        self.assertIn('dashboard:password_reset', self.content)

    def test_reset_links_to_login(self):
        """ResetPassword page must link back to login."""
        self.assertIn('dashboard:login', self.content)

    def test_reset_has_password_reset_title(self):
        self.assertIn('Restablecer', self.content)
        self.assertIn('contrase', self.content)


# ── T6.3: Update password_reset_*.html templates ──


class PasswordResetFormTests(TestCase):
    """T6.3a: password_reset_form.html"""

    @property
    def content(self):
        return _read_template('dashboard', 'dashboard/registration/password_reset_form.html')

    def test_extends_landing_base(self):
        self.assertIn('landing/layouts/base.html', self.content)

    def test_uses_card_modern(self):
        self.assertIn('card-modern', self.content)

    def test_uses_btn_primary_auth(self):
        self.assertIn('btn-primary-auth', self.content)

    def test_uses_input_modern(self):
        self.assertIn('input-modern', self.content)

    def test_removes_adminlte(self):
        self.assertNotIn('adminlte', self.content)

    def test_removes_hold_transition_class(self):
        self.assertNotIn('hold-transition', self.content)

    def test_preserves_csrf(self):
        self.assertIn('csrf_token', self.content)

    def test_preserves_email_input(self):
        self.assertIn('name="email"', self.content)

    def test_preserves_login_url(self):
        self.assertIn("url 'dashboard:login'", self.content)


class PasswordResetDoneTests(TestCase):
    """T6.3b: password_reset_done.html"""

    @property
    def content(self):
        return _read_template('dashboard', 'dashboard/registration/password_reset_done.html')

    def test_extends_landing_base(self):
        self.assertIn('landing/layouts/base.html', self.content)

    def test_uses_card_modern(self):
        self.assertIn('card-modern', self.content)

    def test_has_success_message(self):
        self.assertIn('enviado', self.content.lower())
        self.assertIn('correo', self.content.lower())

    def test_has_login_url(self):
        self.assertIn("url 'dashboard:login'", self.content)

    def test_removes_adminlte(self):
        self.assertNotIn('adminlte', self.content)

    def test_removes_hold_transition(self):
        self.assertNotIn('hold-transition', self.content)


class PasswordResetConfirmTests(TestCase):
    """T6.3c: password_reset_confirm.html"""

    @property
    def content(self):
        return _read_template('dashboard', 'dashboard/registration/password_reset_confirm.html')

    def test_extends_landing_base(self):
        self.assertIn('landing/layouts/base.html', self.content)

    def test_uses_card_modern(self):
        self.assertIn('card-modern', self.content)

    def test_uses_btn_primary_auth(self):
        self.assertIn('btn-primary-auth', self.content)

    def test_removes_adminlte(self):
        self.assertNotIn('adminlte', self.content)

    def test_preserves_validlink_condition(self):
        self.assertIn('validlink', self.content)

    def test_preserves_csrf(self):
        self.assertIn('csrf_token', self.content)

    def test_preserves_form_as_p(self):
        self.assertIn('form.as_p', self.content)

    def test_preserves_password_reset_url(self):
        self.assertIn("url 'dashboard:password_reset'", self.content)


class PasswordResetCompleteTests(TestCase):
    """T6.3d: password_reset_complete.html"""

    @property
    def content(self):
        return _read_template('dashboard', 'dashboard/registration/password_reset_complete.html')

    def test_extends_landing_base(self):
        self.assertIn('landing/layouts/base.html', self.content)

    def test_uses_card_modern(self):
        self.assertIn('card-modern', self.content)

    def test_has_success_title(self):
        self.assertIn('cambiada', self.content.lower())

    def test_has_login_url(self):
        self.assertIn("url 'dashboard:login'", self.content)

    def test_removes_adminlte(self):
        self.assertNotIn('adminlte', self.content)

    def test_removes_hold_transition(self):
        self.assertNotIn('hold-transition', self.content)


class PasswordResetEmailTests(TestCase):
    """T6.3e: password_reset_email.html (plain text, no AdminLTE concerns)"""

    @property
    def content(self):
        return _read_template('dashboard', 'dashboard/registration/password_reset_email.html')

    def test_preserves_uid_token_variables(self):
        self.assertIn('uid', self.content)
        self.assertIn('token', self.content)

    def test_preserves_protocol_domain(self):
        self.assertIn('protocol', self.content)
        self.assertIn('domain', self.content)

    def test_preserves_password_reset_url(self):
        self.assertIn("url 'dashboard:password_reset_confirm'", self.content)

    def test_has_pagolink_brand(self):
        self.assertIn('PagoLink', self.content)

    def test_removes_express_branding(self):
        self.assertNotIn('Express', self.content)


# ── T6.4: Update activation pages ──


class ActivationSuccessTests(TestCase):
    """T6.4a: activation_success.html"""

    @property
    def content(self):
        return _read_template('dashboard', 'dashboard/activation_success.html')

    def test_extends_landing_base(self):
        self.assertIn('landing/layouts/base.html', self.content)

    def test_uses_card_modern(self):
        self.assertIn('card-modern', self.content)

    def test_uses_btn_primary_auth(self):
        self.assertIn('btn-primary-auth', self.content)

    def test_has_green_success_icon(self):
        self.assertIn('check-circle', self.content)
        self.assertIn('success', self.content)

    def test_has_dashboard_link(self):
        self.assertIn("url 'dashboard", self.content)

    def test_removes_bootstrap_btn_primary(self):
        self.assertNotIn('btn btn-primary', self.content)

    def test_preserves_title_block(self):
        self.assertIn('title', self.content)


class ActivationInvalidTests(TestCase):
    """T6.4b: activation_invalid.html"""

    @property
    def content(self):
        return _read_template('dashboard', 'dashboard/activation_invalid.html')

    def test_extends_landing_base(self):
        self.assertIn('landing/layouts/base.html', self.content)

    def test_uses_card_modern(self):
        self.assertIn('card-modern', self.content)

    def test_has_warning_danger_content(self):
        self.assertIn('Inv', self.content)
        self.assertIn('lido', self.content.lower())

    def test_has_register_link(self):
        self.assertIn("url 'dashboard:register'", self.content)

    def test_removes_bootstrap_secondary(self):
        self.assertNotIn('btn btn-secondary', self.content)

    def test_preserves_title_block(self):
        self.assertIn('title', self.content)


# ── T6.5: Branded email master template ──


class BrandedEmailBaseTests(TestCase):
    """T6.5a: base_email.html"""

    @property
    def content(self):
        base = Path(settings.BASE_DIR) / 'templates' / 'emails' / 'base_email.html'
        return base.read_text()

    def test_has_doctype_html(self):
        self.assertIn('<!DOCTYPE html>', self.content)

    def test_has_navy_brand_color(self):
        self.assertIn('162447', self.content)

    def test_has_teal_accent(self):
        self.assertIn('00c9a7', self.content)

    def test_has_content_block(self):
        self.assertIn('block content', self.content)

    def test_has_pagolink_branding(self):
        self.assertIn('PagoLink', self.content)


class ActivationEmailExtendsBaseTests(TestCase):
    """T6.5b: activation_email.html extends base_email.html"""

    @property
    def content(self):
        return _read_template('dashboard', 'dashboard/activation_email.html')

    def test_extends_base_email(self):
        self.assertIn("emails/base_email.html", self.content)

    def test_uses_content_block(self):
        self.assertIn('block content', self.content)

    def test_preserves_user_variable(self):
        self.assertIn('user.first_name', self.content)

    def test_preserves_uid_token(self):
        self.assertIn('uid', self.content)
        self.assertIn('token', self.content)

    def test_preserves_domain(self):
        self.assertIn('domain', self.content)


class InviteEmailExtendsBaseTests(TestCase):
    """T6.5c: invite_email.html extends base_email.html"""

    @property
    def content(self):
        return _read_template('payments', 'payments/emails/invite_email.html')

    def test_extends_base_email(self):
        self.assertIn("emails/base_email.html", self.content)

    def test_uses_content_block(self):
        self.assertIn('block content', self.content)

    def test_preserves_payment_variables(self):
        self.assertIn('payment.first_name', self.content)
        self.assertIn('payment.description', self.content)
        self.assertIn('payment.amount', self.content)

    def test_preserves_pay_url(self):
        self.assertIn('pay_url', self.content)


class ConfirmationEmailExtendsBaseTests(TestCase):
    """T6.5d: confirmation_email.html extends base_email.html"""

    @property
    def content(self):
        return _read_template('payments', 'payments/emails/confirmation_email.html')

    def test_extends_base_email(self):
        self.assertIn("emails/base_email.html", self.content)

    def test_uses_content_block(self):
        self.assertIn('block content', self.content)

    def test_preserves_payment_variables(self):
        self.assertIn('payment.first_name', self.content)
        self.assertIn('payment.description', self.content)
        self.assertIn('payment.amount', self.content)

    def test_preserves_transaction_id(self):
        self.assertIn('transaction_id', self.content)


# ── T6.6: Remove unused AdminLTE static assets ──


class AdminLTEAssetCleanupTests(TestCase):
    """T6.6: Verify AdminLTE assets are removed."""

    def test_adminlte_css_removed(self):
        path = Path(settings.BASE_DIR) / 'dashboard' / 'static' / 'css' / 'adminlte.min.css'
        self.assertFalse(path.exists(), 'adminlte.min.css must be removed')

    def test_adminlte_js_removed(self):
        path = Path(settings.BASE_DIR) / 'dashboard' / 'static' / 'js' / 'adminlte.min.js'
        self.assertFalse(path.exists(), 'adminlte.min.js must be removed')

    def test_icheck_bootstrap_removed(self):
        path = Path(settings.BASE_DIR) / 'dashboard' / 'static' / 'plugins' / 'icheck-bootstrap'
        self.assertFalse(path.exists(), 'icheck-bootstrap directory must be removed')

    def test_fontawesome_still_exists(self):
        path = Path(settings.BASE_DIR) / 'dashboard' / 'static' / 'plugins' / 'fontawesome-free'
        self.assertTrue(path.exists(), 'fontawesome-free must be preserved')

    def test_jquery_still_exists(self):
        path = Path(settings.BASE_DIR) / 'dashboard' / 'static' / 'plugins' / 'jquery'
        self.assertTrue(path.exists(), 'jquery must be preserved')

    def test_bootstrap_still_exists(self):
        path = Path(settings.BASE_DIR) / 'dashboard' / 'static' / 'plugins' / 'bootstrap'
        self.assertTrue(path.exists(), 'bootstrap must be preserved')
