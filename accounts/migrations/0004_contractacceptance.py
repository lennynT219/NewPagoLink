import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
  dependencies = (('accounts', '0003_customuser_is_admin_role'),)

  operations = (
    migrations.CreateModel(
      name='ContractAcceptance',
      fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('version', models.CharField(max_length=128)),
        ('text_hash', models.CharField(max_length=64)),
        ('text_snapshot', models.TextField()),
        ('accepted_at', models.DateTimeField(auto_now_add=True)),
        ('ip', models.GenericIPAddressField(blank=True, null=True)),
        ('city', models.CharField(blank=True, default='', max_length=255)),
        (
          'seller',
          models.ForeignKey(
            on_delete=django.db.models.deletion.PROTECT, related_name='contract_acceptances', to='accounts.customuser'
          ),
        ),
      ],
      options={
        'constraints': [models.UniqueConstraint(fields=('seller', 'version'), name='unique_seller_contract_version')],
      },
    ),
  )
