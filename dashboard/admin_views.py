from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView

from accounts.admin_roles import grant_platform_admin
from dashboard.mixins import AdminRequiredMixin


class AdministratorGrantForm(forms.Form):
  email = forms.EmailField(label='Correo del usuario', max_length=254)
  confirm = forms.BooleanField(label='Confirmo otorgar acceso administrativo a este usuario.')


class AdministratorRowGrantForm(AdministratorGrantForm):
  user_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput)


class PlatformAdminView(LoginRequiredMixin, AdminRequiredMixin, FormView):
  template_name = 'dashboard/platform_admin.html'
  form_class = AdministratorGrantForm
  success_url = reverse_lazy('dashboard:platform-admin')

  def handle_no_permission(self):
    if not self.request.user.is_authenticated:
      return redirect('dashboard:login')
    raise PermissionDenied

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context['summary'] = User.objects.aggregate(
      total=Count('pk'), active=Count('pk', filter=Q(is_active=True)),
      admins=Count('pk', filter=Q(customuser__is_admin_role=True)),
    )
    return context

  def grant_role(self, form):
    return grant_platform_admin(self.request.user, form.cleaned_data['email'])

  def form_valid(self, form):
    try:
      changed = self.grant_role(form)
    except ValidationError as error:
      form.add_error('email', error)
      return self.form_invalid(form)
    message = (
      'El usuario ahora es administrador de la plataforma.'
      if changed
      else 'El usuario ya es administrador de la plataforma.'
    )
    messages.success(self.request, message)
    return super().form_valid(form)


class PlatformUsersView(PlatformAdminView):
  template_name = 'dashboard/platform_users.html'
  form_class = AdministratorRowGrantForm
  success_url = reverse_lazy('dashboard:platform-users')

  def grant_role(self, form):
    return grant_platform_admin(
      self.request.user, form.cleaned_data['email'], expected_user_id=form.cleaned_data['user_id'],
    )

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    search = self.request.GET.get('q', '').strip()[:100]
    users = User.objects.select_related('customuser').order_by('username', 'pk')
    if search:
      users = users.filter(
        Q(username__icontains=search) | Q(email__icontains=search)
        | Q(first_name__icontains=search) | Q(last_name__icontains=search)
      )
    context.update(search=search, page_obj=Paginator(users, 20).get_page(self.request.GET.get('page')))
    return context
