import base64
import secrets

from django.conf import settings
from django.core import signing
from django.db import models

from forums.models import TimeStampedModel


class Admin2FAProfile(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='admin_2fa', verbose_name='Сотрудник')
    secret_ciphertext = models.TextField(blank=True, verbose_name='Ключ двухфакторной защиты')
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name='Настройка подтверждена')
    last_counter = models.BigIntegerField(null=True, blank=True, verbose_name='Последний использованный код')

    class Meta:
        verbose_name = 'защита сотрудника'
        verbose_name_plural = 'Двухфакторная защита'

    def get_or_create_secret(self):
        if self.secret_ciphertext:
            return signing.loads(self.secret_ciphertext, salt='accounts.admin-2fa')
        secret = base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')
        self.secret_ciphertext = signing.dumps(secret, salt='accounts.admin-2fa')
        self.save(update_fields=('secret_ciphertext', 'updated_at'))
        return secret
