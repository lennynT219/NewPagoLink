from pathlib import Path

from django.conf import settings
from django.test import TestCase


def _read_template(app_name, template_path):
    """Read a template file from an app's templates directory."""
    return (Path(settings.BASE_DIR) / app_name / 'templates' / template_path).read_text()


# ══════════════════════════════════════════════════════════════════════
# T5.1: Payment Method Template
# ══════════════════════════════════════════════════════════════════════

class PaymentMethodTemplateTests(TestCase):
    """T5.1: Verify banking/payment_method.html uses design-system classes."""

    @property
    def content(self):
        return _read_template('banking', 'banking/payment_method.html')

    # ── Design-system classes present ──

    def test_payment_method_has_card_modern(self):
        """Must use .card-modern for the bank configuration form wrapper."""
        self.assertIn('card-modern', self.content,
                      'payment_method.html must contain card-modern class')

    def test_payment_method_has_form_styling(self):
        """Form fields must be styled via CSS block targeting form controls."""
        has_styling = (
            '{% block css %}' in self.content or
            'input-' in self.content
        )
        self.assertTrue(has_styling,
                        'payment_method.html must style form controls (block css or input styling)')

    def test_payment_method_has_btn_primary_auth(self):
        """Submit button must use .btn-primary-auth."""
        self.assertIn('btn-primary-auth', self.content,
                      'payment_method.html must use btn-primary-auth')

    # ── AdminLTE classes removed ──

    def test_payment_method_removes_card_primary(self):
        """Must NOT use AdminLTE card-primary/card-outline."""
        self.assertNotIn('card-primary', self.content,
                         'AdminLTE card-primary must be removed')
        self.assertNotIn('card-outline', self.content,
                         'AdminLTE card-outline must be removed')

    def test_payment_method_removes_content_header(self):
        """Must NOT use AdminLTE content-header."""
        self.assertNotIn('content-header', self.content,
                         'AdminLTE content-header must be removed')

    def test_payment_method_removes_alert_dismissible(self):
        """Must NOT use AdminLTE alert-dismissible."""
        self.assertNotIn('alert alert-warning alert-dismissible', self.content,
                         'AdminLTE alert-dismissible must be replaced')

    # ── Context variables preserved ──

    def test_payment_method_preserves_form_fields(self):
        """All form fields must be preserved."""
        self.assertIn('{{ form.fullname }}', self.content)
        self.assertIn('{{ form.bank }}', self.content)
        self.assertIn('{{ form.account_type }}', self.content)
        self.assertIn('{{ form.account_number }}', self.content)
        self.assertIn('{{ form.cci }}', self.content)

    def test_payment_method_preserves_csrf(self):
        """CSRF token must be preserved."""
        self.assertIn('{% csrf_token %}', self.content)

    def test_payment_method_preserves_url_tags(self):
        """URL tags must be preserved."""
        self.assertIn("{% url 'dashboard:dashboard' %}", self.content)

    def test_payment_method_preserves_payment_method_check(self):
        """{% if not payment_method %} guard must be preserved."""
        self.assertIn('payment_method', self.content,
                      'payment_method context variable must be referenced')

    def test_payment_method_extends_correct_base(self):
        """Must extend dashboard/layouts/base.html."""
        self.assertIn("{% extends 'dashboard/layouts/base.html' %}", self.content)

    def test_payment_method_preserves_non_field_errors(self):
        """Non-field error handling must be preserved."""
        self.assertIn('form.non_field_errors', self.content)

    def test_payment_method_preserves_field_errors(self):
        """Per-field error handling must be preserved."""
        self.assertIn('form.fullname.errors', self.content)


# ══════════════════════════════════════════════════════════════════════
# T5.2a: Disbursement List Template
# ══════════════════════════════════════════════════════════════════════

class DisbursementListTemplateTests(TestCase):
    """T5.2: Verify banking/disbursement_list.html uses design-system classes."""

    @property
    def content(self):
        return _read_template('banking', 'banking/disbursement_list.html')

    # ── Design-system classes present ──

    def test_disbursement_list_has_table_modern(self):
        """Must use .table-modern for the disbursement table."""
        self.assertIn('table-modern', self.content,
                      'disbursement_list.html must contain table-modern class')

    def test_disbursement_list_has_badge_status(self):
        """Status column must use .badge-status pills."""
        self.assertIn('badge-status', self.content,
                      'disbursement_list.html must use badge-status')

    def test_disbursement_list_has_empty_state(self):
        """Must use .empty-state for no disbursements case."""
        self.assertIn('empty-state', self.content,
                      'disbursement_list.html must contain empty-state')

    # ── AdminLTE classes removed ──

    def test_disbursement_list_removes_card_primary(self):
        """Must NOT use AdminLTE card-primary/card-outline."""
        self.assertNotIn('card-primary', self.content,
                         'AdminLTE card-primary must be removed')
        self.assertNotIn('card-outline', self.content,
                         'AdminLTE card-outline must be removed')

    def test_disbursement_list_removes_content_header(self):
        """Must NOT use AdminLTE content-header."""
        self.assertNotIn('content-header', self.content,
                         'AdminLTE content-header must be removed')

    def test_disbursement_list_removes_adminlte_badges(self):
        """Must NOT use AdminLTE badge-warning/badge-success/badge-danger."""
        self.assertNotIn('badge-warning', self.content,
                         'AdminLTE badge-warning must be removed')
        self.assertNotIn('badge badge-success', self.content,
                         'AdminLTE badge-success must be removed')
        self.assertNotIn('badge badge-danger', self.content,
                         'AdminLTE badge-danger must be removed')

    # ── Context variables preserved ──

    def test_disbursement_list_preserves_disbursements_loop(self):
        """disbursements for loop must be preserved."""
        self.assertIn('{% for item in disbursements %}', self.content,
                      'disbursements iteration must be preserved')

    def test_disbursement_list_preserves_context_vars(self):
        """Key context variables must be preserved."""
        self.assertIn('item.amount', self.content)
        self.assertIn('item.created_at', self.content)
        self.assertIn('item.status', self.content)
        self.assertIn('item.method.bank.title', self.content)
        self.assertIn('item.method.account_number', self.content)
        self.assertIn('item.processed_at', self.content)

    def test_disbursement_list_preserves_url_tags(self):
        """URL tags must be preserved."""
        self.assertIn("{% url 'dashboard:dashboard' %}", self.content)
        self.assertIn("{% url 'banking:disbursement_create' %}", self.content)

    def test_disbursement_list_extends_correct_base(self):
        """Must extend dashboard/layouts/base.html."""
        self.assertIn("{% extends 'dashboard/layouts/base.html' %}", self.content)


# ══════════════════════════════════════════════════════════════════════
# T5.2b: Disbursement Form Template
# ══════════════════════════════════════════════════════════════════════

class DisbursementFormTemplateTests(TestCase):
    """T5.2: Verify banking/disbursement_form.html uses design-system classes."""

    @property
    def content(self):
        return _read_template('banking', 'banking/disbursement_form.html')

    # ── Design-system classes present ──

    def test_disbursement_form_has_card_modern(self):
        """Must use .card-modern for the form wrapper."""
        self.assertIn('card-modern', self.content,
                      'disbursement_form.html must contain card-modern class')

    def test_disbursement_form_has_form_styling(self):
        """Form fields must be styled via CSS block targeting form controls."""
        has_styling = (
            '{% block css %}' in self.content or
            'form.' in self.content
        )
        self.assertTrue(has_styling,
                        'disbursement_form.html must style form controls')

    def test_disbursement_form_has_btn_primary_auth(self):
        """Submit button must use .btn-primary-auth."""
        self.assertIn('btn-primary-auth', self.content,
                      'disbursement_form.html must use btn-primary-auth')

    # ── AdminLTE classes removed ──

    def test_disbursement_form_removes_small_box(self):
        """Must NOT use AdminLTE small-box."""
        self.assertNotIn('small-box', self.content,
                         'AdminLTE small-box must be replaced with card-stat')

    def test_disbursement_form_removes_card_outline(self):
        """Must NOT use AdminLTE card-outline."""
        self.assertNotIn('card-outline', self.content,
                         'AdminLTE card-outline must be removed')

    def test_disbursement_form_removes_content_header(self):
        """Must NOT use AdminLTE content-header."""
        self.assertNotIn('content-header', self.content,
                         'AdminLTE content-header must be removed')

    def test_disbursement_form_uses_card_stat(self):
        """Balance display must use .card-stat."""
        self.assertIn('card-stat', self.content,
                      'disbursement_form.html must use card-stat for balance')

    # ── Context variables preserved ──

    def test_disbursement_form_preserves_form_fields(self):
        """All form fields must be preserved."""
        self.assertIn('{{ form.amount }}', self.content)
        self.assertIn('{{ form.method }}', self.content)

    def test_disbursement_form_preserves_csrf(self):
        """CSRF token must be preserved."""
        self.assertIn('{% csrf_token %}', self.content)

    def test_disbursement_form_preserves_balance(self):
        """Available balance display must be preserved."""
        self.assertIn('request.user.customuser.available_balance', self.content)

    def test_disbursement_form_preserves_url_tags(self):
        """URL tags must be preserved."""
        self.assertIn("{% url 'banking:disbursement_list' %}", self.content)
        self.assertIn("{% url 'banking:config' %}", self.content)

    def test_disbursement_form_extends_correct_base(self):
        """Must extend dashboard/layouts/base.html."""
        self.assertIn("{% extends 'dashboard/layouts/base.html' %}", self.content)


# ══════════════════════════════════════════════════════════════════════
# T5.3a: Admin Bank List Template
# ══════════════════════════════════════════════════════════════════════

class AdminBankListTemplateTests(TestCase):
    """T5.3: Verify banking/admin/bank_list.html uses design-system classes."""
    template_path = 'banking/admin/bank_list.html'

    @property
    def content(self):
        return _read_template('banking', self.template_path)

    # ── Design-system classes present ──

    def test_bank_list_has_table_modern(self):
        """Must use .table-modern for the bank table."""
        self.assertIn('table-modern', self.content,
                      'bank_list.html must contain table-modern class')

    def test_bank_list_has_btn_secondary(self):
        """Action buttons must use .btn-secondary."""
        self.assertIn('btn-secondary', self.content,
                      'bank_list.html must use btn-secondary for edit/delete')

    # ── AdminLTE classes removed ──

    def test_bank_list_removes_card_primary(self):
        """Must NOT use AdminLTE card-primary/card-outline."""
        self.assertNotIn('card-primary', self.content,
                         'AdminLTE card-primary must be removed')
        self.assertNotIn('card-outline', self.content,
                         'AdminLTE card-outline must be removed')

    def test_bank_list_removes_content_header(self):
        """Must NOT use AdminLTE content-header."""
        self.assertNotIn('content-header', self.content,
                         'AdminLTE content-header must be removed')

    def test_bank_list_removes_table_striped(self):
        """Must NOT use Bootstrap table-striped."""
        self.assertNotIn('table-striped', self.content,
                         'Bootstrap table-striped must be replaced with table-modern')

    # ── Admin indicator ──

    def test_bank_list_has_admin_indicator(self):
        """Admin pages must have a subtle visual admin indicator."""
        has_admin = ('Admin' in self.content or
                     'admin' in self.content.lower() and 'badge' in self.content.lower())
        extra_found = ('text-danger' in self.content or 'text-warning' in self.content)
        self.assertTrue(has_admin or extra_found,
                        'bank_list.html must have an admin indicator (badge/Admin text)')

    # ── Context variables preserved ──

    def test_bank_list_preserves_banks_loop(self):
        """banks for loop must be preserved."""
        self.assertIn('{% for bank in banks %}', self.content,
                      'banks iteration must be preserved')

    def test_bank_list_preserves_context_vars(self):
        """Key context variables must be preserved."""
        self.assertIn('bank.id', self.content)
        self.assertIn('bank.title', self.content)

    def test_bank_list_preserves_url_tags(self):
        """URL tags must be preserved."""
        self.assertIn("{% url 'banking:bank_create' %}", self.content)

    def test_bank_list_extends_correct_base(self):
        """Must extend dashboard/layouts/base.html."""
        self.assertIn("{% extends 'dashboard/layouts/base.html' %}", self.content)


# ══════════════════════════════════════════════════════════════════════
# T5.3b: Admin Bank Form Template
# ══════════════════════════════════════════════════════════════════════

class AdminBankFormTemplateTests(TestCase):
    """T5.3: Verify banking/admin/bank_form.html uses design-system classes."""

    @property
    def content(self):
        return _read_template('banking', 'banking/admin/bank_form.html')

    # ── Design-system classes present ──

    def test_bank_form_has_card_modern(self):
        """Must use .card-modern for the form wrapper."""
        self.assertIn('card-modern', self.content,
                      'bank_form.html must contain card-modern class')

    def test_bank_form_has_form_styling(self):
        """Form field must be styled via CSS block targeting form controls."""
        has_styling = (
            '{% block css %}' in self.content or
            'form.' in self.content
        )
        self.assertTrue(has_styling,
                        'bank_form.html must style form controls')

    def test_bank_form_has_btn_primary_auth(self):
        """Submit button must use .btn-primary-auth."""
        self.assertIn('btn-primary-auth', self.content,
                      'bank_form.html must use btn-primary-auth')

    # ── AdminLTE classes removed ──

    def test_bank_form_removes_card_success(self):
        """Must NOT use AdminLTE card-success."""
        self.assertNotIn('card-success', self.content,
                         'AdminLTE card-success must be removed')

    def test_bank_form_removes_content_header(self):
        """Must NOT use AdminLTE content-header."""
        self.assertNotIn('content-header', self.content,
                         'AdminLTE content-header must be removed')

    # ── Admin indicator ──

    def test_bank_form_has_admin_indicator(self):
        """Admin pages must have a subtle visual admin indicator."""
        has_admin = (
            'Admin' in self.content or
            'Administración' in self.content or
            ('text-danger' in self.content and 'badge' in self.content.lower())
        )
        self.assertTrue(has_admin,
                        'bank_form.html must have an admin indicator')

    # ── Context variables preserved ──

    def test_bank_form_preserves_form_fields(self):
        """form.title field must be preserved."""
        self.assertIn('{{ form.title }}', self.content)

    def test_bank_form_preserves_csrf(self):
        """CSRF token must be preserved."""
        self.assertIn('{% csrf_token %}', self.content)

    def test_bank_form_preserves_url_tags(self):
        """URL tags must be preserved."""
        self.assertIn("{% url 'banking:bank_list' %}", self.content)

    def test_bank_form_preserves_field_errors(self):
        """Field error handling must be preserved."""
        self.assertIn('form.title.errors', self.content)

    def test_bank_form_extends_correct_base(self):
        """Must extend dashboard/layouts/base.html."""
        self.assertIn("{% extends 'dashboard/layouts/base.html' %}", self.content)


# ══════════════════════════════════════════════════════════════════════
# T5.4a: Admin Disbursement List Template
# ══════════════════════════════════════════════════════════════════════

class AdminDisbursementListTemplateTests(TestCase):
    """T5.4: Verify banking/admin/disbursement_list.html uses design-system classes."""

    @property
    def content(self):
        return _read_template('banking', 'banking/admin/disbursement_list.html')

    # ── Design-system classes present ──

    def test_admin_disbursement_list_has_table_modern(self):
        """Must use .table-modern for the disbursement table."""
        self.assertIn('table-modern', self.content,
                      'disbursement_list.html must contain table-modern class')

    def test_admin_disbursement_list_has_badge_status(self):
        """Must use .badge-status pills for approval states."""
        self.assertIn('badge-status', self.content,
                      'disbursement_list.html must use badge-status')

    def test_admin_disbursement_list_has_btn_primary_auth(self):
        """Review button must use .btn-primary-auth."""
        self.assertIn('btn-primary-auth', self.content,
                      'disbursement_list.html must use btn-primary-auth for review CTA')

    # ── AdminLTE classes removed ──

    def test_admin_disbursement_list_removes_card_warning_outline(self):
        """Must NOT use AdminLTE card-warning/card-outline."""
        self.assertNotIn('card-warning', self.content,
                         'AdminLTE card-warning must be removed')
        self.assertNotIn('card-outline', self.content,
                         'AdminLTE card-outline must be removed')

    def test_admin_disbursement_list_removes_content_header(self):
        """Must NOT use AdminLTE content-header."""
        self.assertNotIn('content-header', self.content,
                         'AdminLTE content-header must be removed')

    def test_admin_disbursement_list_removes_table_striped(self):
        """Must NOT use Bootstrap table-striped."""
        self.assertNotIn('table-striped', self.content,
                         'Bootstrap table-striped must be replaced with table-modern')

    # ── Context variables preserved ──

    def test_admin_disbursement_list_preserves_disbursements_loop(self):
        """disbursements for loop must be preserved."""
        self.assertIn('{% for item in disbursements %}', self.content,
                      'disbursements iteration must be preserved')

    def test_admin_disbursement_list_preserves_context_vars(self):
        """Key context variables must be preserved."""
        self.assertIn('item.vendor.user.get_full_name', self.content)
        self.assertIn('item.vendor.user.email', self.content)
        self.assertIn('item.amount', self.content)
        self.assertIn('item.created_at', self.content)
        self.assertIn('item.method.bank.title', self.content)

    def test_admin_disbursement_list_preserves_url_tags(self):
        """URL tags must be preserved."""
        self.assertIn("{% url 'banking:admin_disbursement_process' item.id %}", self.content)

    def test_admin_disbursement_list_extends_correct_base(self):
        """Must extend dashboard/layouts/base.html."""
        self.assertIn("{% extends 'dashboard/layouts/base.html' %}", self.content)


# ══════════════════════════════════════════════════════════════════════
# T5.4b: Admin Disbursement Detail Template
# ══════════════════════════════════════════════════════════════════════

class AdminDisbursementDetailTemplateTests(TestCase):
    """T5.4: Verify banking/admin/disbursement_detail.html uses design-system classes."""

    @property
    def content(self):
        return _read_template('banking', 'banking/admin/disbursement_detail.html')

    # ── Design-system classes present ──

    def test_disbursement_detail_has_card_modern(self):
        """Must use .card-modern for info cards."""
        self.assertIn('card-modern', self.content,
                      'disbursement_detail.html must contain card-modern class')

    # ── AdminLTE classes removed ──

    def test_disbursement_detail_removes_card_outline(self):
        """Must NOT use AdminLTE card-outline."""
        self.assertNotIn('card-outline', self.content,
                         'AdminLTE card-outline must be removed')

    def test_disbursement_detail_removes_content_header(self):
        """Must NOT use AdminLTE content-header."""
        self.assertNotIn('content-header', self.content,
                         'AdminLTE content-header must be removed')

    def test_disbursement_detail_removes_profile_classes(self):
        """Must NOT use AdminLTE box-profile/profile-username."""
        self.assertNotIn('box-profile', self.content,
                         'AdminLTE box-profile must be removed')
        self.assertNotIn('profile-username', self.content,
                         'AdminLTE profile-username must be removed')

    def test_disbursement_detail_removes_list_groups(self):
        """Must NOT use AdminLTE list-group-unbordered."""
        self.assertNotIn('list-group-unbordered', self.content,
                         'AdminLTE list-group-unbordered must be removed')

    # ── Context variables preserved ──

    def test_disbursement_detail_preserves_vendor_info(self):
        """Vendor info context vars must be preserved."""
        self.assertIn('disbursement.vendor.user.get_full_name', self.content)
        self.assertIn('disbursement.vendor.user.email', self.content)
        self.assertIn('disbursement.vendor.available_balance', self.content)

    def test_disbursement_detail_preserves_bank_info(self):
        """Bank detail context vars must be preserved."""
        self.assertIn('disbursement.method.bank.title', self.content)
        self.assertIn('disbursement.method.get_account_type_display', self.content)
        self.assertIn('disbursement.method.account_number', self.content)
        self.assertIn('disbursement.method.fullname', self.content)

    def test_disbursement_detail_preserves_amount(self):
        """amount context var must be preserved."""
        self.assertIn('disbursement.amount', self.content)

    def test_disbursement_detail_preserves_action_buttons(self):
        """Approve/reject action buttons must be preserved."""
        self.assertIn('action', self.content,
                      'Form action field must be preserved for approve/reject')
        self.assertIn('approve', self.content,
                      'Approve action must be preserved')
        self.assertIn('reject', self.content,
                      'Reject action must be preserved')

    def test_disbursement_detail_preserves_csrf(self):
        """CSRF token must be preserved."""
        self.assertIn('{% csrf_token %}', self.content)

    def test_disbursement_detail_preserves_rejection_reason(self):
        """rejection_reason textarea must be preserved."""
        self.assertIn('rejection_reason', self.content)

    def test_disbursement_detail_preserves_confirm_js(self):
        """Confirmation dialogs must be preserved."""
        self.assertIn('confirm(', self.content)

    def test_disbursement_detail_preserves_url_tags(self):
        """URL tags must be preserved."""
        self.assertIn("{% url 'banking:admin_disbursement_list' %}", self.content)

    def test_disbursement_detail_extends_correct_base(self):
        """Must extend dashboard/layouts/base.html."""
        self.assertIn("{% extends 'dashboard/layouts/base.html' %}", self.content)
