from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('forums', '0014_meeting_13_contacts_organizations')]
    operations = [migrations.AddField(
        model_name='contactcard', name='placement',
        field=models.CharField('Место на сайте', max_length=20, default='contacts',
            choices=[('contacts', 'Как найти форум'), ('organizers', 'Под организаторами форума')],
            help_text='Под организаторами можно добавить строку «По вопросам Форума обращаться» с ФИО и телефоном.'))]
