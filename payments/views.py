import re
from typing import Protocol, cast

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView

from accounts.models import CustomUser
from dashboard.mixins import AdminRequiredMixin, ContractRequiredMixin
from gateways.services import PAYER_LIMITS, DatafastClient

from . import services
from .forms import CheckoutForm, LinkForm
from .models import Link, Payment, PaymentAttempt, Refund


class _ProfileUser(Protocol):
  """Generated reverse relation used only behind existing login/contract guards."""

  @property
  def customuser(self) -> CustomUser: ...


class AdminRefundListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
  """Vista administrativa para que el staff vea solicitudes de reembolso pendientes."""

  model = Refund
  template_name = 'payments/admin/refund_list.html'
  context_object_name = 'refunds'

  def get_queryset(self):
    return Refund.objects.filter(status__in=['PENDING', 'PROCESSING', 'UNKNOWN']).order_by('created_at')


class AdminRefundApproveView(LoginRequiredMixin, AdminRequiredMixin, View):
  """Vista para procesar la aprobación de un reembolso."""

  def post(self, request, pk):
    try:
      refund = services.approve_refund_logic(pk, request.user)
      if refund.status == Refund.RefundStatus.APPROVED:
        messages.success(request, 'El reembolso ha sido aprobado y confirmado por Datafast.')
      elif refund.status == Refund.RefundStatus.REJECTED:
        messages.error(request, 'Datafast rechazó el reembolso. La reserva fue liberada.')
      else:
        messages.warning(request, 'Resultado pendiente de conciliación; fondos reservados. No reenviar.')
    except ValueError as exc:
      messages.error(request, str(exc))
    except Exception:  # noqa: BLE001 -- Unknown refund failures remain unresolved; never imply approval.
      messages.error(request, 'No se pudo verificar el reembolso. No reenviar; contacte a soporte.')
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

    return render(
      request,
      self.template_name,
      {
        'link': link,
        'seller': link.seller,
        'payment': payment,
        # A public record selector is not authority to disclose saved payer data.
        'form': CheckoutForm(),
        'DATAFAST_BASE_URL': settings.DATAFAST_BASE_URL,
      },
    )

  def post(self, request, pk, *args, **kwargs):
    link = get_object_or_404(Link, pk=pk)
    if not link.active:
      return render(request, self.inactive_template, {'link': link})
    payment_id = request.GET.get('p')
    payment = None
    if payment_id:
      payment = get_object_or_404(Payment, id=payment_id, link=link)

    if payment and services._settled(payment):
      messages.error(request, 'Este pago ya ha sido procesado.')
      return redirect('payments:link_checkout', pk=pk)
    form = CheckoutForm(request.POST)
    valid = form.is_valid()
    try:
      client_ip = services.checkout_client_ip(request)
    except (ValueError, TypeError) as exc:
      form.add_error(None, str(exc))
      return self.render_info(request, link, payment, form)
    if not valid:
      return self.render_info(request, link, payment, form)
    customer_data = {key: form.cleaned_data[key] for key in PAYER_LIMITS}

    if not payment:
      # Crear pago nuevo (pago directo desde link múltiple)
      payment = Payment.objects.create(
        link=link,
        seller=link.seller,
        description=link.description,
        subtotal=link.subtotal,
        igv=link.igv,
        amount=link.amount,
        amount_client=link.amount,
        **customer_data,
      )

    gateway = DatafastClient()
    try:
      attempt = services.prepare_payment_checkout(payment.pk, gateway, customer_data, client_ip)
    except (ValueError, TypeError) as exc:
      form.add_error(None, str(exc))
      return self.render_info(request, link, payment, form)
    payment.refresh_from_db()
    checkout_id = attempt.checkout_id
    if checkout_id and attempt.state == PaymentAttempt.State.LIVE:
      return render(
        request,
        self.template_name,
        {
          'link': link,
          'checkout_id': checkout_id,
          'payment': payment,
          'step': 'payment',
          'DATAFAST_BASE_URL': settings.DATAFAST_BASE_URL,
        },
      )
    form.add_error(None, 'No se pudo confirmar el intento. No reenviar; contacte a soporte.')
    return self.render_info(request, link, payment, form)

  def render_info(self, request, link, payment, form):
    return render(
      request,
      self.template_name,
      {
        'link': link,
        'seller': link.seller,
        'payment': payment,
        'form': form,
        'DATAFAST_BASE_URL': settings.DATAFAST_BASE_URL,
      },
    )


class PaymentResultView(View):
  """Vista de resultado del pago."""

  template_name = 'payments/payment_result.html'

  def get(self, request):
    resource_path = request.GET.get('resourcePath')
    payment_id = request.GET.get('payment_id')
    if not resource_path or not payment_id:
      return redirect('landing:index')
    if not payment_id.isdecimal() or not re.fullmatch(
      r'/v1/checkouts/[A-Za-z0-9_-][A-Za-z0-9_.-]{0,254}/payment', resource_path
    ):
      return HttpResponseBadRequest('Referencia de pago inválida.')
    checkout_id = resource_path.split('/')[3]
    attempt = PaymentAttempt.objects.filter(payment_id=payment_id, checkout_id=checkout_id).first()
    if attempt is None or resource_path != attempt.resource_path:
      return HttpResponseBadRequest('Referencia de pago inválida.')
    gateway = DatafastClient()
    result_data = gateway.get_payment_status(resource_path)
    payment = services.process_payment_result(int(payment_id), result_data, attempt_id=attempt.pk)
    return render(
      request,
      self.template_name,
      {
        'payment': payment,
        'success': payment.state,
        'error_msg': None if payment.state else 'No se ha confirmado el pago. Intente consultar nuevamente.',
      },
    )


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
    return Payment.objects.filter(seller=cast(_ProfileUser, self.request.user).customuser).order_by('-id')

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
    response = HttpResponse(
      excel_buffer.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="ventas_{seller.user.username}.xlsx"'
    return response


class RefundListView(LoginRequiredMixin, ContractRequiredMixin, ListView):
  """Historial de reembolsos del vendedor."""

  model = Refund
  template_name = 'payments/refund_list.html'
  context_object_name = 'refunds'

  def get_queryset(self):
    return Refund.objects.filter(seller=cast(_ProfileUser, self.request.user).customuser).order_by('-id')


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
      messages.error(request, 'Debe proporcionar un motivo para el reembolso.')
      return render(request, self.template_name, {'payment': payment})

    try:
      services.request_refund(request.user.customuser, payment, description)
      messages.success(request, 'Solicitud de reembolso enviada. Será procesada por nuestro equipo.')
      return redirect('payments:payment_history')
    except ValueError as exc:
      messages.error(request, str(exc))
    except Exception:  # noqa: BLE001 -- Unknown refund errors must not imply settlement or release.
      messages.error(request, 'No se pudo registrar la solicitud. Contacte a soporte.')
    return render(request, self.template_name, {'payment': payment})


class LinkDetailView(LoginRequiredMixin, ContractRequiredMixin, ListView):
  """Vista para ver el detalle de un link y sus pagos asociados."""

  model = Payment
  template_name = 'payments/link_detail.html'
  context_object_name = 'payments'

  def get_queryset(self):
    self.link = get_object_or_404(Link, pk=self.kwargs['pk'], seller=cast(_ProfileUser, self.request.user).customuser)
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
    return Link.objects.filter(seller=cast(_ProfileUser, self.request.user).customuser).order_by('-created_at')


class LinkCreateView(LoginRequiredMixin, ContractRequiredMixin, CreateView):
  model = Link
  form_class = LinkForm
  template_name = 'payments/link_form.html'
  success_url = reverse_lazy('payments:link_list')

  def form_valid(self, form):
    link = services.create_payment_link(cast(_ProfileUser, self.request.user).customuser, form.cleaned_data)

    # Si se proporcionaron datos del cliente, creamos un registro de pago y enviamos invitación
    if form.cleaned_data.get('email'):
      payment = Payment.objects.create(
        link=link,
        seller=cast(_ProfileUser, self.request.user).customuser,
        description=link.description,
        subtotal=link.subtotal,
        igv=link.igv,
        amount=link.amount,
        amount_client=link.amount,
        first_name=form.cleaned_data.get('firstname', ''),
        last_name=form.cleaned_data.get('lastname', ''),
        email=form.cleaned_data.get('email', ''),
        phone=form.cleaned_data.get('phone', ''),
        identify=form.cleaned_data.get('identity', ''),
      )
      try:
        services.send_payment_invite(payment, self.request)
      except Exception:  # noqa: BLE001 -- Notification errors must not expose payer data or provider details.
        services.logger.warning('Payment invite unavailable for payment %s', payment.pk)

    messages.success(self.request, '¡Link creado exitosamente! Se ha enviado una invitación al cliente.')
    # The fixed reverse_lazy target above is non-null; cast preserves the Promise itself.
    return redirect(cast(str, self.success_url))
