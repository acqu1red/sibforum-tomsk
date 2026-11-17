from django.db import migrations, models

OLD_RULES = 'Можно голосовать только в знакомых номинациях. Допустимое количество участников указано в каждой номинации. С одного браузера можно отправить один бюллетень. Разные участники в одной сети могут голосовать.'
NEW_RULES = 'Можно голосовать только в знакомых номинациях. Допустимое количество участников указано в каждой номинации. В текущем этапе с одного браузера можно отправить один бюллетень. Разные участники в одной сети могут голосовать. Результаты предыдущего этапа сохранены и учитываются в общем итоге.'


def start_second_round(apps, schema_editor):
    Contest = apps.get_model('voting', 'Contest')
    contest = Contest.objects.filter(forum__slug='promtour', voting_mode='simple', voting_round=1).first()
    if contest:
        contest.voting_round = 2
        fields = ['voting_round', 'updated_at']
        if contest.rules_text == OLD_RULES:
            contest.rules_text = NEW_RULES
            fields.append('rules_text')
        contest.save(update_fields=fields)


class Migration(migrations.Migration):
    dependencies = [('voting', '0007_allow_shared_network_voters')]
    operations = [
        migrations.AddField(model_name='contest', name='voting_round', field=models.PositiveIntegerField('Текущий раунд голосования', default=1, editable=False)),
        migrations.RunPython(start_second_round, migrations.RunPython.noop),
    ]
