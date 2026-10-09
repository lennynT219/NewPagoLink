from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from accounts.merchant_profile import CONTRACT_PROFILE_FIELDS, missing_contract_profile_fields

from .forms import UserProfileForm


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
  """Owner-bound profile preparation remains available before acceptance."""

  model = User
  form_class = UserProfileForm
  template_name = 'accounts/profile_form.html'
  success_url = reverse_lazy('dashboard:dashboard')

  def get_object(self, queryset=None):
    return self.request.user

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    seller = getattr(self.request.user, 'customuser', None)
    missing = missing_contract_profile_fields(seller)
    context['missing_commerce_fields'] = tuple(CONTRACT_PROFILE_FIELDS[name] for name in missing)
    return context

  def form_valid(self, form):
    messages.success(self.request, 'Tus datos han sido actualizados correctamente.')
    return super().form_valid(form)
