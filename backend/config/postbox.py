from email.utils import parseaddr

import boto3
from botocore.config import Config
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class EmailBackend(BaseEmailBackend):
    """Yandex Cloud Postbox over HTTPS, including Unicode MIME and ticket attachments."""
    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        client = boto3.client('sesv2', endpoint_url=settings.POSTBOX_ENDPOINT_URL,
            region_name='ru-central1', aws_access_key_id=settings.POSTBOX_ACCESS_KEY_ID,
            aws_secret_access_key=settings.POSTBOX_SECRET_ACCESS_KEY,
            config=Config(connect_timeout=5, read_timeout=settings.EMAIL_TIMEOUT,
                          retries={'max_attempts': 2, 'mode': 'standard'}))
        count = 0
        for message in email_messages:
            recipients = [parseaddr(value)[1] for value in message.recipients()]
            if not recipients:
                continue
            try:
                client.send_email(FromEmailAddress=parseaddr(message.from_email)[1],
                    Destination={'ToAddresses': recipients},
                    Content={'Raw': {'Data': message.message().as_bytes(linesep='\r\n')}})
                count += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return count
