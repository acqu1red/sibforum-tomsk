from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('voting', '0005_alter_contest_max_ballots_per_network')]
    operations = [
        migrations.AddField(model_name='nominee', name='detail_title', field=models.CharField(
            'Заголовок окна «Описание»', max_length=500, blank=True,
            help_text='Необязательно. Если пусто, используем название участника. Показывается отдельно от фотографий.')),
        migrations.AlterField(model_name='nomineephoto', name='caption', field=models.TextField(
            'Описание фотографии', max_length=3000, blank=True,
            help_text='Текст только для этого снимка. Общий текст проекта заполняется выше, в поле «Описание».')),
    ]
