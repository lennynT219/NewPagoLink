from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, FormView
from django.urls import reverse_lazy
from django.contrib import messages
from django import forms
from .models import Bank, PaymentMethod
from .forms import PaymentMethodForm
from . import services
from dashboard.mixins import AdminRequiredMixin, ContractRequiredMixin

class PaymentMethodView(LoginRequiredMixin, ContractRequiredMixin, FormView):
  """Vista para configurar y editar los datos bancarios del vendedor."""
  template_name = 'banking/payment_method.html'
  form_class = PaymentMethodForm
  success_url = reverse_lazy('banking:config')

  def get_form_kwargs(self):
    kwargs = super().get_form_kwargs()
    instance = services.get_vendedor_payment_method(self.request.user.customuser) # type: ignore
    if instance:
      kwargs['instance'] = instance
    return kwargs

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context['payment_method'] = services.get_vendedor_payment_method(self.request.user.customuser) # type: ignore
    return context

  def form_valid(self, form):
    try:
      services.save_payment_method(
        seller=self.request.user.customuser, # type: ignore
        data=form.cleaned_data
      )
      messages.success(self.request, "Sus datos bancarios han sido actualizados correctamente.")
      return super().form_valid(form)
    except Exception as e:
      form.add_error(None, f"Error al guardar los datos: {str(e)}")
      return self.form_invalid(form)

class BankForm(forms.ModelForm):
  class Meta:
    model = Bank
    fields = ['title']
    widgets = {'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del banco'})}

class BankListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
  """Vista administrativa para listar los bancos del sistema."""
  model = Bank
  template_name = 'banking/admin/bank_list.html'
  context_object_name = 'banks'

class BankCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
  """Vista administrativa para registrar nuevos bancos."""
  model = Bank
  form_class = BankForm
  template_name = 'banking/admin/bank_form.html'
  success_url = reverse_lazy('banking:bank_list')
