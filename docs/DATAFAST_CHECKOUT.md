# Capture actual DATAFAST payer data

New provider checkout preparation requires the actual payer's mandatory data. The seller's profile and invitation details are not proof of payer identity. T5b1 captures, validates and persists payer data; T5b2 sends the stored tax breakdown, explicit merchant metadata and actual aggregate charge. Neither certifies legal readiness or provider acceptance.

## Checkout path

1. The payer supplies their first and second given names, surname, email, identification document, phone, billing street/country and delivery street/country.
2. Delivery may reuse billing only when the payer explicitly confirms that both street and country are the same. No country, city, postcode or address is inferred from the seller.
3. Django validates the form server-side and displays Spanish errors. The service revalidates before reservation/I/O and stores validated data before the SDK request. The SDK independently rejects incomplete, malformed or placeholder data before POST.
4. Buyer identity freezes after the first persisted attempt, including expired or declined attempts. An open attempt is reused without replacing its buyer or IP. A newly prepared retry keeps the recorded payer reference and identity, and records the actual current request IP. Browser results do not post money directly; the existing bound server-fetched result path remains authoritative.

### Public record selection is not access authority

The public `p` query parameter selects a payment belonging to the link; it is **not** a payer identity credential or permission to read stored payer data. Every public GET renders a blank, unbound checkout form, including invitations, prepared/live, expired, declined, paid and refunded records. Saved names, email, document, phone, addresses and selected countries are never prefilled or disclosed by that GET. Invalid POST forms reflect only that request's submitted values, with no fallback to saved fields. Stored identity, link/payment binding and retry freezing remain unchanged. This does not introduce or claim an authentication token, capability URL or protected payer portal.

### Strict second-name gate

A missing second given name blocks checkout. Do not repeat a first name, invent an alias, or submit SN/NA/default names or addresses. A payer with only one given name needs a separately approved DATAFAST Risks exception and explicit human authorization before a future change; no exception is assumed here. The manual identifies the Risks contact in its mandatory-fields section.

## Persisted fields and SDK mapping

Migration `payments/0007_checkout_payer_data.py` adds six nullable/blank fields only: `buyer_middle_name`, `billing_street`, `shipping_street`, `billing_country`, `shipping_country`, `buyer_client_ip`. It does not backfill existing rows or modify financial history. Invitation buyer fields remain optional until actual checkout. Old paid/refunded records, callbacks, refund settlement and reconciliation do not require the new fields.

| Recorded/input value | Provider field | Contract |
|---|---|---|
| `first_name` | `customer.givenName` | 3–48 characters |
| `buyer_middle_name` | `customer.middleName` | 2–50 characters; mandatory |
| `last_name` | `customer.surname` | 3–48 characters |
| `email` | `customer.email` | Valid email, 6–128 characters |
| `identify` | `customer.identificationDocId` | Actual original stored; provider value normalized below |
| `phone` | `customer.phone` | 7–15 characters; existing storage limit is narrower than the manual's 25 |
| `billing_street`, `shipping_street` | `billing.street1`, `shipping.street1` | Actual printable streets, 1–100 characters |
| `billing_country`, `shipping_country` | `billing.country`, `shipping.country` | Actual uppercase ISO 3166-1 alpha-2 codes; no default |
| Actual request IP | `customer.ip` | Valid single IP under the trust contract below |
| Persisted `Payment.pk` | `customer.merchantCustomerId` | Decimal internal record reference, 1–16 characters |

Names accept alphanumeric characters and spaces. Known placeholder values are rejected, but `SN` (Senegal) and `NA` (Namibia) are valid **countries**, not placeholder country values. The explicit country set has 249 entries. No unsupported optional city/postcode metadata is sent.

For identification, the manual permits left-zero padding of an actual short document to 10 characters, and truncating a 13-digit RUC to its first 10 characters. Original input remains stored. Unsupported 11/12-character documents or nonnumeric 13-character values are rejected instead of silently truncated. Padding is provider normalization, not permission to invent a missing document.

### Recorded guest payer reference

`Payment.pk` is the reference to the guest payer **recorded for that payment**. It is persisted before preparation, stable across that payment's retries and independent of PII. It is not a stable global person identifier, registered-buyer account, seller identity, random/demo ID or constant placeholder. References longer than 16 characters fail before provider I/O. DATAFAST must confirm that these guest-record semantics satisfy its registered-user wording during certification. If a registered-buyer entity is required, that requires separately scoped design/authorization; no entity is invented here.

## Client IP trust

Without controlled-proxy opt-in, use only request `REMOTE_ADDR`; ignore POST IPs, X-Real-IP and X-Forwarded-For. With existing `SECURE_PROXY_SSL_HEADER` opt-in, require a single valid proxy-overwritten X-Real-IP and reject the backend peer as the buyer IP. Never fall back to the backend/server address or an XFF chain. See [the production profile](PRODUCTION_PROFILE.md#proxy-trust-cookies-and-progressive-hsts): enabling proxy trust requires stripping and overwriting **both** X-Forwarded-Proto and X-Real-IP and restricting backend ingress.

Loopback, unspecified, multicast and link-local payer addresses are rejected, including mapped IPv4 forms. Strict staging/production additionally require public IPs. Mocked development tests use explicit documentation-only synthetic addresses. Application parsing cannot certify proxy ingress or prove that an operator supplied the actual frontend client address; that remains an external operational gate.

## Tax, merchant and aggregate-cart contract

All three tax fields are mandatory, formatted with two decimals and no thousands separators. Positive stored `Payment.igv` sends stored `subtotal` as `SHOPPER_VAL_BASEIMP` and stored IVA as `SHOPPER_VAL_IVA`, with `SHOPPER_VAL_BASE0=0.00`. Zero IVA sends subtotal as BASE0 and both other fields as `0.00`. No universal 12%/15% recalculation occurs. Seller-selected VAT 0 and NO_VAT retain the existing non-taxed-base behavior; any provider distinction requires certification, not an invented NO_OBJ API field.

The single cart item represents the **one actual priced payment-link charge**, not a retail catalog. Its name and description are the exact locked `Payment.description`, quantity `1`. Blank, nonprintable, ampersand-containing or over-255-character descriptions fail before attempt reservation; no fabrication, truncation, sanitization or payment/link rewrite occurs. Amount, subtotal and IVA must be finite, nonnegative whole-cent Decimals with exact `subtotal + IVA = amount`. Cart price follows the documented numeric format: 1–10 integer digits and exactly two decimals.

| Explicit variable (empty default in every profile) | Contract |
|---|---|
| `DATAFAST_ECI`, `DATAFAST_PSERV` | Provider-confirmed opaque printable identifiers, no inferred numeric format |
| `DATAFAST_MERCHANT_NAME` | Real registered, approved merchant short name: alphanumeric/spaces, at most 30 characters; not seller/payer data or the UI brand |
| `DATAFAST_CART_PRICE_BASIS` | Exactly `net` (stored subtotal) or `gross` (reserved attempt amount); **no default** |

The manual describes ECI `0103910` and PSERV `17913101` as fixed identifiers. They are not a 3DS authentication ECI such as `07`; obtain confirmed configured values from DATAFAST. Do not infer that these identifiers are always allocated distinctly per merchant. The manual's phase-2 sample MID `1000000406` and TID `PD100406` are rejected by strict production/staging startup: obtain different production MID/TID from DATAFAST.

**Price basis is unresolved in the documentation.** The explicit net/gross switch is an operator choice pending provider confirmation and acceptance/certification, not a claim that the manual specifies either basis. It never changes the buyer total, tax snapshot, commission or ledger. Missing/invalid checkout metadata fails before POST in every profile and at strict startup. RF/query/result methods do not validate these checkout-only fields.

Checkout uses exactly one `Bearer` prefix for raw or already-prefixed tokens, rejects blank/control-character/double-prefix tokens, retains TLS verification by default, sets a 15-second timeout and disables redirects. Root and `/v1/` base URLs resolve to `/v1/checkouts`; non-200 responses cannot supply session IDs. Only explicit `EXTERNAL` on the canonical sandbox sends `testMode`; production omits the field entirely and rejects unsafe test configuration. RF/query headers and payloads remain unchanged.

## Checkout expiration and finalized records

The local no-retry window is 30 minutes from the attempt's **last persisted observation** (`updated_at`), not its initial reservation. Just before that boundary the open attempt is reused; at exactly 30 minutes and afterwards it expires and a new preparation reserves a fresh, unique merchant transaction reference. Later observations conservatively extend this window. Expiration is a local retry decision, not an authoritative provider rejection or refund.

`payments/test_checkout_expiry.py` freezes time and mocks the gateway at one microsecond before, exactly at and one microsecond after the boundary. It also checks the last-observation window and guards paid, refunded and legacy settled-with-Sale records against expiration/recredit. The existing strict comparison already implements this boundary; T6 adds coverage without changing financial runtime behavior. These tests do not prove provider clock timing or PostgreSQL contention.

## Sensitive-data handling and release boundaries

Names, documents, email, phone, addresses and IP are sensitive stored data. Restrict application/DB access and backups to authorized personnel; treat invitation URLs as sensitive, avoid sharing them, and protect exports. Do not log POST bodies, buyer values, provider response bodies, credentials or exception text that may contain them. Checkout/notification failures use sanitized reasons and internal payment references. Deployment logging, error monitoring, retention/deletion and access-control policies require separate operator/legal review; this document is not legal approval or a claim that all repository surfaces have been privacy-audited.

Existing seller-selected gross/subtotal/IVA calculations, Sale/commission history, the retained USD 0.35 fee, RF/query methods and result binding remain unchanged. Mocked tests do not exercise real provider widgets, production PostgreSQL contention, actual proxies or live certification. Obtain representative DATAFAST fixtures and merchant certification before release; provider acceptance/certification remains pending. Follow the [readiness runbook](PRODUCTION_READINESS.md) for staging, backup/restore, rollback and the user's pending functional checks. Repository evidence is not external approval.
