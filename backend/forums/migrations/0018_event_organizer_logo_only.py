from django.db import migrations, models


def show_sber_logo_only(apps, schema_editor):
    event = apps.get_model('forums', 'Event')
    event.objects.using(schema_editor.connection.alias).filter(
        day__forum__slug='promtour', slug='roundtable', organizer__name='СБЕРБАНК',
    ).update(organizer_logo_only=True)


class Migration(migrations.Migration):
    dependencies = [('forums', '0017_short_organizer_labels')]

    operations = [
        migrations.AddField(
            model_name='event',
            name='organizer_logo_only',
            field=models.BooleanField(
                default=False, verbose_name='Показывать только логотип',
                help_text='В карточке события скрывает подпись и ссылку организации. Подпись остаётся, если логотип не загружен.',
            ),
        ),
        migrations.RunPython(show_sber_logo_only, migrations.RunPython.noop),
    ]
