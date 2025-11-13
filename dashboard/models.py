from django.contrib.auth.models import User
from django.db import models


class CustomUser(models.Model):
  user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
  phone = models.CharField(max_length=10)
  identification = models.BigIntegerField(unique=True)
  state = models.BooleanField(default=True)  # type: ignore
  email_active = models.BooleanField(default=False)  # type: ignore

  def __str__(self) -> str:
    return self.user.first_name  # type: ignore
