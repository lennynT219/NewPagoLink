from typing import ClassVar

from django import forms
from django.contrib.auth.models import User
from django.db import models, transaction

from accounts.merchant_profile import CONTRACT_PROFILE_FIELDS

from .models import CustomUser


class UserProfileForm(forms.ModelForm):
  """Edit personal contact and separately declared merchant identity."""

  firstname = forms.CharField(
    max_length=150,
    widget=forms.TextInput(
      attrs={
        'class': 'input-modern',
        'placeholder': 'Tu nombre',
        'autocomplete': 'given-name',
      }
    ),
  )
  lastname = forms.CharField(
    max_length=150,
    widget=forms.TextInput(
      attrs={
        'class': 'input-modern',
        'placeholder': 'Tu apellido',
        'autocomplete': 'family-name',
      }
    ),
  )
  phone = forms.CharField(
    max_length=10,
    widget=forms.TextInput(
      attrs={
        'class': 'input-modern',
        'placeholder': '09XXXXXXXX',
        'autocomplete': 'tel',
      }
    ),
  )
  identification = forms.IntegerField(
    widget=forms.NumberInput(
      attrs={
        'class': 'input-modern',
        'readonly': 'readonly',
        'style': 'background: var(--gray-100); color: var(--gray-500); cursor: not-allowed;',
      }
    ),
  )

  class Meta:
    model = User
    fields = ('email',)
    widgets: ClassVar[dict[str, forms.Widget]] = {
      'email': forms.EmailInput(
        attrs={
          'class': 'input-modern',
          'readonly': 'readonly',
          'style': 'background: var(--gray-100); color: var(--gray-500); cursor: not-allowed;',
        }
      ),
    }

  def __init__(self, *args, **kwargs):
    user = kwargs.get('instance')
    if user and hasattr(user, 'customuser'):
      initial = kwargs.get('initial', {})
      initial['firstname'] = user.first_name
      initial['lastname'] = user.last_name
      initial['phone'] = user.customuser.phone
      initial['identification'] = user.customuser.identification
      kwargs['initial'] = initial
    super().__init__(*args, **kwargs)
    self.fields['email'].disabled = True
    self.fields['identification'].disabled = True
    for name, label in CONTRACT_PROFILE_FIELDS.items():
      model_field = CustomUser._meta.get_field(name)
      assert isinstance(model_field, models.CharField)
      self.fields[name] = forms.CharField(
        label=label,
        required=False,
        max_length=model_field.max_length,
        validators=model_field.validators,
        widget=forms.TextInput(attrs={'class': 'input-modern'}),
      )
      if user and hasattr(user, 'customuser'):
        self.initial[name] = getattr(user.customuser, name)
    self.fields['commerce_ruc'].help_text = '13 dígitos; no uses la identificación personal de tu cuenta como RUC.'
    self.fields['commerce_address'].help_text = 'Declará la dirección del domicilio principal e incluí la ciudad.'
    self.fields[
      'legal_representative_name'
    ].help_text = 'Ingresá el nombre declarado, sin inferirlo del titular de la cuenta.'
    self.fields[
      'commerce_identification'
    ].help_text = (
      '10 dígitos para la frase «cédula de identidad» del contrato; no se copia la identificación de tu cuenta.'
    )

  @property
  def commerce_fields(self):
    return tuple(self[name] for name in CONTRACT_PROFILE_FIELDS)

  def save(self, commit=True):
    user = super().save(commit=False)
    user.first_name = self.cleaned_data['firstname']
    user.last_name = self.cleaned_data['lastname']
    if hasattr(user, 'customuser'):
      user.customuser.phone = self.cleaned_data['phone']
      for name in CONTRACT_PROFILE_FIELDS:
        setattr(user.customuser, name, self.cleaned_data[name])
    if commit:
      with transaction.atomic():
        user.save()
        if hasattr(user, 'customuser'):
          user.customuser.save()
    return user
