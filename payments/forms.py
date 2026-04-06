from django import forms
from decimal import Decimal
from payments.models import Link

class LinkForm(forms.ModelForm):
  """Formulario para la creación y edición de links de pago."""
  
  # Campos adicionales para la invitación al cliente con widgets estilizados
  firstname = forms.CharField(
    max_length=100, required=False, 
    widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre'})
  )
  lastname = forms.CharField(
    max_length=100, required=False, 
    widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellido'})
  )
  email = forms.EmailField(
    required=False, 
    widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'correo@ejemplo.com'})
  )
  phone = forms.CharField(
    max_length=15, required=False, 
    widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. 0999999999'})
  )
  identity = forms.CharField(
    max_length=20, required=False, 
    widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cédula o RUC'})
  )

  class Meta:
    model = Link
    fields = ['description', 'subtotal', 'tax_type', 'include_igv', 'unique']
    widgets = {
      'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Venta de servicios...'}),
      'subtotal': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_monto'}),
      'tax_type': forms.Select(attrs={'class': 'form-control', 'id': 'id_tax_type'}),
      'include_igv': forms.CheckboxInput(attrs={'class': 'custom-control-input', 'id': 'id_include_igv'}),
      'unique': forms.CheckboxInput(attrs={'class': 'custom-control-input', 'id': 'id_unique'}),
    }
    labels = {
      'description': 'Descripción del producto/servicio',
      'subtotal': 'Monto a cobrar (USD)',
      'tax_type': 'Tipo de IVA',
      'include_igv': '¿El monto ya incluye IVA?',
      'unique': 'Link de un solo uso',
    }

  def clean_subtotal(self):
    subtotal = self.cleaned_data.get('subtotal')
    if subtotal and subtotal > Decimal('9999.00'):
      raise forms.ValidationError("El monto máximo permitido por link es de $9,999.00.")
    if subtotal and subtotal <= 0:
      raise forms.ValidationError("El monto debe ser mayor a 0.")
    return subtotal
