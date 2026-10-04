# Run the local app against DATAFAST sandbox

Use the existing approved **sandbox** credentials unchanged. Localhost support is an explicit development-only opt-in, not an offline simulator or proof that DATAFAST accepts localhost. Agents have not read credentials or contacted the provider.

## Quick path (operator only)

1. Confirm the account/credentials are sandbox credentials with DATAFAST. Approval alone does not establish this. Keep secrets out of screenshots, HTML and source control.
2. Ensure the existing local configuration has the required metadata below. Do not invent payer identity, merchant name, IP or a certified cart price basis.
3. From the repository root, start the local UI with the existing virtualenv:

   ```bash
   env -u DJANGO_ENV DEBUG=True EMAIL_BACKEND_MODE=console \
     DATAFAST_ALLOW_LOCALHOST=True \
     DATAFAST_BASE_URL=https://eu-test.oppwa.com DATAFAST_TEST_MODE=EXTERNAL \
     .venv/bin/python -B manage.py runserver 127.0.0.1:8000
   ```

   This is an operator command, **not run by the agent**. It uses the existing local database and can initiate real sandbox requests when you submit checkout. Console mail avoids external email delivery; do not share console output containing payer data.

   `env -u DJANGO_ENV` preserves the legacy `.env` bootstrap: explicitly exporting `DJANGO_ENV=development` would skip that file. The file must select development (or omit `DJANGO_ENV`); a staging/production profile rejects the localhost flag. Exported command values take precedence over `.env`; existing credentials are not replaced by this command. No file needs to be printed or shared.
4. Open the local checkout. Use actual payer data; a public invitation GET deliberately leaves the form blank. Email/account readonly policy is unchanged. Submit only after confirming the sandbox account and amount.

> **HTTP is not certified:** `runserver` serves plain HTTP for local UI checks. The official manual requires the merchant site to use HTTPS/TLS 1.2 even in tests. Arrange an approved HTTPS local setup and confirm DATAFAST acceptance before claiming a functional payment test. Do not expose a DEBUG server publicly. The opt-in only changes the app's loopback rejection; it cannot guarantee provider acceptance.

## Required configuration

| Keys | Requirement |
|---|---|
| `SECRET_KEY` | Existing local application secret; never publish it. |
| `DATAFAST_ENTITY_ID`, `DATAFAST_AUTH_TOKEN`, `DATAFAST_MID`, `DATAFAST_TID` | Existing provider-approved sandbox credentials; no placeholders or production credentials. |
| `DATAFAST_ECI` | Explicit identifier. Official manual describes mandatory fixed `0103910`; verify applicability with DATAFAST. |
| `DATAFAST_PSERV` | Explicit identifier. Official manual describes mandatory fixed `17913101`; verify applicability with DATAFAST. |
| `DATAFAST_MERCHANT_NAME` | Explicit registered merchant identity (up to 30 alphanumeric/space characters), not a guessed UI brand. |
| `DATAFAST_CART_PRICE_BASIS` | Explicit provider-confirmed `net` or `gross`. The manual does not resolve this choice; neither is automatically certified. |

The root, root slash, `/v1` and `/v1/` sandbox base variants all produce `/v1/paymentWidgets.js`. The actual checkout ID and payment result binding are preserved.

For a small approved test, consider a **USD 1.00 no-IVA charge**, only if that tax treatment is appropriate: subtotal and total coincide, so net/gross prices coincide without deciding certification. The manual limits phase-two tests to **USD 50 or less**. This guide does not impose a new production amount cap or change tax/fee calculations.

## Understand a rejection

| Feedback | Action |
|---|---|
| Required/invalid field | Supply actual payer data. Native browser validation may stop submission before the server receives it. |
| IP/localhost error | Check all opt-in gates below; do not substitute a public IP or trust arbitrary forwarded headers. |
| Missing/invalid configuration key | Supply or correct that named key privately. Responses show key names, never secret values. No checkout attempt is reserved for preflight failures. |
| Unconfirmed attempt | Do not blindly resubmit; follow existing reconciliation/support instructions. |

Loopback is permitted **only** when `DATAFAST_ALLOW_LOCALHOST=True`, `DEBUG=True`, non-strict development, canonical HTTPS `eu-test.oppwa.com` (no alternate port/host), and `EXTERNAL` mode all hold. The SDK also checks its actual client configuration, not just global settings. IPv4, IPv6 and IPv4-mapped loopback retain their actual address. Unspecified, multicast and link-local addresses remain rejected. Staging/production startup rejects the enabled flag, and strict SDK validation still rejects loopback.

## Browser checklist

- [ ] Blank public GET reveals no saved payer data.
- [ ] Missing/invalid inputs have understandable native validation or a prominent linked server error summary.
- [ ] With opt-in off, local POST displays IP rejection and never calls the provider.
- [ ] With all gates on, the widget script uses `/v1/paymentWidgets.js` and the correct checkout ID.
- [ ] Confirm HTTPS, sandbox account, provider acceptance and final reconciliation separately; none were verified by mocked tests.

Reference: [official DATAFAST manual](https://developers.datafast.com.ec/Index.aspx). Remove the local opt-in before any staging/production setup; production readiness remains a separate work unit.
