from django import forms
from django.contrib.auth.models import User
from .models import CustomUser

class UserProfileForm(forms.ModelForm):
  """Formulario para editar datos básicos del usuario."""
  firstname = forms.CharField(
    max_length=150,
    widget=forms.TextInput(attrs={
      'class': 'input-modern',
      'placeholder': 'Tu nombre',
      'autocomplete': 'given-name',
    }),
  )
  lastname = forms.CharField(
    max_length=150,
    widget=forms.TextInput(attrs={
      'class': 'input-modern',
      'placeholder': 'Tu apellido',
      'autocomplete': 'family-name',
    }),
  )
  phone = forms.CharField(
    max_length=10,
    widget=forms.TextInput(attrs={
      'class': 'input-modern',
      'placeholder': '09XXXXXXXX',
      'autocomplete': 'tel',
    }),
  )
  identification = forms.IntegerField(
    widget=forms.NumberInput(attrs={
      'class': 'input-modern',
      'readonly': 'readonly',
      'style': 'background: var(--gray-100); color: var(--gray-500); cursor: not-allowed;',
    }),
  )

  class Meta:
    model = User
    fields = ['email']
    widgets = {
      'email': forms.EmailInput(attrs={
        'class': 'input-modern',
        'readonly': 'readonly',
        'style': 'background: var(--gray-100); color: var(--gray-500); cursor: not-allowed;',
      }),
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

  def save(self, commit=True):
    user = super().save(commit=False)
    user.first_name = self.cleaned_data['firstname']
    user.last_name = self.cleaned_data['lastname']
    if commit:
      user.save()
      if hasattr(user, 'customuser'):
        user.customuser.phone = self.cleaned_data['phone']
        user.customuser.save()
    return user
