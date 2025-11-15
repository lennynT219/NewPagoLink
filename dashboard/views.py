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


class Register(FormView):
  template_name = 'register.html'
  form_class = RegisterForm
  success_url = reverse_lazy('dashboard:login')

  def dispatch(self, req, *args, **kwargs):
    if req.user.is_authenticated:
      return redirect('dashboard:dashboard')
    return super().dispatch(req, *args, **kwargs)

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


class Login(FormView):
  template_name = 'login.html'
  form_class = LoginForm
  success_url = reverse_lazy('dashboard')

  def dispatch(self, req, *args, **kwargs):
    if req.user.is_authenticated:
      return redirect('dashboard')
    return super().dispatch(req, *args, **kwargs)

  def form_valid(self, form):
    user = form.cleaned_data['user']
    login(self.request, user)
    return HttpResponseRedirect(form.cleaned_data['redirect_to'])


class ResetPassword(View):
  def get(self, req):
    return render(req, 'reset_password.html')
