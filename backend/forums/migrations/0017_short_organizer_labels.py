import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('forums', '0016_event_organizer_role')]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='organizer',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='events', to='forums.organizationlogo', verbose_name='Организатор',
                help_text='Компания с логотипом внутри события. Она не добавляется в раздел «Люди форума».',
            ),
        ),
        migrations.AlterField(
            model_name='event',
            name='organizer_role',
            field=models.CharField(
                choices=[('organizer', 'Организатор'), ('co_organizer', 'Соорганизатор')],
                default='organizer', max_length=20, verbose_name='Роль организации',
            ),
        ),
    ]
