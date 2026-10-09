import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
  dependencies = (('accounts', '0004_contractacceptance'),)

  operations = (
    migrations.AddField(
      model_name='customuser',
      name='commerce_name',
      field=models.CharField(blank=True, default='', max_length=255, verbose_name='Nombre del comercio o razón social'),
    ),
    migrations.AddField(
      model_name='customuser',
      name='commerce_ruc',
      field=models.CharField(
        blank=True,
        default='',
        max_length=13,
        verbose_name='RUC del comercio',
        validators=[
          django.core.validators.RegexValidator(
            regex=r'\A[0-9]{13}\Z', message='Ingresá un RUC de 13 dígitos. No se verifica su validez oficial.'
          )
        ],
      ),
    ),
    migrations.AddField(
      model_name='customuser',
      name='commerce_address',
      field=models.CharField(
        blank=True, default='', max_length=500, verbose_name='Domicilio principal del comercio (incluí la ciudad)'
      ),
    ),
    migrations.AddField(
      model_name='customuser',
      name='legal_representative_name',
      field=models.CharField(
        blank=True, default='', max_length=300, verbose_name='Nombre completo del representante legal'
      ),
    ),
    migrations.AddField(
      model_name='customuser',
      name='commerce_identification',
      field=models.CharField(
        blank=True,
        default='',
        max_length=10,
        verbose_name='Cédula de identidad declarada para el contrato',
        validators=[
          django.core.validators.RegexValidator(
            regex=r'\A[0-9]{10}\Z', message='Ingresá una cédula de 10 dígitos. No se verifica su validez oficial.'
          )
        ],
      ),
    ),
  )
