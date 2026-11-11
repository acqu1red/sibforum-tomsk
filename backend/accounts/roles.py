from django.contrib.auth.models import Group, Permission


ROLE_CHOICES = (
    ('organizer', 'Организатор — программа, участники и конкурс'),
    ('registration', 'Регистрация — заявки, списки и отметки прибытия'),
    ('content', 'Редактор — программа, площадки и спикеры'),
    ('contest', 'Конкурс — номинации, кандидаты и голосование'),
    ('viewer', 'Наблюдатель — просмотр без изменения данных'),
)


def assign_role(user, role):
    role = role if role in dict(ROLE_CHOICES) else 'viewer'
    group, _ = Group.objects.get_or_create(name=dict(ROLE_CHOICES)[role])
    permissions = Permission.objects.filter(content_type__app_label__in=['forums', 'registrations', 'voting'])
    if role == 'content':
        permissions = permissions.filter(content_type__app_label='forums')
    elif role == 'contest':
        permissions = permissions.filter(content_type__app_label='voting')
    elif role == 'registration':
        permissions = permissions.filter(content_type__app_label='registrations')
    elif role == 'viewer':
        permissions = permissions.filter(codename__startswith='view_')
    if role not in ('organizer', 'viewer'):
        permissions = permissions.exclude(codename__startswith='delete_')
    group.permissions.set(permissions)
    user.groups.add(group)
