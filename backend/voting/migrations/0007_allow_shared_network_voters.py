from django.db import migrations, models
import django.core.validators

OLD_RULES = 'Можно голосовать только в знакомых номинациях. Допустимое количество участников указано в каждой номинации. Повторное голосование с одной сети и браузера ограничено.'
NEW_RULES = 'Можно голосовать только в знакомых номинациях. Допустимое количество участников указано в каждой номинации. С одного браузера можно отправить один бюллетень. Разные участники в одной сети могут голосовать.'


def allow_shared_networks(apps, schema_editor):
    Contest = apps.get_model('voting', 'Contest')
    # The owner reported that the existing one-IP policy blocks genuine voters.
    # Only adjust this contest's known old setting; never touch ballots.
    contest = Contest.objects.filter(forum__slug='promtour', voting_mode='simple', max_ballots_per_network=1).first()
    if contest:
        contest.max_ballots_per_network = 0
        fields = ['max_ballots_per_network', 'updated_at']
        if contest.rules_text == OLD_RULES:
            contest.rules_text = NEW_RULES
            fields.append('rules_text')
        contest.save(update_fields=fields)


class Migration(migrations.Migration):
    dependencies = [('voting', '0006_nominee_details_and_photo_descriptions')]
    operations = [
        migrations.AlterField(model_name='contest', name='voting_mode', field=models.CharField('Способ голосования', max_length=20, choices=[('simple', 'Без почты — один бюллетень с браузера'), ('email', 'С подтверждением почты')], default='email')),
        migrations.AlterField(model_name='contest', name='max_ballots_per_network', field=models.PositiveSmallIntegerField('Бюллетеней с одной сети', default=1, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)], help_text='0 — без общего лимита по IP: разные люди в офисе или Wi-Fi могут голосовать. Повтор с того же браузера всегда запрещён. Значение 1 блокирует всех в сети после первого голоса.')),
        migrations.RunPython(allow_shared_networks, migrations.RunPython.noop),
    ]
