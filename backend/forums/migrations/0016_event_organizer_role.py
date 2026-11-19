from django.db import migrations, models


def set_seminar_role(apps, schema_editor):
    event = apps.get_model('forums', 'Event')
    event.objects.using(schema_editor.connection.alias).filter(
        day__forum__slug='promtour',
        slug='roundtable',
        title='Семинар: «Сильный бренд. Сильный бизнес»',
        organizer__name='СБЕРБАНК',
    ).update(organizer_role='co_organizer')


class Migration(migrations.Migration):
    dependencies = [('forums', '0015_contactcard_placement')]

    operations = [
        migrations.AddField(
            model_name='event',
            name='organizer_role',
            field=models.CharField(
                choices=[('organizer', 'Организатор мероприятия'), ('co_organizer', 'Соорганизатор мероприятия')],
                default='organizer', max_length=20, verbose_name='Роль организации',
            ),
        ),
        migrations.RunPython(set_seminar_role, migrations.RunPython.noop),
    ]
