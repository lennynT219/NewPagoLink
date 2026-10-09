# Choose an environment template safely

The generated root files `env.fase1`, `env.fase2`, and `env.production` are nonsecret skeletons, ignored by Git and created with permissions `0600`. They become private as soon as you fill them. Never paste keys into chat, logs, docs or commits; never force-add these files. Merely copying a skeleton does **not** make it usable or certify production readiness.

## Choose and complete privately

| File | Purpose | Required operator work |
|---|---|---|
| `env.fase1` | Local integrator test; `test.oppwa.com`, empty test mode | Fresh private Django secret and dedicated Phase 1 entity/auth credentials; no Phase 2 fallback or MID/TID |
| `env.fase2` | Local merchant test; `eu-test.oppwa.com`, `EXTERNAL` | Fresh private Django secret and Phase 2 entity/auth/MID/TID; confirm merchant metadata |
| `env.production` | Strict production; `eu-prod.oppwa.com` root without `/v1`, empty test mode | Fresh random secret (at least 50 characters), exact domains, PostgreSQL/TLS/CA, Resend sender/key, distinct production entity/auth/MID/TID and provider-confirmed cart basis |

Fill private values **once in the chosen variant**, replacing every `REPLACE_` marker. Keep credential sets separate: never mix Phase 1, Phase 2 and production keys. Clear conflicting inherited process variables; exported values take precedence over dotenv values.

Local profiles use automatic SQLite and console email; the reserved `example.invalid` sender is harmless, not a verified delivery domain. No SMTP secrets or obsolete database variables are needed. `TAX_IVA=0.12` preserves the existing default. For the local USD 1 / no-IVA pilot, configure the **link's tax as zero**, not the global tax setting. Phase 2 `gross` is only that pilot's local choice, not a generally certified policy. Known ECI `0103910`, PSERV `17913101` and prior public merchant name `ADREST` must be confirmed with DATAFAST and replaced if assigned differently. Production requires an explicit provider-confirmed `net` or `gross` choice.

## Activate manually (operator only)

1. Privately back up any current `.env` **outside Git** before overwriting it. The agent does not read, copy or rename your actual `.env`.
2. After filling and checking the chosen variant, manually copy it to the exact root filename **`.env`** (with the dot). Copying keeps the variants for later switching; renaming is an operator alternative.
3. For example, this ordinary command works in fish and is **human-only**:

   ```fish
   cp env.fase1 .env
   chmod 600 .env
   ```

   Select `env.fase2` or `env.production` instead when appropriate. Do not `source` dotenv files in fish.
4. For **either local test mode**, after private configuration is complete, use:

   ```fish
   env -u DJANGO_ENV .venv/bin/python -B manage.py runserver 127.0.0.1:8000
   ```

   Only when `DJANGO_ENV` is absent from the **process environment** does settings read `.env`; the profile declared inside that file is then honored. Exporting only `DJANGO_ENV` skips `.env` and leaves the other values missing or inherited. The same legacy `env -u DJANGO_ENV` bootstrap can load a completed production `.env`, but this is **not** a production runserver/deployment recommendation.

For production, prefer supplying the **whole completed configuration** through a protected service `EnvironmentFile` or equivalent service environment, including `DJANGO_ENV=production`. Do not supply just the profile selector. No service, bootstrap, server or deployment has been activated or verified here.

## Check before activation

- [ ] Every placeholder is replaced privately; fresh secrets and the selected mode's credentials are present. Files and private backups remain uncommitted and access-restricted.
- [ ] Provider root, test mode and localhost setting match the selected mode; production localhost is `False`.
- [ ] Production exact host and HTTPS CSRF origins, random secret, real PostgreSQL credentials, URL-escaped password and service-readable CA path are confirmed. `verify-full` requires actual certificate/hostname verification; parsing cannot prove it.
- [ ] Production Resend key and verified sender/domain are configured; provider/domain authentication and delivery are checked externally. If preferring SMTP, change `EMAIL_BACKEND_MODE` to `smtp`, remove `RESEND_API_KEY`, and supply `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_PORT=587`, `EMAIL_USE_TLS=True`, `EMAIL_USE_SSL=False` privately (or port 465, TLS False, SSL True). Do not keep unused SMTP secrets active.
- [ ] DATAFAST confirms identifiers, merchant identity, cart basis, VAT and live credentials; authorized card/provider/browser/reconciliation checks are complete. Templates do not populate payer/customer data or prove certification.
- [ ] HTTPS, proxy and backend ingress are independently checked. Keep `TRUST_CONTROLLED_PROXY=False` until only a controlled proxy reaches the backend and it strips/overwrites both `X-Forwarded-Proto` and `X-Real-IP`. Strict cookies/HTTPS redirect are source-enforced, not extra template flags.
- [ ] HSTS starts at `0` with subdomains/preload `False`; enable progressively only after HTTPS coverage is proven.

See [local sandbox modes](LOCAL_SANDBOX.md) and [production profile and external gates](PRODUCTION_PROFILE.md). Actual infrastructure readiness remains unproven by these templates.
