from django.db import models
from django.utils.translation import gettext_lazy as _


class Link(models.Model):
  class TaxType(models.TextChoices):
    VAT_15 = '15', _('IVA 15% (General)')
    VAT_0 = '0', _('IVA 0%')
    NO_VAT = 'NO', _('No objeto de IVA')

  seller = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, related_name='links')
  description = models.CharField(max_length=255)
  tax_type = models.CharField(max_length=2, choices=TaxType.choices, default=TaxType.VAT_15)
  vat_rate = models.DecimalField(max_digits=4, decimal_places=2, default=0.15)
  include_igv = models.BooleanField(default=True)  # Ahora por defecto True (ya incluye IVA)
  subtotal = models.DecimalField(max_digits=10, decimal_places=2)
  igv = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
  amount = models.DecimalField(max_digits=10, decimal_places=2)
  unique = models.BooleanField(default=False)  # type: ignore
  active = models.BooleanField(default=True)  # type: ignore
  is_payment = models.BooleanField(default=False)  # type: ignore
  created_at = models.DateTimeField(auto_now_add=True)

  def __str__(self) -> str:
    return self.description or f'Link #{self.pk}'  # type: ignore


class Payment(models.Model):
  class PaymentStatus(models.TextChoices):
    PENDING = 'PENDING', _('Pendiente')
    PAID = 'PAID', _('Pagado')
    FAILED = 'FAILED', _('Fallido')

  link = models.ForeignKey(Link, on_delete=models.SET_NULL, null=True, related_name='payments')
  seller = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='sales')

  # Datos del cliente
  first_name = models.CharField(max_length=100)
  last_name = models.CharField(max_length=100)
  email = models.EmailField()
  identify = models.CharField(max_length=20)
  phone = models.CharField(max_length=15)

  description = models.CharField(max_length=255)
  subtotal = models.DecimalField(max_digits=10, decimal_places=2)
  igv = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
  commission = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
  amount_client = models.DecimalField(max_digits=10, decimal_places=2)
  amount = models.DecimalField(max_digits=10, decimal_places=2)
  transaction_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
  status = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
  state = models.BooleanField(default=False)  # type: ignore

  def __str__(self):
    return f'{self.first_name}{self.last_name} - {self.amount}'


class Sale(models.Model):
  vendor = models.ForeignKey('accounts.CustomUser', on_delete=models.CASCADE, related_name='sales_records')
  payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='sale_record')
  amount = models.DecimalField(max_digits=10, decimal_places=2)
  commission = models.DecimalField(max_digits=10, decimal_places=2)
  net_amount = models.DecimalField(max_digits=10, decimal_places=2)
  created_at = models.DateTimeField(auto_now_add=True)

  def __str__(self):
    return f'Venta de {self.vendor.user.username} - {self.amount}'  # type: ignore


class Refund(models.Model):
  class RefundStatus(models.TextChoices):
    PENDING = 'PENDING', _('Pendiente')
    APPROVED = 'APPROVED', _('Aprobado')
    REJECTED = 'REJECTED', _('Rechazado')

  seller = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, related_name='refunds')
  payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='refund')
  description = models.TextField()
  amount = models.DecimalField(max_digits=10, decimal_places=2)
  status = models.CharField(max_length=10, choices=RefundStatus.choices, default=RefundStatus.PENDING)
  ticket = models.CharField(max_length=255, null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  
  # Campos de Auditoría Administrativa
  processed_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_refunds')
  processed_at = models.DateTimeField(null=True, blank=True)

  def __str__(self):
    return f'Resembolso #{self.pk} - {self.amount}'  # type: ignore

  @property
  def client_name(self):
    return f'{self.payment.first_name} {self.payment.last_name}'  # type: ignore

  @property
  def client_email(self):
    return self.payment.email  # type: ignore
