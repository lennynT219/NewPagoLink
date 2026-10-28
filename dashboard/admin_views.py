from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView

from accounts.admin_roles import grant_platform_admin
from dashboard.mixins import AdminRequiredMixin


class AdministratorGrantForm(forms.Form):
  email = forms.EmailField(label='Correo del usuario', max_length=254)
  confirm = forms.BooleanField(label='Confirmo otorgar acceso administrativo a este usuario.')


class PlatformAdminView(LoginRequiredMixin, AdminRequiredMixin, FormView):
  template_name = 'dashboard/platform_admin.html'
  form_class = AdministratorGrantForm
  success_url = reverse_lazy('dashboard:platform-admin')

  def handle_no_permission(self):
    if not self.request.user.is_authenticated:
      return redirect('dashboard:login')
    raise PermissionDenied

  def form_valid(self, form):
    try:
      changed = grant_platform_admin(self.request.user, form.cleaned_data['email'])
    except ValidationError as error:
      form.add_error('email', error)
      return self.form_invalid(form)
    message = (
      'El usuario ahora es administrador de la plataforma.'
      if changed else 'El usuario ya es administrador de la plataforma.'
    )
    messages.success(self.request, message)
    return super().form_valid(form)
