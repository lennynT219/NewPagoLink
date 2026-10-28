from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.forms import (
  CharField,
  CheckboxInput,
  EmailField,
  EmailInput,
  Form,
  HiddenInput,
  IntegerField,
  PasswordInput,
  TextInput,
  ValidationError,
)

from accounts.contracts import has_current_acceptance
from accounts.merchant_profile import validate_contact_phone
from accounts.models import CustomUser


class ContractAcceptanceForm(Form):
  # CharField deliberately avoids BooleanField's permissive coercion.
  consent = CharField(strip=False, widget=CheckboxInput(attrs={'value': 'accept'}))
  version = CharField(strip=False, widget=HiddenInput)
  text_hash = CharField(strip=False, widget=HiddenInput)
  preview_token = CharField(strip=False, widget=HiddenInput)

  def clean(self):
    data = super().clean() or {}
    if (
      self.data.get('consent') != 'accept'
      or not data.get('version')
      or not data.get('text_hash')
      or not data.get('preview_token')
    ):
      raise ValidationError(
        'Debe aceptar explícitamente el contrato vigente. Revise los términos y vuelva a intentarlo.'
      )
    return data


class RegisterForm(Form):
  firstname = CharField(
    label='nombres',
    max_length=150,
    error_messages={'max_length': 'Este campo admite como máximo %(limit_value)s caracteres.'},
    widget=TextInput(
      attrs={
        'class': 'form-control',
        'placeholder': 'Nombres',
      }
    ),
  )
  lastname = CharField(
    label='apellidos',
    max_length=150,
    error_messages={'max_length': 'Este campo admite como máximo %(limit_value)s caracteres.'},
    widget=TextInput(
      attrs={
        'class': 'form-control',
        'placeholder': 'Apellidos',
      }
    ),
  )
  identification = IntegerField(
    label='Cédula de identidad',
    min_value=-(2**63),
    max_value=2**63 - 1,
    error_messages={
      'min_value': 'La identificación está fuera del rango permitido.',
      'max_value': 'La identificación está fuera del rango permitido.',
    },
    widget=TextInput(attrs={'class': 'form-control', 'placeholder': 'Cédula', 'type': 'number'}),
  )
  phone = CharField(
    label='Nro de celular',
    max_length=10,
    error_messages={'max_length': 'El celular admite como máximo 10 caracteres.'},
    widget=TextInput(
      attrs={
        'class': 'form-control',
        'placeholder': 'Nro de celular',
        'type': 'tel',
        'inputmode': 'numeric',
        'autocomplete': 'tel-national',
      }
    ),
  )
  email = EmailField(
    label='Correo electrónico',
    # Registration uses the email as auth.User.username (150 characters).
    max_length=150,
    error_messages={'max_length': 'Este campo admite como máximo %(limit_value)s caracteres.'},
    widget=TextInput(
      attrs={
        'class': 'form-control',
        'placeholder': 'Correo electrónico',
      }
    ),
  )
  password = CharField(
    label='contraseña',
    widget=PasswordInput(
      attrs={
        'class': 'form-control',
        'placeholder': 'Contraseña',
        'id': 'password_register',
      }
    ),
  )

  def clean_identification(self):
    identification = self.cleaned_data['identification']
    if CustomUser.objects.filter(identification=identification).exists():
      raise ValidationError('Esta identificación ya está registrada.')
    return identification

  def clean_phone(self):
    phone = self.cleaned_data['phone']
    validate_contact_phone(phone)
    return phone

  def clean_email(self):
    email = self.cleaned_data['email']
    if User.objects.filter(email=email).exists():
      raise ValidationError('Este correo ya está en uso.')
    return email


class LoginForms(Form):
  email = CharField(
    label='Correo electrónico',
    widget=TextInput(
      attrs={
        'class': 'form-control',
        'placeholder': 'Correo electrónico',
        'type': 'email',
      }
    ),
  )
  password = CharField(
    label='Contraseña',
    widget=PasswordInput(
      attrs={
        'class': 'form-control',
        'placeholder': 'Contraseña',
        'id': 'password_login',
      }
    ),
  )

  def clean(self):
    cleaned_data = super().clean() or {}
    email = cleaned_data.get('email')
    password = cleaned_data.get('password')

    if not email or not password:
      raise ValidationError('Ambos campos son obligatorios.')

    user = authenticate(username=email, password=password)
    if not user:
      raise ValidationError('Correo o contraseña incorrecta.')
    if not user.is_active:
      raise ValidationError('El usuario no está activo, contáctese con soporte.')

    # Verifica si el usuario tiene contrato
    try:
      seller = CustomUser.objects.get(user=user)
      redirect_to = 'dashboard' if has_current_acceptance(seller) else 'contract'
    except CustomUser.DoesNotExist:
      raise ValidationError('El usuario no existe en el sistema.')

    cleaned_data['user'] = user
    cleaned_data['redirect_to'] = redirect_to
    return cleaned_data


class LoginForm(AuthenticationForm):
  username = EmailField(
    label='Correo electrónico',
    widget=EmailInput(
      attrs={
        'autofocus': True,
        'class': 'form-control',
        'placeholder': 'Correo electrónico',
      }
    ),
  )
  password = CharField(
    label='Contraseña',
    strip=False,
    widget=PasswordInput(
      attrs={
        'autocomplete': 'current-password',
        'class': 'form-control',
        'placeholder': 'Contraseña',
      }
    ),
  )
  error_messages = {
    'invalid_login': ('Correo o contraseña incorrectas. Por favor, intentelo de nuevo.'),
    'inactive': ('Esta cuenta esta inactiva. Revisa tu correo de activacion.'),
  }

  def __init__(self, request=None, *args, **kwargs) -> None:
    super().__init__(request, *args, **kwargs)
