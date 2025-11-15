from django.contrib.auth.models import User
from django.db import models


class CustomUser(models.Model):
  user = models.OneToOneField(User, on_delete=models.CASCADE)
  phone = models.CharField(max_length=10)
  identification = models.BigIntegerField(unique=True)
  state = models.BooleanField(default=True)  # type: ignore
  email_active = models.BooleanField(default=False)  # type: ignore

  def __str__(self) -> str:
    return self.user.get_full_name() or self.user.username  # type: ignore


class Contract(models.Model):
  seller = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
  ip = models.GenericIPAddressField()
  city = models.CharField(max_length=255)
  created_at = models.DateTimeField(auto_now_add=True)

  def __str__(self) -> str:
    return f'Contrato de {self.seller.user.username} aceptado el {self.created_at.strftime("%Y-%m-%d")}'
