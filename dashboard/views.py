from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic.edit import FormView

from dashboard import services
from .forms import LoginForm, RegisterForm
from django.contrib.auth import login


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


class ResetPassword(View):
  def get(self, req):
    return render(req, 'reset_password.html')
