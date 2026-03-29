from django.shortcuts import get_object_or_404, render, redirect
from django.views import View
from .models import Link, Payment
from gateways.services import DatafastClient
from . import services

class LinkCheckoutView(View):
  """Vista pública que muestra la información del cobro al cliente final."""
  template_name = 'payments/checkout.html'

  def get(self, request, pk, *args, **kwargs):
    link = get_object_or_404(Link, pk=pk, active=True)
    
    # Preparamos los datos básicos para el formulario
    context = {
      'link': link,
      'seller': link.seller,
    }
    return render(request, self.template_name, context)

  def post(self, request, pk, *args, **kwargs):
    link = get_object_or_404(Link, pk=pk, active=True)
    
    # 1. Recolectar datos del cliente desde el formulario
    customer_data = {
      'first_name': request.POST.get('first_name'),
      'last_name': request.POST.get('last_name'),
      'email': request.POST.get('email'),
      'identify': request.POST.get('identify'),
      'phone': request.POST.get('phone'),
    }

    # 2. Crear registro de pago pendiente (Trazabilidad)
    payment = Payment.objects.create(
      link=link,
      seller=link.seller,
      description=link.description,
      subtotal=link.subtotal,
      igv=link.igv,
      amount=link.amount,
      amount_client=link.amount, # En este punto es el total
      **customer_data
    )

    # 3. Solicitar sesión a Datafast
    gateway = DatafastClient()
    checkout_id = gateway.prepare_checkout(
      amount=link.amount,
      currency='USD',
      transaction_id=f"PAY-{payment.id}",
      customer_data=customer_data
    )

    if checkout_id:
      # Guardamos el ID temporalmente para el widget de pagos
      context = {
        'link': link,
        'checkout_id': checkout_id,
        'payment': payment,
        'step': 'payment' # Cambiamos a la fase de tarjeta
      }
      return render(request, self.template_name, context)
    else:
      messages.error(request, "Lo sentimos, no pudimos conectar con la pasarela de pagos. Intente más tarde.")
      return redirect('payments:link_checkout', pk=pk)
  """Vista para listar los links de pago del vendedor."""
  model = Link
  template_name = 'payments/link_list.html'
  context_object_name = 'links'

  def get_queryset(self):
    # Solo mostramos los links del vendedor autenticado
    return Link.objects.filter(seller=self.request.user.customuser).order_by('-created_at') # type: ignore


class LinkCreateView(LoginRequiredMixin, ContractRequiredMixin, CreateView):
  """Vista para crear un nuevo link de pago."""
  model = Link
  form_class = LinkForm
  template_name = 'payments/link_form.html'
  success_url = reverse_lazy('payments:link_list')

  def form_valid(self, form):
    try:
      # Delegamos la creación a la capa de servicios
      services.create_payment_link(
        seller=self.request.user.customuser, # type: ignore
        data=form.cleaned_data
      )
      messages.success(self.request, "¡Link de pago creado exitosamente!")
      return super().form_valid(form)
    except Exception as e:
      form.add_error(None, f"Ocurrió un error al procesar el link: {str(e)}")
      return self.form_invalid(form)
