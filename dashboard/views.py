from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views import View
from django.views.generic.edit import FormView
from dashboard import services
from .forms import LoginForm, RegisterForm
from django.contrib.auth import get_user_model, login
from .tokens import account_activation_token
from .services import RedirectIfAuth, login_redirect_url


class Register(RedirectIfAuth, FormView):
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
    except (TypeError, ValueError, OverflowError, self.User.DoesNotExist) as e:
      user = None
    if user is not None and account_activation_token.check_token(user, token):
      user.is_active = True
      user.save()
      login(req, user)

      return render(req, self.template_name_success)
    else:
      return render(req, self.template_name_invalid)


class Login(RedirectIfAuth, FormView):
  template_name = 'login.html'
  form_class = LoginForm

  def get_form_kwargs(self):
    kwargs = super().get_form_kwargs()
    kwargs['request'] = self.request
    return kwargs

  def form_valid(self, form):
    user = form.get_user()
    login(self.request, user)
    redirect_url = login_redirect_url(user)
    messages.success(self.request, f'¡Bienvenido de nuevo, {user.first_name or user.username}!')
    return redirect(redirect_url)  # type:ignore


class ResetPassword(View):
  def get(self, req):
    return render(req, 'reset_password.html')
