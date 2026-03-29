from typing import Any, Dict, Optional
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.urls import reverse_lazy
from django.contrib.gis.geoip2 import GeoIP2
from accounts.models import CustomUser
from accounts.tokens import account_activation_token


def create_user(form_data: Dict[str, Any]) -> User:
  """Crea el User y el Custom User de forma atómica."""
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


from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags

def send_activation_email(user: User, req: Any) -> None:
  """Construye y envía un email de activación en formato HTML."""
  current_site = get_current_site(req)
  mail_subject = 'Active su cuenta de PagoLink'
  html_content = render_to_string(
    'dashboard/activation_email.html',
    {
      'user': user,
      'domain': current_site.domain,
      'uid': urlsafe_base64_encode(force_bytes(user.pk)),
      'token': account_activation_token.make_token(user),
    },
  )
  text_content = strip_tags(html_content) # Versión en texto plano para clientes que no soportan HTML
  
  email = EmailMultiAlternatives(
    mail_subject, 
    text_content, 
    'PagoLink <pagoslinkexpress@gmail.com>', 
    [user.email]
  )
  email.attach_alternative(html_content, "text/html")
  
  try:
    email.send()
  except Exception as e:
    print(f'Error al enviar el email de activación: {e}')


def login_redirect_url(user: User) -> str:
  """Determina a dónde enviar al usuario tras el login."""
  if user.is_staff:
    return reverse_lazy('admin:index')
  try:
    seller = user.customuser # type: ignore
  except Exception:
    return reverse_lazy('dashboard:login')

  if hasattr(seller, 'contract'):
    return reverse_lazy('dashboard:dashboard')
  return reverse_lazy('dashboard:contract')


def get_client_ip(req: Any) -> str:
  """Obtiene la IP real del cliente."""
  x_forwarded_for = req.META.get('HTTP_X_FORWARDED_FOR')
  return x_forwarded_for.split(',')[0] if x_forwarded_for else req.META.get('REMOTE_ADDR')


def get_location_from_ip(ip: str) -> str:
  """Geolocaliza una IP usando GeoIP2."""
  try:
    return GeoIP2().city(ip)['city']
  except Exception:
    return 'No identificado'
