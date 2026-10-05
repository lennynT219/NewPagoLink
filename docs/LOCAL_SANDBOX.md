# Select the DATAFAST environment safely

`DATAFAST_ENVIRONMENT` accepts exactly `phase1`, `phase2`, or `production`. It selects the provider contract, not the application security profile. No agent has read credentials, migrated the real database, or contacted DATAFAST.

## Choose a mode

| Selector | Application profile | Provider root and contract |
|---|---|---|
| `phase1` | `DJANGO_ENV=development`, `DEBUG=True`, non-strict | `https://test.oppwa.com/v1/`; basic integrator checkout; no `testMode` |
| `phase2` | Development, non-strict | `https://eu-test.oppwa.com/v1/`; `DATAFAST_TEST_MODE=EXTERNAL`; full payer/cart/tax/merchant metadata |
| `production` | Strict staging/production, `DEBUG=False` | `https://eu-prod.oppwa.com/v1/`; full metadata; no `testMode`, no localhost flag |

**Absent selector:** development defaults to Phase 2; staging and production default to the production provider. Staging does not acquire a new Phase 2 bypass. Invalid selectors, profile/host mismatches and contradictory test modes fail before provider I/O. The selector alone cannot start production from development or relax secret, database, email, HTTPS or proxy gates.

Development supplies a mode-specific default root; Phase 2 supplies the default `EXTERNAL` test mode. Explicit contradictory configuration is rejected, not ignored. Strict profiles still require an explicit canonical root `https://eu-prod.oppwa.com` under their existing startup policy. Development root, root slash, `/v1` and `/v1/` variants produce the canonical API/widget root.

## Configure privately (operator only)

Export configuration without printing or committing secret values. With `DJANGO_ENV` explicitly exported, settings do not read `.env`. Omitting `DJANGO_ENV` preserves the existing legacy `.env` bootstrap; exported values take precedence. Do not modify private configuration through an agent or bypass its access/write guard.

| Keys | Requirement |
|---|---|
| `SECRET_KEY` | Existing application secret; all existing profile checks still apply. |
| `DATAFAST_PHASE1_ENTITY_ID`, `DATAFAST_PHASE1_AUTH_TOKEN` | Required dedicated Phase 1 credentials. No public defaults or fallback to Phase 2 credentials. |
| `DATAFAST_ENTITY_ID`, `DATAFAST_AUTH_TOKEN`, `DATAFAST_MID`, `DATAFAST_TID` | Required existing merchant-assigned credentials for Phase 2/production. Not required or read from the environment on the Phase 1 path. |
| `DATAFAST_ECI`, `DATAFAST_PSERV` | Explicit provider-approved identifiers for Phase 2/production. |
| `DATAFAST_MERCHANT_NAME` | Registered merchant identity, up to 30 alphanumeric/space characters. |
| `DATAFAST_CART_PRICE_BASIS` | Provider-confirmed `net` or `gross`, not an inferred certification. |

For Phase 1, set `DATAFAST_ENVIRONMENT=phase1`, `DJANGO_ENV=development`, `DEBUG=True`, `EMAIL_BACKEND_MODE=console`, and the two dedicated secrets. Unset an old Phase 2 base/test mode or supply the Phase 1 base with an empty test mode. For Phase 2, select `phase2`, its EU test root, `EXTERNAL`, and the existing complete merchant configuration. Never use production credentials for either test mode.

Phase 1 sends only `entityId`, exact charge `amount`, `currency=USD`, and `paymentType=DB`. It omits Phase 2 payer/cart/tax/merchant metadata. The app still requires real payer input, preserves blank public forms and stores the actual client IP; no identity or IP substitution is introduced. Phase 1 transactions do **not** reach the DATAFAST switch and do not certify Phase 2 processing.

## Localhost and browser checks

`DATAFAST_ALLOW_LOCALHOST=True` permits actual loopback only with `DEBUG=True`, non-strict development and the selected canonical test contract: Phase 1 at `test.oppwa.com` without test mode, or Phase 2 at `eu-test.oppwa.com` with `EXTERNAL`. Actual SDK overrides are checked too. Unspecified, multicast and link-local addresses remain forbidden; strict profiles reject localhost opt-in at startup.

- [ ] Use the selected host's `/v1/paymentWidgets.js` and the exact created checkout ID.
- [ ] Confirm the public form reveals no saved payer data and displays clear validation errors.
- [ ] With opt-in off, local POST rejects loopback without a provider call.
- [ ] Supply actual payer information; do not invent merchant metadata or a public IP.
- [ ] Confirm provider-approved HTTPS/TLS 1.2 even for tests. Plain HTTP `runserver` is not certification; do not disable TLS verification or expose DEBUG publicly.

The manual limits Phase 2 tests to USD 50 or less; this change does not introduce a production amount cap. Tax calculations and the USD 0.35 seller fee remain unchanged.

## Attempt binding and refunds

New attempts persist an independent `PaymentAttempt.environment` creation snapshot. Changing today's selector cannot reuse, query or apply results to another mode's attempt. Mutable JSON history is not mode evidence. The migration leaves older attempts blank rather than guessing their origin.

Only a newly Phase 1-bound attempt under active Phase 1 conditions can accept official `000.100.110` with absent `merchantTransactionId`. Callback checkout/path binding, safe provider ID uniqueness, exact amount, USD and DB are still required. A supplied mismatching (including null) merchant ID is rejected. Phase 2/production always require the original full merchant binding; production never approves test connector codes. Blank legacy attempts may retain that full-bound Phase 2/production result compatibility, but can never become Phase 1.

**Phase 1 refunds are unsupported and fail before reservation/provider POST.** Under valid active Phase 2/production profile, host and authorization configuration, legacy PAID payments remain refund-eligible with blank attempt environments or no historical attempt, as before. No origin is inferred from JSON history or backfilled. Any nonblank conflicting payment-attempt environment denies RF; an unrelated blank attempt cannot override the original transaction's pin. Existing paid/ownership, exact amount/USD, original transaction/provider ID, outcome/result-code binding, gross holds, retained USD 0.35 fee, accounting, replay and idempotency rules remain required. Already-held legacy PROCESSING/UNKNOWN refunds may settle only validated bound CONFIRMED/DECLINED terminal observations, once and without another RF POST. Malformed, unbound or nonfinal responses retain the hold; UNKNOWN is never permission to retry or release money. This preserves compatibility, not production certification or reclassification of `800.100.100`.

External functional checks remain operator-owned: verify HTTPS, approved credentials, separate Phase 2 test cards, provider acceptance and reconciliation. Mocked deterministic tests prove none of these external conditions.

Reference: [official DATAFAST manual](https://developers.datafast.com.ec/Index.aspx#anexo_i_edited).
