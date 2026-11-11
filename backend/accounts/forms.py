from django import forms
from django.contrib.auth.forms import AdminUserCreationForm

from .roles import ROLE_CHOICES


class StaffCreationForm(AdminUserCreationForm):
    role = forms.ChoiceField(label='Роль сотрудника', choices=ROLE_CHOICES, required=False,
                             initial='registration', help_text='Управление сотрудниками остаётся только у руководителя.')


class TwoFactorCodeForm(forms.Form):
    code = forms.CharField(
        label='Код из приложения',
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'one-time-code', 'autofocus': True, 'pattern': '[0-9]{6}'}),
    )
