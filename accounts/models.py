from django.contrib.auth.models import User
from django.db import models

from accounts.merchant_profile import CONTRACT_PROFILE_FIELDS, validate_commerce_identification, validate_commerce_ruc


class CustomUser(models.Model):
  user = models.OneToOneField(User, on_delete=models.CASCADE)
  phone = models.CharField(max_length=10)
  identification = models.BigIntegerField(unique=True)
  state = models.BooleanField(default=True)  # type: ignore
  email_active = models.BooleanField(default=False)  # type: ignore
  is_admin_role = models.BooleanField(default=False)  # Nuevo campo Admin App
  available_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
  commerce_name = models.CharField(CONTRACT_PROFILE_FIELDS['commerce_name'], max_length=255, blank=True, default='')
  commerce_ruc = models.CharField(
    CONTRACT_PROFILE_FIELDS['commerce_ruc'], max_length=13, blank=True, default='', validators=[validate_commerce_ruc]
  )
  commerce_address = models.CharField(
    CONTRACT_PROFILE_FIELDS['commerce_address'], max_length=500, blank=True, default=''
  )
  legal_representative_name = models.CharField(
    CONTRACT_PROFILE_FIELDS['legal_representative_name'], max_length=300, blank=True, default=''
  )
  commerce_identification = models.CharField(
    CONTRACT_PROFILE_FIELDS['commerce_identification'],
    max_length=10,
    blank=True,
    default='',
    validators=[validate_commerce_identification],
  )

  class Meta:
    db_table = 'dashboard_customuser'

  def __str__(self) -> str:
    return self.user.get_full_name() or self.user.username  # type: ignore


class ContractAcceptance(models.Model):
  """Version-bound evidence; legacy Contract rows remain independent."""

  seller = models.ForeignKey('accounts.CustomUser', on_delete=models.PROTECT, related_name='contract_acceptances')
  version = models.CharField(max_length=128)
  text_hash = models.CharField(max_length=64)
  text_snapshot = models.TextField()
  accepted_at = models.DateTimeField(auto_now_add=True)
  ip = models.GenericIPAddressField(null=True, blank=True)
  city = models.CharField(max_length=255, blank=True, default='')

  class Meta:
    constraints = (models.UniqueConstraint(fields=['seller', 'version'], name='unique_seller_contract_version'),)

  def __str__(self):
    return f'{self.seller} — {self.version}'


class Contract(models.Model):
  seller = models.OneToOneField('accounts.CustomUser', on_delete=models.CASCADE)
  ip = models.GenericIPAddressField()
  city = models.CharField(max_length=255)
  created_at = models.DateTimeField(auto_now_add=True)

  def __str__(self) -> str:
    return f'Contrato de {self.seller.user.username} aceptado el {self.created_at.strftime("%Y-%m-%d")}'  # type: ignore
