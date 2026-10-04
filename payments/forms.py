from decimal import Decimal
from typing import ClassVar

from django import forms

from gateways.services import COUNTRY_CODES, PAYER_LIMITS, validate_payer_field
from payments.models import Link


class CheckoutForm(forms.Form):
  """Actual payer input only; invitation data is not proof of identity."""

  first_name = forms.CharField(label='Primer nombre (obligatorio)', min_length=3, max_length=48)
  buyer_middle_name = forms.CharField(label='Segundo nombre (obligatorio)', min_length=2, max_length=50)
  last_name = forms.CharField(label='Apellido (obligatorio)', min_length=3, max_length=48)
  email = forms.EmailField(label='Correo electrónico (obligatorio)', min_length=6, max_length=128)
  identify = forms.CharField(label='Cédula, RUC o documento (obligatorio)', max_length=13)
  phone = forms.CharField(label='Teléfono (obligatorio)', min_length=7, max_length=15)
  billing_street = forms.CharField(label='Dirección de facturación (obligatoria)', max_length=100)
  billing_country = forms.ChoiceField(
    label='País de facturación (obligatorio)',
    choices=[('', 'Seleccione un país')] + [(code, code) for code in sorted(COUNTRY_CODES)],
  )
  shipping_same_as_billing = forms.BooleanField(
    required=False, label='Confirmo que la dirección y el país de entrega son los mismos que los de facturación'
  )
  shipping_street = forms.CharField(
    label='Dirección de entrega (obligatoria si es diferente)', max_length=100, required=False
  )
  shipping_country = forms.ChoiceField(
    label='País de entrega (obligatorio si es diferente)',
    required=False,
    choices=[('', 'Seleccione un país')] + [(code, code) for code in sorted(COUNTRY_CODES)],
  )

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    for field in self.fields.values():
      field.widget.attrs['class'] = 'input-modern'
      field.error_messages.update(
        {
          'required': 'Este dato real del pagador es obligatorio.',
          'invalid': 'Ingrese un dato válido.',
          'min_length': 'Ingrese al menos %(limit_value)s caracteres.',
          'max_length': 'Ingrese como máximo %(limit_value)s caracteres.',
          'invalid_choice': 'Seleccione un país válido.',
        }
      )

  def clean(self):
    cleaned = super().clean() or {}
    if cleaned.get('shipping_same_as_billing'):
      for suffix in ('street', 'country'):
        cleaned[f'shipping_{suffix}'] = cleaned.get(f'billing_{suffix}', '')
    for key in PAYER_LIMITS:
      if key in self.errors:
        continue
      try:
        validate_payer_field(key, cleaned.get(key))
      except (TypeError, ValueError) as exc:
        self.add_error(key, str(exc))
    return cleaned


class LinkForm(forms.ModelForm):
  """Formulario para la creación y edición de links de pago."""

  # Campos adicionales para la invitación al cliente con widgets estilizados
  firstname = forms.CharField(
    max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre'})
  )
  lastname = forms.CharField(
    max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellido'})
  )
  email = forms.EmailField(
    required=False, widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'correo@ejemplo.com'})
  )
  phone = forms.CharField(
    max_length=15,
    required=False,
    widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. 0999999999'}),
  )
  identity = forms.CharField(
    max_length=20,
    required=False,
    widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cédula o RUC'}),
  )

  class Meta:
    model = Link
    fields: ClassVar[list[str]] = ['description', 'subtotal', 'tax_type', 'include_igv', 'unique']
    widgets: ClassVar[dict[str, forms.Widget]] = {
      'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Venta de servicios...'}),
      'subtotal': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_monto'}),
      'tax_type': forms.Select(attrs={'class': 'form-control', 'id': 'id_tax_type'}),
      'include_igv': forms.CheckboxInput(attrs={'class': 'custom-control-input', 'id': 'id_include_igv'}),
      'unique': forms.CheckboxInput(attrs={'class': 'custom-control-input', 'id': 'id_unique'}),
    }
    labels: ClassVar[dict[str, str]] = {
      'description': 'Descripción del producto/servicio',
      'subtotal': 'Monto a cobrar (USD)',
      'tax_type': 'Tipo de IVA',
      'include_igv': '¿El monto ya incluye IVA?',
      'unique': 'Link de un solo uso',
    }

  def clean_subtotal(self):
    subtotal = self.cleaned_data.get('subtotal')
    if subtotal and subtotal > Decimal('9999.00'):
      raise forms.ValidationError('El monto máximo permitido por link es de $9,999.00.')
    if subtotal and subtotal <= 0:
      raise forms.ValidationError('El monto debe ser mayor a 0.')
    return subtotal
