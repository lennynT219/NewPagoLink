# Platform administration

## Separate platform and merchant access

An active user with `CustomUser.is_admin_role=True` lands at
`/dashboard/administracion/`, without completing a merchant profile or accepting
a seller contract. An existing authenticated session uses the same destination.

Django `is_staff` and `is_superuser` remain separate technical permissions.
Staff-only users retain their existing Django admin destination. When an account
also has the application administrator role, application login prefers the
platform panel; explicit `/admin/` access still follows Django permissions.

The default administrator landing is a styled overview with live account counts
and links to existing administration modules, not the user-management form.
The sidebar exposes a separate **Usuarios** entry at
`/dashboard/administracion/usuarios/`, plus existing bank, refund, and disbursement administration. It does not show personal sales,
withdrawal, or merchant-onboarding actions. This changes presentation, not the
commercial authorization rules: direct payment-link creation still requires
the merchant contract. Creating links for another merchant is not implemented.

## Grant another user the application administrator role

1. Sign in as an application administrator.
2. Open **Usuarios** in the sidebar.
3. Find the account by name, username, or email. The list is paginated at 20 rows.
4. Expand **Hacer administrador** on the selected user's row.
5. Read the permission notice, select its confirmation checkbox, and submit
   **Confirmar administrador**. Existing administrators and ineligible accounts
   show their status instead of a promotion form.

The directory uses the application's navy/teal palette, stat cards, table,
buttons, role/status indicators, search, and empty state. Small screens retain
scrollable table access and a stacked toolbar; confirmation works without JavaScript.
The original email-based POST endpoint remains compatible, but is no longer
presented as the default landing screen.

The new administrator can grant this same role to other users. Only delegate it
to trusted operators: it also enables the application's existing administrative
operations. Unknown, inactive, missing-profile, and ambiguous email matches are
rejected without a role change. Email matching is case-insensitive.

Each row binds the displayed account ID and email; stale or mismatched row
identities are rejected instead of granting a different account.
The action requires a CSRF-protected POST and changes only `is_admin_role`.
It does not activate accounts, assign Django staff/superuser permissions, create
users, accept contracts, or change balances. A successful new grant records the
actor and target profile in Django's existing admin log in the same transaction.
Repeating a grant is a no-op, without a duplicate audit entry.

There is no public self-enrollment or role-revocation control in this delivery.
A first administrator must be bootstrapped by an explicitly authorized operator
against a unique existing account; never expose a public bootstrap endpoint.
The existing role policy uses auth `User.is_active`; it does not redefine the
separate merchant-profile `state` field.

## Verification

`dashboard.test_platform_admin` covers login and navigation, missing merchant
onboarding, delegated promotion, rejected and CSRF-less requests, idempotence,
audit rollback, unchanged account permissions, and preserved merchant gates.
Run with the project's isolated test profile, never against production data.
