from django.shortcuts import get_object_or_404, render, redirect
from django.views import View
from django.views.generic import ListView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Sum
from django.http import HttpResponse
from django.conf import settings
from .models import Link, Payment, Refund
from .forms import LinkForm
from . import services
from gateways.services import DatafastClient
from dashboard.mixins import ContractRequiredMixin

from dashboard.mixins import ContractRequiredMixin, AdminRequiredMixin

class AdminRefundListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
  """Vista administrativa para que el staff vea solicitudes de reembolso pendientes."""
  model = Refund
  template_name = 'payments/admin/refund_list.html'
  context_object_name = 'refunds'
  def get_queryset(self):
    return Refund.objects.filter(status=Refund.RefundStatus.PENDING).order_by('created_at')

class AdminRefundApproveView(LoginRequiredMixin, AdminRequiredMixin, View):
  """Vista para procesar la aprobación de un reembolso."""
  def post(self, request, pk):
    try:
      services.approve_refund_logic(pk, request.user)
      messages.success(request, "El reembolso ha sido aprobado y procesado exitosamente.")
    except Exception as e:
      messages.error(request, f"Error al procesar el reembolso: {str(e)}")
    return redirect('payments:admin_refund_list')

class LinkCheckoutView(View):
  """Vista pública de Checkout."""
  template_name = 'payments/checkout.html'
  inactive_template = 'payments/link_inactive.html'

  def get(self, request, pk, *args, **kwargs):
    link = get_object_or_404(Link, pk=pk)
    if not link.active:
      return render(request, self.inactive_template, {'link': link})
    
    payment_id = request.GET.get('p')
    payment = None
    if payment_id:
      payment = get_object_or_404(Payment, id=payment_id, link=link)

    return render(request, self.template_name, {
      'link': link, 
      'seller': link.seller,
      'payment': payment, # Pasamos el pago para pre-rellenar campos en el HTML
      'DATAFAST_BASE_URL': settings.DATAFAST_BASE_URL
    })

  def post(self, request, pk, *args, **kwargs):
    link = get_object_or_404(Link, pk=pk)
    if not link.active:
      return render(request, self.inactive_template, {'link': link})
    payment_id = request.GET.get('p')
    payment = None
    if payment_id:
      payment = get_object_or_404(Payment, id=payment_id, link=link)

    customer_data = {
      'first_name': request.POST.get('first_name'),
      'last_name': request.POST.get('last_name'),
      'email': request.POST.get('email'),
      'identify': request.POST.get('identify'),
      'phone': request.POST.get('phone'),
    }

    if payment:
      # Actualizar pago existente (invitación)
      for key, value in customer_data.items():
        setattr(payment, key, value)
      payment.save()
    else:
      # Crear pago nuevo (pago directo desde link múltiple)
      payment = Payment.objects.create(
        link=link, seller=link.seller, description=link.description,
        subtotal=link.subtotal, igv=link.igv, amount=link.amount, amount_client=link.amount,
        **customer_data
      )

    gateway = DatafastClient()
    from accounts.services import get_client_ip
    client_ip = get_client_ip(request)

    checkout_id = gateway.prepare_checkout(
      amount=link.amount,
      subtotal=link.subtotal,
      igv=link.igv,
      include_igv=link.include_igv,
      transaction_id=f"PAY-{payment.id}",
      customer_data=customer_data,
      client_ip=client_ip
    )
    if checkout_id:
      return render(request, self.template_name, {
        'link': link, 
        'checkout_id': checkout_id, 
        'payment': payment, 
        'step': 'payment',
        'DATAFAST_BASE_URL': settings.DATAFAST_BASE_URL
      })
    messages.error(request, "Error de conexión con la pasarela.")
    return redirect('payments:link_checkout', pk=pk)

class PaymentResultView(View):
  """Vista de resultado del pago."""
  template_name = 'payments/payment_result.html'
  def get(self, request):
    resource_path = request.GET.get('resourcePath')
    payment_id = request.GET.get('payment_id')
    if not resource_path or not payment_id: return redirect('landing:index')
    gateway = DatafastClient()
    result_data = gateway.get_payment_status(resource_path)
    payment = services.process_payment_result(int(payment_id), result_data)
    return render(request, self.template_name, {
      'payment': payment, 
      'success': payment.state, 
      'error_msg': result_data.get('result', {}).get('description')
    })

class PaymentDetailView(LoginRequiredMixin, ContractRequiredMixin, View):
  """Vista para ver el detalle de una transacción específica."""
  template_name = 'payments/payment_detail.html'
  def get(self, request, pk):
    payment = get_object_or_404(Payment, id=pk, seller=request.user.customuser)
    return render(request, self.template_name, {'payment': payment})

class PaymentListView(LoginRequiredMixin, ContractRequiredMixin, ListView):
  """Historial de transacciones."""
  model = Payment
  template_name = 'payments/payment_list.html'
  context_object_name = 'payments'
  def get_queryset(self):
    return Payment.objects.filter(seller=self.request.user.customuser).order_by('-id')
  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    total_agg = self.get_queryset().filter(state=True).aggregate(total=Sum('amount'))
    context['total_collected'] = total_agg['total'] or 0.0
    return context

class PaymentExportCSVView(LoginRequiredMixin, ContractRequiredMixin, View):
  def get(self, request):
    seller = request.user.customuser
    csv_buffer = services.generate_payments_csv(seller)
    response = HttpResponse(csv_buffer.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="ventas_{seller.user.username}.csv"'
    return response

class PaymentExportExcelView(LoginRequiredMixin, ContractRequiredMixin, View):
  def get(self, request):
    seller = request.user.customuser
    excel_buffer = services.generate_payments_excel(seller)
    response = HttpResponse(excel_buffer.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="ventas_{seller.user.username}.xlsx"'
    return response

class RefundListView(LoginRequiredMixin, ContractRequiredMixin, ListView):
  """Historial de reembolsos del vendedor."""
  model = Refund
  template_name = 'payments/refund_list.html'
  context_object_name = 'refunds'
  def get_queryset(self):
    return Refund.objects.filter(seller=self.request.user.customuser).order_by('-id')

class RefundRequestView(LoginRequiredMixin, ContractRequiredMixin, View):
  """Vista para solicitar un reembolso de un pago específico."""
  template_name = 'payments/refund_form.html'

  def get(self, request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id, seller=request.user.customuser)
    return render(request, self.template_name, {'payment': payment})

  def post(self, request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id, seller=request.user.customuser)
    description = request.POST.get('description')
    
    if not description:
      messages.error(request, "Debe proporcionar un motivo para el reembolso.")
      return render(request, self.template_name, {'payment': payment})

    try:
      services.request_refund(request.user.customuser, payment, description)
      messages.success(request, "Solicitud de reembolso enviada. Será procesada por nuestro equipo.")
      return redirect('payments:payment_history')
    except Exception as e:
      messages.error(request, str(e))
      return render(request, self.template_name, {'payment': payment})

class LinkDetailView(LoginRequiredMixin, ContractRequiredMixin, ListView):
  """Vista para ver el detalle de un link y sus pagos asociados."""
  model = Payment
  template_name = 'payments/link_detail.html'
  context_object_name = 'payments'

  def get_queryset(self):
    self.link = get_object_or_404(Link, pk=self.kwargs['pk'], seller=self.request.user.customuser)
    return Payment.objects.filter(link=self.link).order_by('-id')

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context['link'] = self.link
    return context

class LinkListView(LoginRequiredMixin, ContractRequiredMixin, ListView):
  model = Link
  template_name = 'payments/link_list.html'
  context_object_name = 'links'
  def get_queryset(self):
    return Link.objects.filter(seller=self.request.user.customuser).order_by('-created_at')

class LinkCreateView(LoginRequiredMixin, ContractRequiredMixin, CreateView):
  model = Link
  form_class = LinkForm
  template_name = 'payments/link_form.html'
  success_url = reverse_lazy('payments:link_list')

  def form_valid(self, form):
    link = services.create_payment_link(self.request.user.customuser, form.cleaned_data)
    
    # Si se proporcionaron datos del cliente, creamos un registro de pago y enviamos invitación
    if form.cleaned_data.get('email'):
      payment = Payment.objects.create(
        link=link, seller=self.request.user.customuser, description=link.description,
        subtotal=link.subtotal, igv=link.igv, amount=link.amount, amount_client=link.amount,
        first_name=form.cleaned_data.get('firstname', ''),
        last_name=form.cleaned_data.get('lastname', ''),
        email=form.cleaned_data.get('email', ''),
        phone=form.cleaned_data.get('phone', ''),
        identify=form.cleaned_data.get('identity', '')
      )
      try:
        services.send_payment_invite(payment, self.request)
      except Exception as e:
        print(f"Error enviando invitación: {e}")

    messages.success(self.request, "¡Link creado exitosamente! Se ha enviado una invitación al cliente.")
    return redirect(self.success_url)
