from django.contrib.auth.models import Group, Permission


ROLE_CHOICES = (
    ('checkin', 'Администратор на входе — QR и посещаемость'),
    ('moderator', 'Модератор — заявки и проверка оплаты'),
    ('organizer', 'Организатор — программа, участники и конкурс'),
    ('registration', 'Регистрация — заявки, списки и отметки прибытия'),
    ('content', 'Редактор — программа, площадки и спикеры'),
    ('contest', 'Конкурс — номинации, кандидаты и голосование'),
    ('viewer', 'Наблюдатель — просмотр без изменения данных'),
)

LIMITED_PERMISSIONS = {
    'checkin': ('add_checkin', 'export_checkin'),
    'moderator': ('view_participant', 'view_registration', 'view_registrationitem',
                  'change_registrationitem', 'view_registrationitemhistory', 'confirm_payment'),
}


def role_permissions(role):
    permissions = Permission.objects.filter(content_type__app_label__in=['forums', 'registrations', 'voting'])
    if role in LIMITED_PERMISSIONS:
        return permissions.filter(content_type__app_label='registrations', codename__in=LIMITED_PERMISSIONS[role])
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
    return permissions


def assign_role(user, role):
    role = role if role in dict(ROLE_CHOICES) else 'viewer'
    group, _ = Group.objects.get_or_create(name=dict(ROLE_CHOICES)[role])
    group.permissions.set(role_permissions(role))
    user.groups.add(group)
