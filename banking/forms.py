from django import forms
from .models import PaymentMethod, Bank

class PaymentMethodForm(forms.ModelForm):
  """Formulario para la configuración de la cuenta bancaria del vendedor."""
  
  class Meta:
    model = PaymentMethod
    fields = ['bank', 'fullname', 'account_type', 'account_number', 'cci']
    widgets = {
      'bank': forms.Select(attrs={'class': 'form-control select2'}),
      'fullname': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre completo del titular'}),
      'account_type': forms.Select(attrs={'class': 'form-control'}),
      'account_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Número de cuenta'}),
      'cci': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Código de Cuenta Interbancario (Opcional)'}),
    }
    labels = {
      'bank': 'Banco',
      'fullname': 'Titular de la cuenta',
      'account_type': 'Tipo de cuenta',
      'account_number': 'Número de cuenta',
      'cci': 'CCI (Interbancario)',
    }

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.fields['bank'].empty_label = "Seleccione un banco..."
