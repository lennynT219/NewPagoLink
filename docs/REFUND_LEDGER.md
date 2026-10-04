# Full refunds reserve gross funds before DATAFAST

A refund request is not an approval. Approval reserves the full purchase amount in the seller ledger, commits that reservation, sends one DATAFAST RF, and settles only a strictly bound provider result. The buyer receives the full purchase total; the seller's earned USD 0.35 fee remains retained.

## Money and states

For a USD 100 purchase, the seller earned USD 99.65. Refunding USD 100 requires an additional USD 0.35 of available funds. Insufficient funds reject approval **before RF**, leaving the request pending. No loan, negative balance, smaller buyer refund, or fee cap is used.

| Refund state | Held amount | Available balance effect | RF retry |
|---|---:|---|---|
| PENDING | 0 | None | First approval only |
| PROCESSING | Gross | Gross already deducted | Never |
| UNKNOWN | Gross | Hold retained | Never |
| APPROVED | 0 | Hold consumed; no second debit | Never |
| REJECTED | 0 | Definitive decline releases gross once | Never |

Confirmed RF sets Payment to REFUNDED and `state=False`. Payment commission and the original Sale, including commission and net proceeds, remain unchanged. Historical Sale evidence prevents late debit callbacks from crediting the payment again. Migration `0006_refund_reservation` adds metadata with zero/empty defaults, not a historical accounting rewrite. Previously approved refunds have no fabricated reservation or retroactive debit.

## Transaction boundaries

1. `approve_refund_logic` locks Payment, Refund, then seller. It rechecks PAID status, seller binding, gross amount, safe original transaction identity, and available funds.
2. It deducts gross from `available_balance`, records `held_amount`, original provider ID, PROCESSING status, initiating administrator and time, and commits before provider I/O. Calls inside an outer transaction or disabled autocommit are rejected.
3. It calls the existing `DatafastClient.refund_payment(original_id, gross)` once outside database locks.
4. `settle_refund` reloads and locks the same ledger rows. It validates original/refund identity, unique refund ID, Decimal gross amount, USD currency and exact outcome/code before consuming or releasing the hold. APPROVED requires CONFIRMED; REJECTED requires the adapter's definitive `800.100.174` decline. Sandbox approval `000.100.112` is accepted only with the exact test host and EXTERNAL mode.

Payout approval already locks the seller and checks/debits the same available balance. It cannot spend reserved funds. Credit locks Payment before seller; refund uses the same relative order. Payout never locks Payment or Refund. SQLite tests prove lifecycle/reentrant behavior, **not PostgreSQL contention**.

## Uncertainty is intentional

Timeouts, malformed/foreign results, exceptions, and non-final codes keep the gross hold. A crash after reservation may leave PROCESSING even if RF was never sent. A database error after RF leaves the committed hold available for reconciliation; repeat approval cannot resend. Audit history stores only internal reasons, validated provider identifiers and result codes, never raw payloads or exception text.

`settle_refund(refund_id, normalized_result)` is a bounded internal seam for T4's server-side reconciliation. It performs no RF call and has no public settlement route. Terminal records are no-ops. A stored provider refund ID cannot be replaced by a foreign observation. A uniqueness race rolls back settlement rather than moving money twice. T4 querying/scheduling is not implemented here; do not manually clear holds or repost RF to recover.

## Review and operation gates

- Check reservation visibility before mocked RF and exact gross debit/release-once behavior in `payments/test_refund_accounting.py`.
- Seller/admin screens show actual persisted status; unresolved admin rows disable resending. Only provider-confirmed results display approval success.
- Verify PostgreSQL contention, browser behavior and provider certification separately before production use.
- Do not roll back the schema while unresolved reservations exist: dropping reservation/audit fields destroys recovery evidence. Resolve holds and plan an accounting-aware rollback first.

Related provider contract: [DATAFAST RF adapter](DATAFAST_REFUNDS.md). Server reconciliation, production configuration and broader UI/test remediation remain T4–T6 work.
