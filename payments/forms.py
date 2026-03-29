from django import forms
from decimal import Decimal
from payments.models import Link

class LinkForm(forms.ModelForm):
  """Formulario para la creación y edición de links de pago."""
  
  # Campos adicionales que no están directamente en el modelo pero se capturan
  firstname = forms.CharField(max_length=100, required=False, label="Nombre del Cliente")
  lastname = forms.CharField(max_length=100, required=False, label="Apellido del Cliente")
  email = forms.EmailField(required=False, label="Email del Cliente")
  phone = forms.CharField(max_length=15, required=False, label="Teléfono del Cliente")
  identity = forms.CharField(max_length=20, required=False, label="Identificación del Cliente")

  class Meta:
    model = Link
    fields = ['description', 'subtotal', 'include_igv', 'unique']
    widgets = {
      'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Venta de servicios...'}),
      'subtotal': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
      'include_igv': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
      'unique': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    }

  def clean_subtotal(self):
    subtotal = self.cleaned_data.get('subtotal')
    if subtotal and subtotal > Decimal('999.00'):
      raise forms.ValidationError("El monto máximo permitido por link es de $999.00.")
    if subtotal and subtotal <= 0:
      raise forms.ValidationError("El monto debe ser mayor a 0.")
    return subtotal
