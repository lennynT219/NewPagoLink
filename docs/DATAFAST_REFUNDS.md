# DATAFAST RF adapter contract

`DatafastClient.refund_payment` sends one documented RF request and returns a
sanitized outcome. **This adapter alone is not completed refund accounting or
production certification.** It does not reserve funds, change payment status,
release balances, debit sellers, or write audit records. Those belong to T3.

## Calling contract

Pass the persisted approved provider payment ID and a finite, positive,
whole-cent `Decimal` amount. Invalid parameters raise `ValueError` before any
network request. Floats, strings, integers and sub-cent inputs are rejected;
amounts are never rounded to make a mismatched request look valid.

The adapter sends exactly one POST to `/v1/payments/{approved-payment-id}` with
Bearer authorization and `entityId`, `amount`, `currency=USD`, `paymentType=RF`.
TLS verification is enabled, redirects are disabled, timeout is 10 seconds, and
the default Requests adapter has no automatic retries. The base URL must use
HTTPS with no credentials, query, fragment or unrelated path; an origin or
`/v1/` base is accepted. Deployment host/credential validation remains T5.

`testMode=EXTERNAL` is sent only when both the configured authority is exactly
`eu-test.oppwa.com` and the explicit mode is `EXTERNAL`. It is omitted entirely
on production, even when production accidentally inherits that mode.

## Outcomes for the lifecycle caller

| Outcome | Meaning | Caller boundary |
|---------|---------|-----------------|
| `CONFIRMED` | Authoritative, matching RF response with exact success code | T3 must finalize accounting exactly once against its reservation. |
| `DECLINED` | Matching RF response with the narrowly allowed definitive invalid-amount code `800.100.174` | T3 owns reservation disposition and auditing; this adapter changes nothing. |
| `UNKNOWN` | Unavailable, malformed, foreign, non-final or otherwise ambiguous result | Reconcile; do not blindly resend or release reserved funds. |

Confirmation requires all of: a nonempty safe refund `id`, `referencedId`
matching the requested original ID, `paymentType=RF`, `currency=USD`, and an
exact positive whole-cent amount. The archived `referencedid` spelling is also
accepted; conflicting spellings are rejected. JSON fractional numbers are
parsed as `Decimal`, never through binary floats.

The exact production approval code is `000.000.000`. Code `000.100.112` is
accepted only under the explicit sandbox configuration above. No success
prefix, pending family or generic failure family is accepted. The only
`DECLINED` allowlist entry is the documented definitive invalid-amount failure;
it requires the same reference, ID, type, currency and amount validation as a
confirmation. Missing binding fields therefore remain `UNKNOWN`, even with a
decline code.

A bound, well-formed response returns `outcome`, `refund_id`, `original_id`,
`amount` (`Decimal`), `currency`, and `code`. HTTP/transport errors, timeouts,
non-200 responses, JSON errors and invalid binding return only
`{'outcome': 'UNKNOWN'}`. No card/customer payload, provider description or
exception message is returned or logged. Safe fields on an `UNKNOWN` result
are diagnostic evidence, not proof of a completed refund.

In particular, `700.400.200` (refund volume exceeded/already reversed/invalid
workflow) remains reconciliation-needed `UNKNOWN`. A timeout may occur after
the provider processed RF. Neither result authorizes a second request.

## Verification and remaining work

`gateways/test_refunds.py` exercises actual adapter behavior with mocked HTTP,
including no-I/O invalid parameters, exact POST/auth/payload, test-mode gating,
TLS/redirect policy, reference and monetary mismatches, exact codes, and
ambiguous outcomes without a second request. Existing T1 labels remain in the
isolated verification run. No real provider requests are needed for these tests.

T3 must add reservation, gross-funds checks, once-only gross debit, retained
USD 0.35 fee, durable audit and reconciliation handling. PostgreSQL concurrency,
live sandbox/provider certification, staging checks and production configuration
are not proven by this adapter's local tests.

## Contract references

- [Official DATAFAST documentation, Anulaciones](https://developers.datafast.com.ec/Index.aspx)
- Local archived reference: `../docs/Datafast.md`, Anulaciones and result-code tables.

No RV endpoint, webhook signature, idempotency header or settlement window is
assumed by this implementation.
