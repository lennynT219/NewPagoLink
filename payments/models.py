from django.db import models
from django.utils.translation import gettext_lazy as _


class Link(models.Model):
  seller = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, related_name='links')
  description = models.CharField(max_length=255)
  include_igv = models.BooleanField(default=False)  # type: ignore
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


class Refund(models.Model):
  seller = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, related_name='refunds')
  payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='refund')
  description = models.TextField()
  amount = models.DecimalField(max_digits=10, decimal_places=2)
  state = models.BooleanField(default=False)  # type: ignore
  ticket = models.CharField(max_length=255, null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)

  def __str__(self):
    return f'Resembolso #{self.pk} - {self.amount}'  # type: ignore

  @property
  def client_name(self):
    return f'{self.payment.first_name} {self.payment.last_name}'  # type: ignore

  @property
  def client_email(self):
    return self.payment.email  # type: ignore
