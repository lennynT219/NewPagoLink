from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import HttpRequest
from django.shortcuts import redirect

from accounts.admin_roles import is_platform_admin
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
      if is_platform_admin(request.user):
        return redirect('dashboard:platform-admin')
      return redirect('dashboard:dashboard')
    return super().dispatch(request, *args, **kwargs)  # type: ignore


class AdminRequiredMixin(UserPassesTestMixin):
  """Mixin para restringir el acceso únicamente a usuarios con el rol administrativo de la App."""

  request: HttpRequest

  def test_func(self):
    user = self.request.user
    return is_platform_admin(user)

  def handle_no_permission(self):
    return redirect('dashboard:dashboard')
