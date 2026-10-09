from typing import cast

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views import View
from django.views.generic import RedirectView, TemplateView
from django.views.generic.edit import FormView

from accounts.contracts import has_current_acceptance, record_current_acceptance
from accounts.models import CustomUser
from accounts.personalized_contract import (
  PREVIEW_SESSION_KEY,
  IncompleteContractProfile,
  personalized_contract,
  prepare_preview,
  validated_preview,
)
from accounts.tokens import account_activation_token

from . import services
from .forms import ContractAcceptanceForm, LoginForm, RegisterForm
from .mixins import ContractRequiredMixin, RedirectIfAuthMixin


class Register(RedirectIfAuthMixin, FormView):
  template_name = 'dashboard/auth.html'
  form_class = RegisterForm
  success_url = reverse_lazy('dashboard:login')

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context['login_form'] = LoginForm()
    context['register_form'] = context.pop('form', self.get_form())
    context['active_tab'] = 'register'
    return context

  def form_valid(self, form):
    user = services.create_user(form.cleaned_data)
    services.send_activation_email(user, self.request)
    return super().form_valid(form)

  def form_invalid(self, form):
    context = self.get_context_data(form=form)
    context['register_form'] = form
    return self.render_to_response(context)


class ActivateAccount(View):
  template_name_success = 'dashboard/activation_success.html'
  template_name_invalid = 'dashboard/activation_invalid.html'
  User = get_user_model()

  def get(self, req, uidb64, token, *args, **kwargs):
    try:
      uid = force_str(urlsafe_base64_decode(uidb64))
      user = self.User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, self.User.DoesNotExist):
      user = None
    if user is not None and account_activation_token.check_token(user, token):
      user.is_active = True
      user.save()

      # Activamos también el flag en nuestro modelo de negocio
      profile = CustomUser.objects.filter(user=user).first()
      if profile is not None:
        profile.email_active = True
        profile.save()

      login(req, user)
      return render(req, self.template_name_success)
    else:
      return render(req, self.template_name_invalid)


class Login(RedirectIfAuthMixin, FormView):
  template_name = 'dashboard/auth.html'
  form_class = LoginForm

  def get_form_kwargs(self):
    kwargs = super().get_form_kwargs()
    kwargs['request'] = self.request
    return kwargs

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context['register_form'] = RegisterForm()
    context['login_form'] = context.pop('form', self.get_form())
    context['active_tab'] = 'login'
    return context

  def form_valid(self, form):
    user = form.get_user()
    login(self.request, user)
    redirect_url = services.login_redirect_url(user)
    messages.success(self.request, f'¡Bienvenido de nuevo, {user.first_name or user.username}!')
    return redirect(redirect_url)

  def form_invalid(self, form):
    context = self.get_context_data(form=form)
    context['login_form'] = form
    return self.render_to_response(context)


class Dashboard(LoginRequiredMixin, ContractRequiredMixin, TemplateView):
  template_name = 'dashboard/dashboard.html'

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    current_user = cast(CustomUser, self.request.user.customuser)  # type: ignore
    stats = services.get_dashboard_stats(current_user)

    if stats:
      context.update(stats)

    # Forzar el estado real del objeto de usuario actual
    context['email_active'] = current_user.email_active
    context['active'] = current_user.state

    return context


class ContractAccept(LoginRequiredMixin, View):
  template_name = 'dashboard/contract.html'
  login_url = reverse_lazy('dashboard:login')
  success_url = reverse_lazy('dashboard:dashboard')

  def render_terms(self, request, seller, form=None, contract=None):
    context = {'acceptance_form': form}
    try:
      contract = contract or personalized_contract(seller)
    except IncompleteContractProfile as error:
      request.session.pop(PREVIEW_SESSION_KEY, None)
      context['profile_error'] = error.messages[0]
    except ImproperlyConfigured:
      request.session.pop(PREVIEW_SESSION_KEY, None)
      context['provider_error'] = (
        'El contrato no está disponible. Contactá al administrador para revisar los datos del prestador.'
      )
    else:
      context.update(
        contract_blocks=contract.blocks,
        contract_version=contract.version,
        contract_hash=contract.text_hash,
        preview_token=prepare_preview(request, seller, contract),
      )
    return render(request, self.template_name, context)

  def get(self, request, *args, **kwargs):
    seller = getattr(request.user, 'customuser', None)
    if seller is None:
      return redirect('dashboard:login')
    if has_current_acceptance(seller):
      return redirect(str(self.success_url))
    return self.render_terms(request, seller)

  def post(self, request, *args, **kwargs):
    seller = getattr(request.user, 'customuser', None)
    if seller is None:
      return redirect('dashboard:login')
    if has_current_acceptance(seller):
      return redirect(str(self.success_url))
    form = ContractAcceptanceForm(request.POST)
    try:
      contract = personalized_contract(seller)
    except (IncompleteContractProfile, ImproperlyConfigured):
      return self.render_terms(request, seller, form)
    preview = validated_preview(request, seller, contract, request.POST) if form.is_valid() else None
    if preview is None:
      if not form.non_field_errors():
        form.add_error(
          None,
          'Debe aceptar explícitamente el contrato vigente. La vista previa cambió o venció; revisá el texto actualizado.',
        )
      return self.render_terms(request, seller, form, contract)
    record_current_acceptance(seller, ip=services.get_client_ip(request), preview=preview)
    request.session.pop(PREVIEW_SESSION_KEY, None)
    return redirect(str(self.success_url))


class Logout(RedirectView):
  url = reverse_lazy('dashboard:login')  # type:ignore

  def get(self, req, *args, **kwargs):
    if req.user.is_authenticated:
      logout(req)
    return super().get(req, *args, **kwargs)


class ResetPassword(View):
  def get(self, req):
    return render(req, 'dashboard/reset_password.html')
