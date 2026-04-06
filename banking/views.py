from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, FormView, DetailView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django import forms
from .models import Bank, PaymentMethod, DisbursementRequest
from .forms import PaymentMethodForm, DisbursementRequestForm
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


class DisbursementListView(LoginRequiredMixin, ContractRequiredMixin, ListView):
  """Vista para que el vendedor vea su historial de retiros."""
  model = DisbursementRequest
  template_name = 'banking/disbursement_list.html'
  context_object_name = 'disbursements'

  def get_queryset(self):
    return DisbursementRequest.objects.filter(vendor=self.request.user.customuser).order_by('-created_at') # type: ignore


class DisbursementCreateView(LoginRequiredMixin, ContractRequiredMixin, CreateView):
  """Vista para solicitar un nuevo desembolso."""
  model = DisbursementRequest
  form_class = DisbursementRequestForm
  template_name = 'banking/disbursement_form.html'
  success_url = reverse_lazy('banking:disbursement_list')

  def get_form_kwargs(self):
    kwargs = super().get_form_kwargs()
    kwargs['seller'] = self.request.user.customuser # type: ignore
    return kwargs

  def form_valid(self, form):
    try:
      services.create_disbursement_request(
        seller=self.request.user.customuser, # type: ignore
        amount=form.cleaned_data['amount'],
        method_id=form.cleaned_data['method'].id
      )
      messages.success(self.request, "Solicitud de desembolso enviada para aprobación.")
      return redirect(self.success_url)
    except Exception as e:
      form.add_error(None, str(e))
      return self.form_invalid(form)


class AdminDisbursementListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
  """Vista para que el admin vea todas las solicitudes pendientes."""
  model = DisbursementRequest
  template_name = 'banking/admin/disbursement_list.html'
  context_object_name = 'disbursements'

  def get_queryset(self):
    return DisbursementRequest.objects.filter(status=DisbursementRequest.Status.PENDING).order_by('-created_at')


class AdminDisbursementProcessView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
  """Vista para procesar (Aprobar/Rechazar) una solicitud."""
  model = DisbursementRequest
  template_name = 'banking/admin/disbursement_detail.html'
  context_object_name = 'disbursement'

  def post(self, request, *args, **kwargs):
    disbursement = self.get_object()
    action = request.POST.get('action')
    reason = request.POST.get('rejection_reason', '')

    try:
      status = DisbursementRequest.Status.APPROVED if action == 'approve' else DisbursementRequest.Status.REJECTED
      services.process_disbursement(
        request_id=disbursement.id,
        status=status,
        admin_user=request.user,
        rejection_reason=reason
      )
      messages.success(request, f"Solicitud {status} correctamente.")
    except Exception as e:
      messages.error(request, f"Error al procesar: {str(e)}")

    return redirect('banking:admin_disbursement_list')
