# Bound checkout attempts and one-time seller credit

A newly confirmed DATAFAST debit credits the seller the purchase total minus
USD 0.35. The buyer pays the purchase total only. Existing commissions and sale
records are not backfilled or rewritten.

## Checkout and return path

1. Reserve a `PaymentAttempt` before requesting a checkout. Each attempt has a
   unique `PAY-<UUID>` merchant ID, immutable amount/currency snapshot, optional
   checkout/provider IDs, timestamps and sanitized state history.
2. Reuse the open attempt for the selected payment. A database constraint permits
   only one `CREATING`, `LIVE` or `UNKNOWN` attempt per payment. A creation timeout
   is ambiguous: it does not authorize an immediate replacement checkout.
3. Wait at least 30 minutes after the last local attempt observation before
   expiring it and reserving another. This conservatively covers the documented
   checkout window without counting request latency against it. Repeated result
   observations extend the local wait. Expiry is not proof of decline; retain every
   old mapping so a late, validated success can still settle the payment once.
4. Accept a browser return only when `resourcePath` exactly equals the selected
   payment attempt's stored `/v1/checkouts/{checkoutId}/payment`. Reject URLs,
   query strings, fragments, traversal and cross-payment paths before provider I/O.
   The gateway additionally validates canonical paths and disables GET redirects.

## What authorizes money movement

| Check | Required value |
|---|---|
| Merchant identity | Exact stored attempt merchant ID |
| Amount | Finite exact Decimal, whole cents, equal to both snapshot and payment |
| Currency / type | `USD` / `DB` |
| Provider ID | Nonempty, unclaimed by another payment or attempt |
| Production approval | Exact `000.000.000`; never a substring |
| Test connector approvals | `000.100.110` / `000.100.112` only with explicit test mode on `eu-test.oppwa.com` |

Amounts represented as JSON floats are rejected because fractional precision may
already have been lost. Risk/review codes `000.400.010` and `000.400.020` do not
credit funds. Only explicitly allowlisted documented decline codes mark a failure;
unavailable, malformed, mismatched and non-final results remain unconfirmed.
Validated non-final results retain their provider ID for future reconciliation.

## Financial invariants

- Payment and seller locks plus unique sale/provider constraints protect atomic
  sale creation, USD 0.35 commission and seller balance credit. Constraint conflicts
  roll back the posting rather than partially crediting money.
- Gross below USD 0.35 fails before requesting a checkout. Gross exactly USD 0.35
  has zero seller net; the fee is neither capped nor added to the buyer's amount.
- An existing sale, paid/state flag or refunded status prevents another checkout,
  recredit, confirmation replay or status downgrade. The sale guard also protects
  historical refunds represented by `FAILED` in the legacy implementation.
- Confirmation is attempted only after the new sale commits. Email delivery is not
  guaranteed and cannot roll back or repeat the financial posting.

## Boundaries and review checks

The USD 0.35 fee is retained on refunds by policy; refund execution/accounting is
not implemented here. The reconciliation command, production configuration and
payload certification also remain separate tasks. Stored attempts provide their
inputs; expiry and `UNKNOWN` are not promises of automatic recovery.

Mocked regressions live in `payments/test_financial_integrity.py` and
`gateways/tests.py`. Review fee boundaries, historical-sale guards, identity/amount
mismatches, late results, constraint collisions and canonical-path rejection.
SQLite tests establish deterministic constraints and behavior, not production
multi-connection lock behavior. Validate concurrency on the deployment database
before certification. No real provider requests are needed for these tests.
