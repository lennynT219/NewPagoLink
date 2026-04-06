from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect

class ContractRequiredMixin(UserPassesTestMixin):
  """Asegura que el usuario tenga un contrato aceptado."""
  def test_func(self):
    return hasattr(self.request.user.customuser, 'contract') # type: ignore

  def handle_no_permission(self):
    return redirect('dashboard:contract')

class RedirectIfAuthMixin:
  """Redirige al dashboard si el usuario ya está autenticado."""
  def dispatch(self, request, *args, **kwargs):
    if request.user.is_authenticated:
      return redirect('dashboard:dashboard')
    return super().dispatch(request, *args, **kwargs) # type: ignore

class AdminRequiredMixin(UserPassesTestMixin):
  """Mixin para restringir el acceso únicamente a usuarios con el rol administrativo de la App."""
  def test_func(self):
    user = self.request.user
    return user.is_active and hasattr(user, 'customuser') and user.customuser.is_admin_role

  def handle_no_permission(self):
    return redirect('dashboard:dashboard')
