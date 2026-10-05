from typing import ClassVar

from django.db import migrations, models


class Migration(migrations.Migration):
  # The repository already has refund/payer migrations numbered 0006/0007.
  dependencies: ClassVar = [('payments', '0007_checkout_payer_data')]

  operations: ClassVar = [
    migrations.AddField(
      model_name='paymentattempt',
      name='environment',
      field=models.CharField(
        blank=True,
        default='',
        max_length=10,
        choices=[('phase1', 'Phase 1'), ('phase2', 'Phase 2'), ('production', 'Production')],
      ),
    ),
  ]
