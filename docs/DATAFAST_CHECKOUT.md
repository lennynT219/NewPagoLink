# Capture actual DATAFAST payer data

New provider checkout preparation requires the actual payer's mandatory data. The seller's profile and invitation details are not proof of payer identity. T5b1 adds capture, validation and persistence; it does **not** certify legal readiness or complete the provider integration. Tax/merchant metadata/auth payload alignment remains T5b2.

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

## Sensitive-data handling and release boundaries

Names, documents, email, phone, addresses and IP are sensitive stored data. Restrict application/DB access and backups to authorized personnel; treat invitation URLs as sensitive, avoid sharing them, and protect exports. Do not log POST bodies, buyer values, provider response bodies, credentials or exception text that may contain them. Checkout/notification failures use sanitized reasons and internal payment references. Deployment logging, error monitoring, retention/deletion and access-control policies require separate operator/legal review; this document is not legal approval or a claim that all repository surfaces have been privacy-audited.

Existing seller-selected gross/subtotal/IVA calculations, Sale/commission history, the retained USD 0.35 fee, RF/query methods and result binding remain unchanged. Mocked tests do not exercise real provider widgets, production PostgreSQL contention, actual proxies or live certification. Obtain representative DATAFAST fixtures and merchant certification before release; T5b2 and T6 operational gates remain pending.
