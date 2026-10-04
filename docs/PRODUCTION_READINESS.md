# Release only after operational and DATAFAST gates pass

**Not production-certified.** Repository checks use fake configuration, blocked network, in-memory SQLite and locmem mail. They cannot approve a deployment. This checklist is the canonical T6 runbook; it does not authorize any external operation or replace the user's pending functional checks.

## Evidence boundary

| Evidence | Status / limit |
|---|---|
| T1–T5b1 isolated payment, refund, reconciliation and profile checks | Recorded in the [task history](../odd/tasks/datafast-production-hardening.md); not infrastructure proof |
| T5b2 tax/cart/merchant payload | Implemented with mocked-provider evidence; consolidated closing verification remains parent-owned |
| T6 UI contracts and expiry | Deterministic tests in `dashboard/tests.py` and `payments/test_checkout_expiry.py`; focused results belong to the implementation handoff |
| Consolidated full suite, schema and candidate code verification | Pending coordinator closure; no passing result asserted here |
| Real browser, PostgreSQL, provider, mail and operational exercises | **UNVERIFIED**; record dated evidence and responsible approver before release |

## Staging and certification checklist — UNVERIFIED

Obtain separate operator authorization before touching infrastructure or calling providers. Strict `staging` uses the production security/financial profile, including the production-host allowlist and no testMode; it is **not** an automatically safe sandbox. Use only the provider-approved endpoint/account for the approved exercise. Development sandbox fixtures do not certify the strict deployment profile.

- [ ] Record release commit, reviewed lock, runtime, configuration revision, owners and go/no-go approval. Follow [production configuration](PRODUCTION_PROFILE.md), not older untracked deployment notes. Recheck the locked production dependency audit at release time; the historical zero-finding audit is time-sensitive.
- [ ] Obtain provider-confirmed ECI, PSERV, actual registered merchant short name, MID/TID/entity and explicit `net` or `gross` cart-price basis. All four checkout metadata defaults are empty, not demo values. Confirm aggregate-charge descriptions, guest `Payment.pk` reference and strict second-name requirements; never fabricate identity or addresses. See [checkout contract](DATAFAST_CHECKOUT.md).
- [ ] Obtain representative DATAFAST fixtures and merchant certification for preparation, browser return, authoritative query, rejection, timeout/unknown outcome, expiration and RF refund. Confirm unresolved query-root, RF, pagination and retention contracts. Production must omit testMode. No invented webhook/signature or idempotency contract.
- [ ] Verify real PostgreSQL TLS/hostname/CA, least privilege and multi-connection contention: duplicate callbacks, checkout reservation, concurrent refunds and payout/refund seller locking. SQLite cannot establish these properties.
- [ ] Verify HTTPS/proxy-only ingress, overwritten X-Forwarded-Proto and X-Real-IP, actual payer IP, redirects, secure cookies and browser returns on mobile/desktop. Progress HSTS only after HTTPS verification.
- [ ] Verify static assets, process supervision/restart, health checks, sanitized logs/alerts and mail provider/domain delivery. Do not put credentials, payer data or raw provider bodies into tickets or logs.
- [ ] Complete the user's pending functional checks: account navigation/profile save and email presentation; payer validation and public GET privacy; VAT-15 included/excluded, VAT-0 and NO_VAT links; payment retry/return, fee and refund/reconciliation display. Record actual outcomes, not assumptions from tests.

Financial acceptance remains unchanged: buyer pays gross; stored subtotal plus IVA equals gross; a new USD 100 approval credits USD 99.65 once. A full refund returns/debits USD 100 while retaining the original USD 0.35 fee. Failed/pending payments earn no fee. Do not backfill historical Sales or commissions, recalculate tax, or alter pricing to obtain certification.

## Bounded operating runbook

1. **Before enablement:** approve the checklist, rehearse recovery below, record a rollback target and deploy the reviewed artifact/configuration. Operator-only migration/static/startup/deploy checks must use the intended environment; none were run against real services by T6.
2. **Observe:** monitor unresolved payment/refund counts, sanitized result reasons, errors, latency and mail failures. Compare authoritative payment/refund evidence with ledger/Sale records; alerts are not approval evidence.
3. **Reconcile carefully:** `datafast_reconcile` defaults to a bounded preview (`--limit 50`); it reads the configured DB. Only separately authorized `--apply` performs provider GETs and local settlement. Use `--attempt-id` / `--refund-id` for investigation. Confirm query contracts before enabling an operator-managed schedule; start bounded, prevent overlapping jobs and alert on persistent unresolved results.
4. **Unknown outcome:** retain refund holds, inspect stored internal/provider identifiers with restricted access and escalate to the provider. Never resend RF blindly, credit from a browser response, manually release ambiguous holds or invent an approval. Reconciliation is not another refund request.
5. **Incident:** stop new checkout/refund activity and scheduled application of reconciliation through the approved operational control, retain evidence and involve the financial/operator owner. Do not delete attempts, Sales or refund history to clear an alert.

## Backup, restore and rollback checklist — UNVERIFIED

- [ ] Define recovery point/time objectives and retention; encrypt and restrict DB/media/config backups. Keep secret recovery material separate from public release artifacts. Capture a consistent backup before schema/deployment changes and test integrity.
- [ ] Restore into an isolated, access-restricted target with provider/network/mail jobs disabled. Validate schema, record counts and representative payment/Sale/commission/refund-hold balances, including historical paid/refunded records. Record measured recovery time and data-loss window.
- [ ] Rehearse rollback with the exact prior artifact and compatible configuration. Review additive migrations and old-code compatibility before choosing an app rollback; do not assume reversing migrations is safe. Preserve the current financial database unless an explicitly approved recovery plan requires restoration.
- [ ] A DB restore can lose locally recorded approvals/refunds while remote transactions remain real. Freeze financial writes, inventory transactions since the recovery point and reconcile authoritative provider evidence before reopening. Never replay checkout/RF blindly or overwrite history to match a stale backup.
- [ ] Confirm jobs resume only once, health/static/mail checks pass, financial totals reconcile and owners sign off. If any certification or recovery gate fails, remain disabled; rollback is not a certification bypass.

## Next step

The coordinator runs one consolidated isolated closing verification and records its observed results. Operators then collect external evidence and the user completes functional validation. Release is blocked until the applicable unchecked gates have explicit approval; this document makes no deployment or production certification claim.
