"""Application administrator authorization, separate from Django staff privileges."""

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounts.models import CustomUser


def is_platform_admin(user):
  profile = getattr(user, 'customuser', None)
  return bool(user.is_authenticated and user.is_active and profile and profile.is_admin_role)


@transaction.atomic
def grant_platform_admin(actor, email):
  """Grant only the app role; role and audit evidence succeed or roll back together."""
  if not CustomUser.objects.filter(user=actor, user__is_active=True, is_admin_role=True).exists():
    raise PermissionDenied
  candidates = list(User.objects.select_related('customuser').filter(email__iexact=email)[:2])
  if len(candidates) != 1 or not candidates[0].is_active:
    raise ValidationError('Ingresá el correo de un único usuario activo con perfil registrado.')
  profile = getattr(candidates[0], 'customuser', None)
  if profile is None:
    raise ValidationError('Ingresá el correo de un único usuario activo con perfil registrado.')
  changed = CustomUser.objects.filter(pk=profile.pk, is_admin_role=False).update(is_admin_role=True)
  if changed:
    LogEntry.objects.create(
      user=actor,
      content_type=ContentType.objects.get_for_model(CustomUser),
      object_id=str(profile.pk),
      object_repr=f'User {profile.user.pk}',
      action_flag=CHANGE,
      change_message='[{"changed": {"fields": ["is_admin_role"]}}]',
    )
  return bool(changed)
