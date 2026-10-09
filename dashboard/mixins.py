from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import HttpRequest
from django.shortcuts import redirect

from accounts.contracts import has_current_acceptance


class ContractRequiredMixin(UserPassesTestMixin):
  """Asegura que el usuario tenga un contrato aceptado."""

  request: HttpRequest

  def test_func(self):
    return has_current_acceptance(getattr(self.request.user, 'customuser', None))

  def handle_no_permission(self):
    return redirect('dashboard:contract')


class RedirectIfAuthMixin:
  """Redirige al dashboard si el usuario ya está autenticado."""

  def dispatch(self, request, *args, **kwargs):
    if request.user.is_authenticated:
      return redirect('dashboard:dashboard')
    return super().dispatch(request, *args, **kwargs)  # type: ignore


class AdminRequiredMixin(UserPassesTestMixin):
  """Mixin para restringir el acceso únicamente a usuarios con el rol administrativo de la App."""

  def test_func(self):
    user = self.request.user
    return user.is_active and hasattr(user, 'customuser') and user.customuser.is_admin_role

  def handle_no_permission(self):
    return redirect('dashboard:dashboard')
