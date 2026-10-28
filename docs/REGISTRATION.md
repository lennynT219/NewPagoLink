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
- Phone: exactly 10 ASCII digits, retained as text so an initial zero is not lost.

These checks are not official identity or phone-number verification.
Identification retains its existing numeric field; the profile phone is already
stored in a character field, so preserving submitted phone text needs no schema
change or migration.

Rejected requests return the registration form with errors and do not create
users/profiles or submit activation mail. Relevant messages:
- `Esta identificación ya está registrada.`
- `Este correo ya está en uso.` (existing behavior)
- `El celular admite como máximo 10 caracteres.`
- `Ingresá un teléfono de 10 dígitos.`
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

## Phone and contract preparation

Registration, profile editing and contract preparation use the same ten-digit
contact-phone validator. A profile form with a short or malformed phone returns
an inline field error instead of saving successfully and then failing at the
contract preview. Valid phones keep their initial zero, including on mobile
telephone inputs.

Existing malformed phone values are not rewritten or prefixed automatically.
The account owner must enter their actual ten-digit phone through the profile
form (`Completar mi perfil`). A valid profile can display the contract preview;
this does not accept it. Consent, preview validation, ownership, declared legal
identity and previously accepted evidence remain unchanged.

## Verification

`dashboard.test_registration_integrity` exercises the public registration
endpoint and creation service against isolated state, including duplicate
identity, existing email, storage bounds, uniqueness conflicts, rollback,
non-disclosure, and one secure activation message for a valid registration.
`dashboard.test_onboarding_phone` covers registration-to-profile-to-contract,
invalid contact rejection without partial saves, and owner-driven correction of
a synthetic legacy phone without automatically accepting the contract.
`dashboard.test_onboarding_boundaries` also pins ASCII/length boundaries,
read-only identity fields and preservation of historical acceptance evidence.
Use the isolated test profile, locmem email, and blocked networking; do not
probe registration by creating real production accounts.
