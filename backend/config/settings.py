import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {'1', 'true', 'yes', 'on'}


DEBUG = env_bool('DEBUG')
SECRET_KEY = os.environ.get('SECRET_KEY', 'local-development-only-change-me')
if not DEBUG and SECRET_KEY == 'local-development-only-change-me':
    raise RuntimeError('SECRET_KEY must be set when DEBUG is disabled')

PUBLIC_DOMAIN = os.environ.get('DOMAIN', 'siberianforum.ru')
ADMIN_DOMAIN = os.environ.get('ADMIN_DOMAIN', 'admin.localhost' if DEBUG else f'admin.{PUBLIC_DOMAIN}')
if not ADMIN_DOMAIN or '://' in ADMIN_DOMAIN or '/' in ADMIN_DOMAIN:
    raise RuntimeError('ADMIN_DOMAIN must be a hostname without scheme or path')
ADMIN_HOSTS = [host.strip().lower().rstrip('.') for host in os.environ.get('ADMIN_HOSTS', ADMIN_DOMAIN).split(',') if host.strip()]
ADMIN_OWNER_USERNAME = os.environ.get('ADMIN_OWNER_USERNAME', 'director')
ADMIN_TOTP_REQUIRED = env_bool('ADMIN_TOTP_REQUIRED', True)
ADMIN_SITE_URL = os.environ.get('ADMIN_SITE_URL', ('http' if DEBUG else 'https') + '://' + ADMIN_DOMAIN + (':8100' if DEBUG else '')).rstrip('/')
ALLOWED_HOSTS = list(dict.fromkeys(
    [host.strip() for host in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if host.strip()] + ADMIN_HOSTS
))
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(
    [origin.strip() for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()] + [ADMIN_SITE_URL]
))
TRUST_PROXY_IP_HEADER = env_bool('TRUST_PROXY_IP_HEADER')

INSTALLED_APPS = [
    'config.admin_config.ForumAdminConfig',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts.apps.AccountsConfig',
    'forums.apps.ForumsConfig',
    'registrations.apps.RegistrationsConfig',
    'voting.apps.VotingConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'accounts.middleware.Admin2FAMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

if os.environ.get('POSTGRES_HOST'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('POSTGRES_DB', 'siberian_forum'),
            'USER': os.environ.get('POSTGRES_USER', 'forum'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
            'HOST': os.environ['POSTGRES_HOST'],
            'PORT': os.environ.get('POSTGRES_PORT', '5432'),
            'CONN_MAX_AGE': 60,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.environ.get('SQLITE_PATH', BASE_DIR / 'db.sqlite3'),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Asia/Tomsk'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = 'media/'
MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', BASE_DIR / 'media'))
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SESSION_COOKIE_AGE = int(os.environ.get('ADMIN_SESSION_COOKIE_AGE', '1800'))
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', not DEBUG)
SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', not DEBUG)
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '0' if DEBUG else '31536000'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', not DEBUG)
SECURE_HSTS_PRELOAD = env_bool('SECURE_HSTS_PRELOAD', not DEBUG)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': os.environ.get('LOG_LEVEL', 'INFO')},
}


EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '1026' if DEBUG else '25'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS')
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL')
EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT', '15'))
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'forum@localhost')
PUBLIC_SITE_URL = os.environ.get('PUBLIC_SITE_URL', 'http://localhost:8095').rstrip('/')
if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise RuntimeError('EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be enabled')

PUBLIC_BACKEND_URL = os.environ.get('PUBLIC_BACKEND_URL', 'http://localhost:8100').rstrip('/')
PDF_FONT_PATH = os.environ.get('PDF_FONT_PATH', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')

YANDEX_SMARTCAPTCHA_SECRET = os.environ.get('YANDEX_SMARTCAPTCHA_SECRET', '')
YANDEX_SMARTCAPTCHA_URL = os.environ.get('YANDEX_SMARTCAPTCHA_URL', 'https://smartcaptcha.yandexcloud.net/validate')

YANDEX_SMARTCAPTCHA_CLIENT_ID = os.environ.get('YANDEX_SMARTCAPTCHA_CLIENT_ID', '')
if not DEBUG and YANDEX_SMARTCAPTCHA_SECRET and not YANDEX_SMARTCAPTCHA_CLIENT_ID:
    raise RuntimeError('YANDEX_SMARTCAPTCHA_CLIENT_ID must be set when SmartCaptcha is enabled')

# Public source assets and uploaded media can live entirely in Object Storage.
PUBLIC_ASSET_BASE_URL = os.environ.get('PUBLIC_ASSET_BASE_URL', '').rstrip('/')
PUBLIC_SITE_ROOT = os.environ.get('PUBLIC_SITE_ROOT', str(BASE_DIR.parent / 'site'))
MEDIA_BUCKET_NAME = os.environ.get('MEDIA_BUCKET_NAME', '')
MEDIA_PUBLIC_BASE_URL = os.environ.get('MEDIA_PUBLIC_BASE_URL', '').rstrip('/')
if MEDIA_BUCKET_NAME:
    STORAGES = {
        'default': {
            'BACKEND': 'config.storage.ForumMediaStorage',
            'OPTIONS': {
                'bucket_name': MEDIA_BUCKET_NAME,
                'access_key': os.environ.get('MEDIA_ACCESS_KEY_ID', ''),
                'secret_key': os.environ.get('MEDIA_SECRET_ACCESS_KEY', ''),
                'endpoint_url': 'https://storage.yandexcloud.net',
                'region_name': 'ru-central1',
                'signature_version': 's3v4',
                'default_acl': None,
                'file_overwrite': False,
                'querystring_auth': True,
                'querystring_expire': 900,
            },
        },
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
POSTBOX_ENDPOINT_URL = os.environ.get('POSTBOX_ENDPOINT_URL', 'https://postbox.cloud.yandex.net')
POSTBOX_ACCESS_KEY_ID = os.environ.get('POSTBOX_ACCESS_KEY_ID', '')
POSTBOX_SECRET_ACCESS_KEY = os.environ.get('POSTBOX_SECRET_ACCESS_KEY', '')
