from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from .models import CustomUser
from .tokens import account_activation_token


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
