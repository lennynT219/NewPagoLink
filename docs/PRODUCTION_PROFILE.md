# Compile a safe production profile

Use exported configuration, PostgreSQL TLS and an explicit mail provider before deploying. Passing repository checks is **not** infrastructure readiness or DATAFAST certification. Checkout/customer/tax alignment and production payload test-mode omission remain T5b; live certification remains required.

This is the canonical replacement for older deployment/email notes. Existing untracked `DEPLOYMENT.md`, `EMAIL_CONFIGURATION.md`, Resend notes and DigitalOcean instructions may describe obsolete `DB_NAME` settings, manual settings edits or ad-hoc Gunicorn installs. They are not updated by this work.

## Quick path

1. Provision a supported Python runtime and a project-local virtual environment separately. The verified local runtime was Python 3.14.7. Do not download a runtime implicitly.
2. Install the reviewed lock with `uv sync --locked --no-dev --no-python-downloads --default-index https://pypi.org/simple`. For a shared **local** venv use `--inexact` to retain extra human tools; a dedicated deployment venv should match the lock exactly. Gunicorn and psycopg binary are runtime dependencies; pip-audit is dev-only.
3. Supply the variables below through a protected service environment. Never commit actual secrets. Restrict secret-file permissions to the service account (e.g. 0600), rotate compromised keys and avoid logging environment/database URLs. Explicit profiles do **not** read the project's development `.env`; no `DJANGO_ENV` preserves the old local bootstrap.
4. Run `.venv/bin/python -B manage.py check --deploy` with the intended configuration. Startup validates configuration without opening a PostgreSQL connection. A check can still import the application; use the isolated fake-profile procedure below for repository verification.
5. Only after external gates pass, use `.venv/bin/gunicorn pagolink.wsgi:application --bind 127.0.0.1:8000` behind a controlled HTTPS proxy. This example does not install units, cron jobs, certificates or services. Select worker count/timeouts from measured load; do not expose the backend port publicly.

## Required exported configuration

All values here are placeholders, **not deployable credentials**. `DJANGO_ENV` accepts exactly `development`, `staging` or `production`. Staging applies the same strict financial/security rules as production.

| Variable | Example / rule |
|---|---|
| `DJANGO_ENV`, `DEBUG` | `production`, `False`; invalid boolean values fail closed |
| `SECRET_KEY` | Generate a random secret with at least 50 characters and sufficient diversity; no `django-insecure-` prefix |
| `ALLOWED_HOSTS` | `app.example.com`; comma-separated exact hosts, no wildcards, schemes or leading-dot suffix policies |
| `CSRF_TRUSTED_ORIGINS` | `https://app.example.com`; exact HTTPS root origins only |
| `DATABASE_URL` | `postgresql://FAKE_USER:FAKE_PASSWORD@db.example.com:5432/FAKE_DB?sslmode=verify-full&sslrootcert=/operator/path/ca.pem` |
| `DEFAULT_FROM_EMAIL` | `PagoLink <noreply@example.com>`; sender must be verified by your provider |
| `DATAFAST_BASE_URL` | `https://eu-prod.oppwa.com` (root, optionally trailing `/`); no `/v1/`, userinfo, foreign host, query or fragment |
| `DATAFAST_ENTITY_ID`, `DATAFAST_AUTH_TOKEN`, `DATAFAST_MID`, `DATAFAST_TID` | Operator-provided merchant credentials; no production defaults |
| `DATAFAST_TEST_MODE` | Omit it entirely (empty accepted); `EXTERNAL` and `INTERNAL` fail startup |

### Fake exported-profile example

The canonical example lives in this Markdown guide rather than a separate environment-example file. This shell-format block shows the complete SMTP profile; do not deploy the fake credentials or source private files during repository checks.

```sh
export DJANGO_ENV=production
export DEBUG=False
export SECRET_KEY='FAKE_ONLY_REPLACE_WITH_A_RANDOM_SECRET_AT_LEAST_50_CHARACTERS'
export ALLOWED_HOSTS=app.example.com
export CSRF_TRUSTED_ORIGINS=https://app.example.com
export DATABASE_URL='postgresql://FAKE_USER:FAKE_PASSWORD@db.example.com:5432/FAKE_DB?sslmode=verify-full&sslrootcert=/operator/path/ca.pem'
export DEFAULT_FROM_EMAIL='PagoLink <noreply@example.com>'
export EMAIL_BACKEND_MODE=smtp
export EMAIL_HOST=smtp.example.com
export EMAIL_HOST_USER=FAKE_SMTP_USER
export EMAIL_HOST_PASSWORD=FAKE_SMTP_PASSWORD
export EMAIL_PORT=587
export EMAIL_USE_TLS=True
export EMAIL_USE_SSL=False
export DATAFAST_BASE_URL=https://eu-prod.oppwa.com
export DATAFAST_ENTITY_ID=FAKE_ENTITY
export DATAFAST_AUTH_TOKEN=FAKE_TOKEN
export DATAFAST_MID=FAKE_MID
export DATAFAST_TID=FAKE_TID
# Omit DATAFAST_TEST_MODE; remove any inherited test-mode value.
unset DATAFAST_TEST_MODE
export TRUST_CONTROLLED_PROXY=False
export SECURE_HSTS_SECONDS=0
export SECURE_HSTS_INCLUDE_SUBDOMAINS=False
export SECURE_HSTS_PRELOAD=False
# Alternative mail profile: replace SMTP mode with these two exports:
# export EMAIL_BACKEND_MODE=resend
# export RESEND_API_KEY=FAKE_RESEND_KEY
```

The fake defaults deliberately retain progressive HSTS warnings until an operator verifies HTTPS. SMTP versus Resend is an explicit deployment choice, not a provider guessed by startup.

The strict DATAFAST allowlist deliberately uses the existing canonical EU production host. DATAFAST also documents `test.oppwa.com` / `oppwa.com`, but alias acceptance is not expanded here because T1's sandbox policy and T5b payload policy must remain aligned. Development retains fake credentials and explicit `EXTERNAL` with `https://eu-test.oppwa.com`. No tax-policy change is made here.

### PostgreSQL and TLS

Only `postgresql://` / `postgres://` URLs are accepted in strict profiles. URL-escape credential characters (`@` becomes `%40`); parsing decodes them without logging values. Supply database, user, password and host; port defaults to 5432. Only unique `sslmode` and optional `sslrootcert` query parameters are allowed. SQLite, missing/insecure TLS modes, duplicate/conflicting parameters and arbitrary libpq options fail closed.

Prefer `sslmode=verify-full` and an operator-managed CA file: it verifies certificate and hostname. `verify-ca` verifies the chain but not hostname. Both require explicit `sslrootcert` in this profile. `require` enforces encryption but is weaker identity assurance and is accepted for documented transitional setups. The compiler does not validate CA-file existence, server reachability, certificate validity or credentials. PostgreSQL row-lock contention and real TLS connection tests remain external gates; development/test SQLite is not proof of production concurrency.

### Choose SMTP or Resend explicitly

Neither production nor staging defaults to console or guesses a provider.

| Mode | Required values | Backend |
|---|---|---|
| `EMAIL_BACKEND_MODE=smtp` | `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`; port defaults to 587 | Django SMTP |
| `EMAIL_BACKEND_MODE=resend` | `RESEND_API_KEY`, `DEFAULT_FROM_EMAIL` | Existing `anymail.backends.resend.EmailBackend` |

SMTP defaults: `EMAIL_USE_TLS=True`, `EMAIL_USE_SSL=False`, timeout 30 seconds. For implicit TLS set `EMAIL_USE_TLS=False`, `EMAIL_USE_SSL=True`, `EMAIL_PORT=465`. Enabling both or disabling both fails strict startup. Port must be 1–65535. Do not test by actually sending mail during repository checks. Tests compile both backends with fake credentials; functional tests use locmem. Provider/domain verification, SPF/DKIM/DMARC and delivery must be verified separately.

## Proxy trust, cookies and progressive HSTS

Strict profiles enforce SSL redirect, secure session/CSRF cookies, HttpOnly sessions and SameSite **Lax**. Avoid blindly changing to Strict: checkout/browser returns must be tested.

`TRUST_CONTROLLED_PROXY=False` is the default. Checkout uses only the actual request `REMOTE_ADDR`; client-posted IPs, `X-Forwarded-For` and `X-Real-IP` are ignored. Enable proxy trust only when the application is reachable **solely** through an operator-controlled proxy. The proxy must strip incoming **both `X-Forwarded-Proto` and `X-Real-IP`**, then overwrite them with the observed frontend scheme and actual client IP respectively. Never append or retain client-provided values. It enables `SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https')`, which also signals the checkout IP trust opt-in; this is no longer a TLS-only contract.

With that opt-in, checkout requires exactly one valid `X-Real-IP`. Missing/malformed/list-valued headers or a value matching the backend peer fail closed: there is no fallback to the proxy/server address or the first `X-Forwarded-For` entry. Strict staging/production also reject nonpublic, loopback and unspecified payer IPs. Restrict backend ingress; otherwise forged headers could bypass these assumptions. For multi-proxy deployments, the operator must establish the actual frontend client identity before overwriting headers; forwarding a chain is not accepted. Gunicorn's forwarding settings require the same ingress/trust review. Test actual headers, redirects and certificates in authorized staging; no infrastructure verification has occurred here. See [payer checkout](DATAFAST_CHECKOUT.md) for the stored-data and certification boundaries.

| HSTS variable | Initial default | Operator progression |
|---|---|---|
| `SECURE_HSTS_SECONDS` | `0` | Verify HTTPS, then short TTL such as 3600, gradually increase |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `False` | Only after every subdomain is permanently HTTPS-capable |
| `SECURE_HSTS_PRELOAD` | `False` | Explicit long-term operator choice; understand removal delays before preload submission |

Django may emit W004/W005/W021 during a deliberate staged rollout. Do not silence them by blindly committing an irreversible policy. A fully explicit **fake** test profile uses 31536000 seconds and enables both flags solely to exercise a zero-warning `check --deploy`. This is not a recommendation to preload the real domain.

## Isolated repository verification

`pagolink/test_production_settings.py` supplies only fake exported variables and blocks `socket.connect`, `connect_ex` and `create_connection` **before Django imports**. It instantiates the installed PostgreSQL/psycopg backend, confirms `connection.connection is None`, tests SMTP and Resend compilation and runs deployment security checks. It does not replace the production database with SQLite. Legacy `.env` bootstrap is tested with the environment reader mocked, never the actual secret file.

For focused functional regressions, the parent-authorized wrapper sets explicit development variables, replaces the database with in-memory SQLite and email with locmem, and blocks all sockets. Schema consistency uses `makemigrations --check --dry-run --skip-checks` under that same isolated wrapper, not real migrations.

### Dependency evidence and audit results

Observed local lock/setup: Django **5.2.17** (`>=5.2.8,<5.3`), Gunicorn **23.0.0**, psycopg/binary **3.3.6**, pip-audit **2.10.1** (dev). Framework stays in the 5.2 patch lane. Installation used public PyPI, no-config/no-cache, no Python downloads and inexact sync into the existing `.venv`; no global installs.

Audit only locked **production** dependencies, never extra/private installed packages:

```sh
env -i PATH=/usr/bin:/bin HOME="$PWD/.venv" TMPDIR="$PWD/.venv" /usr/bin/uv --no-config --no-cache export --locked --offline --no-dev --no-emit-project --no-hashes --no-annotate --no-header --default-index https://pypi.org/simple --no-python-downloads --python .venv/bin/python --output-file .venv/production-audit.txt
env -i PATH=/usr/bin:/bin HOME="$PWD/.venv" TMPDIR="$PWD/.venv" PYTHONDONTWRITEBYTECODE=1 .venv/bin/pip-audit -r .venv/production-audit.txt --no-deps --disable-pip --strict --progress-spinner off --cache-dir .venv/audit-cache --index-url https://pypi.org/simple --vulnerability-service pypi --format json --desc off --aliases on
```

Run tools in a sanitized environment with public indexes, disabled keyring, protected project-local cache/temp paths and no inherited private index configuration. Export contains public package names/versions only. No `--fix` was used. The offline-compatible `--dry-run` CLI path collected 34 platform-applicable packages; its "No known vulnerabilities" message is **not a scan**.

The initial actual PyPI advisory scan failed: **21 advisory rows across four packages**, including duplicate advisory rows (14 unique primary IDs). The human explicitly authorized the following exact transitive updates; scoped resolution and inexact sync changed **only these four package versions**, preserving Django 5.2.17, Gunicorn 23.0.0, psycopg/binary 3.3.6 and pip-audit 2.10.1. Exact UV constraints now protect this bounded remediation. Historical findings and applied versions:

| Locked package | Required version reported | IDs (deduplicated) |
|---|---|---|
| anyio 4.13.0 | 4.14.2 | CVE-2026-63374, CVE-2026-64847 |
| idna 3.11 | 3.15 | CVE-2026-45409 |
| sqlparse 0.5.3 | 0.6.0 (one advisory also reports 0.5.4) | CVE-2026-71491, CVE-2026-59894, CVE-2026-59893, CVE-2026-54284, CVE-2026-84305, GHSA-27jp-wm6q-gp25 |
| urllib3 2.6.3 | 2.8.0 (older advisories report 2.7.0) | CVE-2026-44431, CVE-2026-44432, CVE-2026-97689, CVE-2026-97688, CVE-2026-97687 |

The repeated locked-production export still contains 35 requirement entries; 34 apply to this CPython/Linux environment (Windows-only tzdata is excluded). The actual repeated PyPI scan exited **0**, auditing all 34 applicable packages with **zero vulnerability rows or CVE IDs** and no automatic fixes. Pip-audit warns that unhashed `--no-deps` requirements are weaker than a fully hashed audit input; this input is an exact-version export from the reviewed hash-bearing UV lock, not an installed-environment scan. No unrelated/private venv metadata was audited. Audit evidence is time-sensitive, not a permanent security guarantee.

The earlier setup attempt with `--no-build` failed because existing `standardwebhooks` has no wheel; retrying without that flag succeeded before this follow-up. The follow-up did not repeat that failed attempt or install a Python runtime. After these four security updates, observed blocked-network checks exited 0: seven profile tests passed separately, all 282 focused regressions passed, schema consistency reported no changes, and fake production `check --deploy --fail-level WARNING` reported zero issues with the installed PostgreSQL backend and `connection=None`. Development regression tests used in-memory SQLite and locmem; production startup did not override PostgreSQL. Independent candidate verification remains parent-owned.

## External release gates

- [x] Apply the four explicitly approved security updates and repeat the locked-production audit (34 packages, zero findings).
- [ ] Independently verify the frozen T5a candidate and rerun the audit at release time.
- [ ] Complete T5b checkout/customer/tax policy and production payload test-mode omission.
- [ ] Verify real PostgreSQL contention, TLS/CA/hostname and least-privilege database permissions.
- [ ] Verify actual proxy ingress/header overwrite, HTTPS certificates, cookies and browser returns.
- [ ] Verify chosen mail provider/domain and delivery in authorized staging.
- [ ] Verify backup/restore, rollback, static serving, monitoring and scheduling in T6.
- [ ] Obtain DATAFAST representative fixtures and live merchant certification.

No database connections, provider/refund calls, mail sends, infrastructure installation or deployment are authorized by these repository checks.
