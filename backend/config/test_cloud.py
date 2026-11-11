from email import policy
from email.parser import BytesParser
from unittest.mock import patch

from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from .postbox import EmailBackend
from .storage import ForumMediaStorage


@override_settings(POSTBOX_ACCESS_KEY_ID='test-id', POSTBOX_SECRET_ACCESS_KEY='test-secret',
                   DEFAULT_FROM_EMAIL='Сибирский форум <noreply@example.org>')
class PostboxTests(SimpleTestCase):
    @patch('config.postbox.boto3.client')
    def test_russian_message_and_pdf_attachment_survive_raw_api(self, factory):
        message = EmailMessage('Ваш билет', 'Код подтверждения: 123456',
                               'Сибирский форум <noreply@example.org>', ['Участник <person@example.org>'])
        message.attach('Билет.pdf', b'%PDF-test', 'application/pdf')
        self.assertEqual(EmailBackend().send_messages([message]), 1)
        sent = factory.return_value.send_email.call_args.kwargs
        self.assertEqual(sent['FromEmailAddress'], 'noreply@example.org')
        self.assertEqual(sent['Destination']['ToAddresses'], ['person@example.org'])
        parsed = BytesParser(policy=policy.default).parsebytes(sent['Content']['Raw']['Data'])
        self.assertEqual(str(parsed['Subject']), 'Ваш билет')
        self.assertIn('123456', parsed.get_body(preferencelist=('plain',)).get_content())
        self.assertEqual(next(parsed.iter_attachments()).get_payload(decode=True), b'%PDF-test')

    @patch('config.postbox.boto3.client')
    def test_provider_failure_is_not_reported_as_success(self, factory):
        factory.return_value.send_email.side_effect = RuntimeError('provider unavailable')
        message = EmailMessage('Тест', 'Текст', 'noreply@example.org', ['person@example.org'])
        with self.assertRaises(RuntimeError):
            EmailBackend().send_messages([message])
        self.assertEqual(EmailBackend(fail_silently=True).send_messages([message]), 0)


@override_settings(MEDIA_PUBLIC_BASE_URL='https://media.example.org')
class CloudMediaTests(SimpleTestCase):
    def test_only_derivatives_have_stable_public_urls(self):
        storage = ForumMediaStorage(access_key='test', secret_key='test', bucket_name='test',
                                   endpoint_url='https://storage.yandexcloud.net', region_name='ru-central1')
        self.assertEqual(storage.url('optimized/test-400.webp'), 'https://media.example.org/optimized/test-400.webp')
        private_url = storage.url('speakers/original.jpg')
        self.assertIn('Signature=', private_url)
        self.assertNotIn('media.example.org', private_url)
        self.assertEqual(storage.get_object_parameters('speakers/original.jpg')['CacheControl'], 'private, no-store')

    @override_settings(PUBLIC_ASSET_BASE_URL='https://media.example.org/site')
    def test_bundled_images_use_cloud_base(self):
        from forums.media import public_asset
        self.assertEqual(public_asset('/img/logo.svg'), 'https://media.example.org/site/img/logo.svg')
        self.assertEqual(public_asset('https://other.example.org/a.jpg'), 'https://other.example.org/a.jpg')
