# Registration integrity

## Account creation

A successful registration saves both Django's inactive `User` and its
`CustomUser` profile in one database transaction. An unsuccessful profile save
must not leave a newly created login account behind.

The public registration view submits activation mail only after both saves
succeed. It does not activate the account, assign administrative permissions,
or accept a merchant contract. Mail submission is not proof of inbox delivery;
provider failure handling and the login redirect remain unchanged.

## Validation and rejected requests

The form checks identification uniqueness before persistence. It preserves
the database uniqueness constraint for concurrent registrations.

Storage-compatible limits are checked before saving:
- First and last names: at most 150 characters each.
- Email: at most 150 characters, because it is also the login username.
- Identification: the signed 64-bit range supported by the existing field.
- Phone: at most 10 characters after the existing numeric coercion.

These are storage limits, not official identity or phone-number verification.
The existing numeric field types and stored formats are unchanged.

Rejected requests return the registration form with errors and do not create
users/profiles or submit activation mail. Relevant messages:
- `Esta identificación ya está registrada.`
- `Este correo ya está en uso.` (existing behavior)
- `El celular admite como máximo 10 caracteres.`
- `La identificación está fuera del rango permitido.`
- `Este campo admite como máximo 150 caracteres.`
- `No se pudo completar el registro con estos datos. Revisalos e intentá nuevamente.`

The final message handles an integrity conflict or storage-data rejection
during insertion, after transaction rollback. It never includes raw database
errors, another user's data, or the submitted password.

## Existing incomplete accounts

This change does not alter or remove accounts left incomplete by older code.
An email already present in `User` remains rejected rather than silently
replacing credentials or attaching a profile. Inspect only an explicitly
identified account and obtain separate authorization for any recovery,
deletion, activation, or real resend. Never infer the missing identity/phone.

## Verification

`dashboard.test_registration_integrity` exercises the public registration
endpoint and creation service against isolated state, including duplicate
identity, existing email, storage bounds, uniqueness conflicts, rollback,
non-disclosure, and one secure activation message for a valid registration.
Use the isolated test profile, locmem email, and blocked networking; do not
probe registration by creating real production accounts.
