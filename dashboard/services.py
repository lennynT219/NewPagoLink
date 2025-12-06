from typing import Any, Dict, Optional
from django.db.models import Sum
from django.urls import reverse_lazy
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from .models import CustomUser, Contract, Link, Payment, Refund
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

  CustomUser.objects.create(user=user, phone=form_data['phone'], identification=form_data['identification'])

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


def get_dashboard_stats(user: CustomUser) -> Optional[Dict[str, Any]]:
  try:
    seller = user
    links_count = Link.objects.filter(seller=seller).count()
    sales_agg = Payment.objects.filter(seller=seller, state=True).aggregate(total=Sum('amount'))
    total_sales = sales_agg['total'] or 0.0
    refunds_agg = Refund.objects.filter(seller=seller).aggregate(total=Sum('amount'))
    total_refunds = refunds_agg['total'] or 0.0

    return {
      'links_count': links_count,
      'total_sales': total_sales,
      'total_refunds': total_refunds,
      'active': seller.state,
      'email_active': seller.email_active,
      'seller_name': seller.user.first_name,
    }

  except CustomUser.DoesNotExist:
    return None
