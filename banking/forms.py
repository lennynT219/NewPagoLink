from django import forms
from .models import PaymentMethod, Bank, DisbursementRequest

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


class DisbursementRequestForm(forms.ModelForm):
  """Formulario para solicitar un desembolso."""
  
  class Meta:
    model = DisbursementRequest
    fields = ['amount', 'method']
    widgets = {
      'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Monto a retirar'}),
      'method': forms.Select(attrs={'class': 'form-control select2'}),
    }
    labels = {
      'amount': 'Monto ($)',
      'method': 'Cuenta de destino',
    }

  def __init__(self, *args, **kwargs):
    self.seller = kwargs.pop('seller', None)
    super().__init__(*args, **kwargs)
    if self.seller:
      self.fields['method'].queryset = PaymentMethod.objects.filter(seller=self.seller)
      self.fields['method'].empty_label = "Seleccione una cuenta bancaria..."

  def clean_amount(self):
    amount = self.cleaned_data.get('amount')
    if amount and amount <= 0:
      raise forms.ValidationError("El monto debe ser mayor a cero.")
    if self.seller and amount > self.seller.available_balance:
      raise forms.ValidationError(f"Saldo insuficiente. Su saldo actual es ${self.seller.available_balance}")
    return amount
