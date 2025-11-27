from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from .models import CustomUser, Contract
from .tokens import account_activation_token
from django.contrib.gis.geoip2 import GeoIP2


def create_user(form_data):
  """
  Crea el User y el Custom User de forma atómica
  Recibe el cleaned_data del formulario
  """
  user = User.objects.create_user(
    username=form_data['email'],
    email=form_data['email'],
    first_name=form_data['firstname'],
    last_name=form_data['lastname'],
    password=form_data['password'],
    is_active=False,
  )

  CustomUser.objects.create(user=user, phone=form_data['phone'], identification=form_data['identification'])  # type: ignore

  return user


def send_activation_email(user, req):
  """
  Construye y envía un email de activación al usuario recién registrado.
  """
  current_site = get_current_site(req)
  mail_subject = 'Active su cuenta de PagoLink'
  message = render_to_string(
    'activation_email.html',
    {
      'user': user,
      'domain': current_site.domain,
      'uid': urlsafe_base64_encode(force_bytes(user.pk)),
      'token': account_activation_token.make_token(user),
    },
  )
  email = EmailMessage(mail_subject, message, 'PagoLink <pagoslinkexpress@gmail.com>', to=[user.email])

  try:
    email.send()
  except Exception as e:
    print(f'Error al enviar el email de activación: {e}')


def login_redirect_url(user):
  if user.is_staff:
    return reverse_lazy('admin:index')

  try:
    seller = user.customuser
  except CustomUser.DoesNotExist:
    return reverse_lazy('dashboard:login')

  if hasattr(seller, 'contract'):
    return reverse_lazy('dashboard:dashboard')
  else:
    return reverse_lazy('dashboard:contract')


def get_client_ip(req):
  x_forwarded_for = req.META.get('HTTP_X_FORWARDED_FOR')
  if x_forwarded_for:
    ip = x_forwarded_for.split(',')[0]
  else:
    ip = req.META.get('REMOTE_ADDR')
  return ip


def get_location_from_ip(ip):
  try:
    city = GeoIP2().city(ip)['city']
    return city
  except Exception:
    return 'No identificado'


class DashboardView(View):
  def get(self, request):
    if not request.user.is_authenticated:
      return redirect('login')
    seller = CustomUser.objects.get(user=request.user)

    try:
      if seller.contract:
        links = Link.objects.filter(seller=seller)
        sales = Payment.objects.filter(seleer=seller, state=True)
        refunds = Refund.objects.filter(seller=seller)
        sale = 0
        refund = 0
        for r in refunds:
          refund += r.amount

        for s in sales:
          sale += s.amount
        context = {
          'links': links,
          'sale': sale,
          'refund': refund,
          'active': seller.state,
          'email_active': seller.email_active,
                    p
        }
        return render(request, 'dashboard/dashboard.html', context)
    except:
      return redirect('contract')


def get_dashboard_stats(user):
  seller = user.customuser
  links_count = ''
