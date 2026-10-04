# Reconcile DATAFAST without resending payments

`datafast_reconcile` previews a bounded set of internal IDs by default. Only
explicit `--apply` performs authenticated GET queries and calls the existing
atomic payment/refund settlers. It never creates a checkout or sends an RF POST.
Unavailable, absent, incomplete or ambiguous results leave funds unresolved.

**Production gate:** representative provider query fixtures, RF query fields,
full JSON envelope, pagination semantics and retention are not certified. The
recognized layouts below are conservative local support, **not a guarantee of
the live provider contract**. Tests use synthetic fixtures, NOT observed live
provider contracts. Production configuration (T5), PostgreSQL contention and
DATAFAST merchant certification remain separate gates.

## Operator quick path

Run only in an approved environment with its existing secured configuration:

```sh
python manage.py datafast_reconcile --limit 50
python manage.py datafast_reconcile --attempt-id 123
python manage.py datafast_reconcile --refund-id 456
# Future operator action, after approval and provider-contract validation:
python manage.py datafast_reconcile --apply --limit 50
```

- `--limit` is 1–200, default 50, across both kinds of records together.
- Repeated `--attempt-id` / `--refund-id` accept positive internal primary keys,
  at most 200 per kind. Supplying either restricts selection to supplied scopes;
  it does not query unrelated records. Provider IDs are not CLI inputs.
- Default mode performs no provider I/O, no client construction and no DB writes.
- Output contains only kind, internal ID, local status, bounded reason and counts.
  It never prints provider payloads, credentials, customer data or exception text.
- Dry-run reasons mean eligibility, not provider approval. Apply `settled` means
  the existing settler returned a terminal local outcome. `non_final`,
  `query_unresolved`, `identity_unavailable` and
  `observation_or_settlement_unavailable` require follow-up, not a resend.

## Selection and identity

| Record | Eligibility and query binding |
|---|---|
| Payment attempt | CREATING/LIVE/UNKNOWN/EXPIRED, pending unsettled payment, no historical Sale. Require stored checkout and merchant identity. Prefer stored provider transaction ID; otherwise query stored merchant identity. |
| Refund | PROCESSING/UNKNOWN with positive full gross hold, matching payment gross, PAID payment and bound seller/original transaction. Prefer stored RF ID. Fallback requires exactly one SUCCEEDED payment attempt bound to the original provider ID, gross, USD and stored checkout; query its stored merchant identity. |
| Legacy/terminal | No inferred IDs, no history backfill. Missing provenance stays unresolved. Paid/refunded/historical payments and terminal refunds are skipped. |

Selection is stable by internal ID, attempts before refunds, globally bounded.
For busy queues, scope refund runs separately to avoid starvation and track
unresolved ages. All GET I/O occurs outside DB transactions; apply rejects an
outer transaction. Existing atomic settlers revalidate current state and retain
the T1 credit/fee and T3 hold/settlement idempotence guards.

## Supported observations (deliberately conservative)

Supported roots are a **complete canonical transaction object**, or
`{"payments": [<complete transactions>]}`. The collection may have only one
additional root key, `result`, whose `code` must be `000.000.000`; optional
`description` is ignored. No envelope result substitutes for transaction fields.
Any other root metadata, including pagination/count/continuation flags, is
unsupported. Empty collections and batches above 100 transactions are rejected;
no pagination is followed and no truncated batch is accepted. The batch limit
applies to decoded record count, not HTTP response bytes.

Each transaction requires safe `id`, `paymentType` DB/RF, positive exact whole-cent
`amount`, `currency` USD and `result.code` in `NNN.NNN.NNN` form. Binary float
amounts are rejected; GET JSON decodes fractional numbers as Decimal.
`result` permits only `code` and optional `description`. DB additionally requires
exact `merchantTransactionId` and cannot carry RF reference fields. RF requires
`referencedId` (or established `referencedid` alias); if both occur they must
agree. RF ID must differ from the original ID. Merchant fallback additionally
requires the RF record's exact queried `merchantTransactionId`. Stored RF-ID
queries do not require an invented merchant field.

The only optional transaction keys are `merchantTransactionId`, reference aliases
(for RF), `resultDetails`, `timestamp`, `paymentBrand` and `descriptor`. These
metadata values are ignored and not forwarded to accounting or emitted. All
other transaction keys are unsupported. Further live layouts require evidence,
additional binding tests and a separately reviewed change, not silent defaults.

Every record must be structurally complete, including a DB/RF sibling. Exactly
one target-type record is required. Properly typed opposite-type siblings may
be ignored; malformed siblings, duplicate IDs, multiple target-type candidates,
foreign identity, conflicting bindings or wrong gross/currency leave unresolved.
No first/latest-record heuristic is used. DB observations match stored merchant,
provider ID when known, type, gross and USD. RF observations match stored RF ID
when known, original referenced ID, type, gross and USD, then use the shared
strict T2 RF normalizer and T3 settler. Unknown codes never imply approval or
decline. Only established exact final codes can settle. Absence/unavailability
never releases a hold. A confirmed full refund consumes the reserved gross
once, preserving Sale history and the USD 0.35 earned fee.

## Future scheduling and monitoring

**No schedule is installed by this change.** After operator approval, live query
contract validation, production configuration and merchant certification, an
operator could install a cron entry using the deployment's secured launcher:

```cron
# Example only: choose approved paths, environment and run frequency first.
*/5 * * * * /approved/app/.venv/bin/python /approved/app/manage.py datafast_reconcile --apply --limit 50
```

Prevent overlapping jobs operationally. Monitor selected/settled/unresolved
counts, oldest open-attempt/held-refund age, provider unavailability, repeated
unresolved internal IDs and starvation. Preserve holds during investigation.
Escalate unresolved records to an authorized operator/provider support; do not
resend RF or manually release funds based on an empty query. Retention is
uncertified: an old missing query is not proof of failure. There is no fabricated
webhook/signature path and no automatic refund retry.

## Evidence and review checklist

Query routes are documented in the official DATAFAST **Verificador de
Transacciones** section, https://developers.datafast.com.ec/Index.aspx, corroborated
by `../docs/Datafast.md:1172–1247`: Bearer-authenticated
`GET /v1/query/{paymentId}?entityId=...` and
`GET /v1/query?entityId=...&merchantTransactionId=...`. Merchant queries may include
DB and RF transactions. The merchant ID is a URL-encoded parameter, never a path.
HTTPS, TLS verification, disabled redirects and a ten-second timeout are required.
No live query, real apply, schedule, installation or deployment was performed.

- [ ] Validate representative production DB/RF envelopes and pagination/retention.
- [ ] Verify binding failures and unavailability retain funds; no RF POST occurs.
- [ ] Verify dry-run is read-only and scoped apply uses only existing settlers.
- [ ] Approve production configuration, scheduling and unresolved-hold monitoring.
