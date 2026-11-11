import io
import json
from unittest.mock import patch
from urllib.error import URLError

from django.test import TestCase, override_settings
from django.utils import timezone

from forums.models import Forum
from .models import Ballot, Contest


@override_settings(
    DEBUG=False,
    SECURE_SSL_REDIRECT=False,
    YANDEX_SMARTCAPTCHA_SECRET='test-only-secret',
    YANDEX_SMARTCAPTCHA_CLIENT_ID='test-only-client',
)
class BallotCaptchaErrorsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        forum = Forum.objects.create(
            slug='captcha-check',
            title='Captcha regression check',
            starts_at=now,
            ends_at=now + timezone.timedelta(days=1),
            status=Forum.Status.PUBLISHED,
        )
        Contest.objects.create(forum=forum, title='Test contest', is_open=True)

    def submit(self, token=None):
        return self.client.post(
            '/api/v1/contests/captcha-check/ballots/',
            data=json.dumps({'email': 'test@example.com', 'selections': [], 'captcha_token': token}),
            content_type='application/json',
        )

    def assert_captcha_error(self, response, status, code):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.json()['error'], code)
        self.assertFalse(response.json()['ok'])
        self.assertTrue(response.json()['message'])
        self.assertFalse(Ballot.objects.exists())

    def test_missing_token_returns_json_instead_of_server_error(self):
        self.assert_captcha_error(self.submit(), 422, 'captcha_required')

    def test_rejected_token_returns_json_instead_of_server_error(self):
        with patch('forums.security.urllib.request.urlopen', return_value=io.BytesIO(b'{"status":"failed"}')):
            response = self.submit('rejected-token')
        self.assert_captcha_error(response, 422, 'captcha_invalid')

    def test_captcha_network_failure_returns_retryable_error(self):
        with patch('forums.security.urllib.request.urlopen', side_effect=URLError('offline test')):
            response = self.submit('test-token')
        self.assert_captcha_error(response, 503, 'captcha_unavailable')
