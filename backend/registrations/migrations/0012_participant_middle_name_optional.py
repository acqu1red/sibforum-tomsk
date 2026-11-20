from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('registrations', '0011_payment_evidence_immutable')]

    operations = [
        migrations.AlterField(
            model_name='participant',
            name='middle_name',
            field=models.CharField(max_length=100, blank=True, verbose_name='Отчество'),
        ),
    ]
