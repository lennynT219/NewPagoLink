from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import UpdateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth.models import User
from .forms import UserProfileForm
from dashboard.mixins import ContractRequiredMixin

class ProfileUpdateView(LoginRequiredMixin, ContractRequiredMixin, UpdateView):
  """Vista para actualizar los datos del perfil del vendedor."""
  model = User
  form_class = UserProfileForm
  template_name = 'accounts/profile_form.html'
  success_url = reverse_lazy('dashboard:dashboard')

  def get_object(self, queryset=None):
    return self.request.user

  def form_valid(self, form):
    messages.success(self.request, "Tus datos han sido actualizados correctamente.")
    return super().form_valid(form)
