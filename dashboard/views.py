from typing import cast
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views import View
from django.views.generic import RedirectView, TemplateView
from django.views.generic.edit import FormView
from .mixins import ContractRequiredMixin, RedirectIfAuthMixin
from .models import Contract, CustomUser
from .forms import LoginForm, RegisterForm
from django.contrib.auth import get_user_model, login, logout
from .tokens import account_activation_token
from . import services


class Register(RedirectIfAuthMixin, FormView):
  template_name = 'register.html'
  form_class = RegisterForm
  success_url = reverse_lazy('dashboard:login')

  def form_valid(self, form):
    user = services.create_user(form.cleaned_data)
    services.send_activation_email(user, self.request)
    return super().form_valid(form)


class ActivateAccount(View):
  template_name_success = 'activation_success.html'
  template_name_invalid = 'activation_invalid.html'
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
      login(req, user)

      return render(req, self.template_name_success)
    else:
      return render(req, self.template_name_invalid)


class Login(RedirectIfAuthMixin, FormView):
  template_name = 'login.html'
  form_class = LoginForm

  def get_form_kwargs(self):
    kwargs = super().get_form_kwargs()
    kwargs['request'] = self.request
    return kwargs

  def form_valid(self, form):
    user = form.get_user()
    login(self.request, user)
    redirect_url = services.login_redirect_url(user)
    messages.success(self.request, f'¡Bienvenido de nuevo, {user.first_name or user.username}!')
    return redirect(redirect_url)


class Dashboard(LoginRequiredMixin, ContractRequiredMixin, TemplateView):
  template_name = 'dashboard.html'

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    current_user = cast(CustomUser, self.request.user)
    stats = services.get_dashboard_stats(current_user)

    if stats:
      context.update(stats)

    return context


class ContractAccept(LoginRequiredMixin, View):
  template_name = 'dashboard/contract.html'
  success_url = reverse_lazy('dashboard:index')  # A dónde va después de aceptar

  def get(self, request, *args, **kwargs):
    if hasattr(request.user.customuser, 'contract'):
      return redirect(self.success_url)  # type:ignore

    return render(request, self.template_name)

  def post(self, request, *args, **kwargs):
    if hasattr(request.user.customuser, 'contract'):
      return redirect(self.success_url)  # type:ignore

    client_ip = services.get_client_ip(request)
    city = services.get_location_from_ip(client_ip)

    Contract.objects.create(seller=request.user.customuser, ip=client_ip, city=city)  # type:ignore

    return redirect(self.success_url)  # type:ignore


class Logout(RedirectView):
  url = reverse_lazy('dashboard:login')  # type:ignore

  def get(self, req, *args, **kwargs):
    if req.user.is_authenticated:
      logout(req)
    return super().get(req, *args, **kwargs)


class ResetPassword(View):
  def get(self, req):
    return render(req, 'reset_password.html')
