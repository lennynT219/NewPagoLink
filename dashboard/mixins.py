from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.auth.mixins import AccessMixin
from django.urls import reverse_lazy


class RedirectIfAuthMixin:
  redirect_url = reverse_lazy('dashboard:dashboard')

  def dispatch(self, request, *args, **kwargs):
    if request.user.is_authenticated:
      messages.info(request, 'Ya has iniciado sesión.')
      return redirect(self.redirect_url)  # type:ignore
    return super().dispatch(request, *args, **kwargs)  # type:ignore


class ContractRequiredMixin(AccessMixin):
  def dispatch(self, request, *args, **kwargs):
    if not request.user.is_authenticated:
      return self.handle_no_permission()

    if not hasattr(request.user.customuser, 'contract'):
      return redirect(reverse_lazy('dashboard:contract-accept'))  # type:ignore

    return super().dispatch(request, *args, **kwargs)  # type:ignore
