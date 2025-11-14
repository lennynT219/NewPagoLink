from base64 import urlsafe_b64encode
from django import forms
from django.contrib.auth import authenticate, login
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage
from django.utils.encoding import force_bytes
from .models import CustomUser, User
from .tokens import account_activation_token


class LoginForm(forms.Form):
  email = forms.CharField(
    label='Correo electrónico',
    widget=forms.TextInput(
      attrs={
        'class': 'form-control',
        'placeholder': 'Correo electrónico',
        'type': 'email',
      }
    ),
  )
  password = forms.CharField(
    label='Contraseña',
    widget=forms.PasswordInput(
      attrs={
        'class': 'form-control',
        'placeholder': 'Contraseña',
        'id': 'password_login',
      }
    ),
  )

  def clean(self):
    cleaned_data = super().clean()
    email = cleaned_data.get('email')
    password = cleaned_data.get('password')

    if not email or not password:
      raise forms.ValidationError('Ambos campos son obligatorios.')

    user = authenticate(username=email, password=password)
    if not user:
      raise forms.ValidationError('Correo o contraseña incorrecta.')
    if not user.is_active:
      raise forms.ValidationError('El usuario no está activo, contáctese con soporte.')

    # Verifica si el usuario tiene contrato
    try:
      seller = CustomUser.objects.get(user=user)
      redirect_to = 'contract' if not getattr(seller, 'contract', None) else 'dashboard'
    except CustomUser.DoesNotExist:
      raise forms.ValidationError('El usuario no existe en el sistema.')

    cleaned_data['user'] = user
    cleaned_data['redirect_to'] = redirect_to
    return cleaned_data


class RegisterForm(forms.Form):
  firstname = forms.CharField(
    label='nombres',
    widget=forms.TextInput(
      attrs={
        'class': 'form-control',
        'placeholder': 'Nombres',
      }
    ),
  )
  lastname = forms.CharField(
    label='apellidos',
    widget=forms.TextInput(
      attrs={
        'class': 'form-control',
        'placeholder': 'Apellidos',
      }
    ),
  )
  identification = forms.IntegerField(
    label='Cédula de identidad',
    widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cédula', 'type': 'number'}),
  )
  phone = forms.IntegerField(
    label='Nro de celular',
    widget=forms.TextInput(
      attrs={
        'class': 'form-control',
        'placeholder': 'Nro de celular',
      }
    ),
  )
  email = forms.EmailField(
    label='Correo electrónico',
    widget=forms.TextInput(
      attrs={
        'class': 'form-control',
        'placeholder': 'Correo electrónico',
        'type': 'email',
      }
    ),
  )
  password = forms.CharField(
    label='contraseña',
    widget=forms.TextInput(
      attrs={
        'class': 'form-control',
        'placeholder': 'Contraseña',
        'type': 'password',
        'id': 'password_register',
      }
    ),
  )

  def clean_email(self):
    email = self.cleaned_data['email']
    if User.objects.filter(email=email).exists():
      raise forms.ValidationError('Este correo ya está en uso.')
    return email
