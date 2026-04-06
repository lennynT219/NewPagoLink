from django.db import models
from django.utils.translation import gettext_lazy as _


class Bank(models.Model):
  title = models.CharField(max_length=100)

  def __str__(self):  # type: ignore
    return self.title


class PaymentMethod(models.Model):
  class AccountType(models.TextChoices):
    SAVINGS = 'AHO', _('Ahorros')
    CURRENT = 'CTE', _('Corriente')

  seller = models.ForeignKey('accounts.CustomUser', on_delete=models.CASCADE, related_name='payment_methods')
  bank = models.ForeignKey(Bank, on_delete=models.SET_NULL, null=True)
  fullname = models.CharField(max_length=50)
  account_type = models.CharField(max_length=3, choices=AccountType.choices, default=AccountType.SAVINGS)
  account_number = models.CharField(max_length=50)
  cci = models.CharField(max_length=50, null=True, blank=True)

  def __str__(self):
    return f'{self.bank.title} - {self.account_number}'  # type: ignore


class DisbursementRequest(models.Model):
  class Status(models.TextChoices):
    PENDING = 'PENDING', _('Pendiente')
    APPROVED = 'APPROVED', _('Aprobado')
    REJECTED = 'REJECTED', _('Rechazado')

  vendor = models.ForeignKey('accounts.CustomUser', on_delete=models.CASCADE, related_name='disbursements')
  method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name='disbursements')
  amount = models.DecimalField(max_digits=12, decimal_places=2)
  status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
  rejection_reason = models.TextField(null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  processed_at = models.DateTimeField(null=True, blank=True)

  def __str__(self):
    return f'Solicitud de {self.vendor.user.username} - {self.amount} ({self.status})'  # type: ignore
