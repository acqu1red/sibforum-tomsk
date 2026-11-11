from urllib.parse import quote
from django.conf import settings
from storages.backends.s3 import S3Storage


class ForumMediaStorage(S3Storage):
    """Private originals; stable public URLs only for generated display images."""
    def url(self, name, parameters=None, expire=None, http_method=None):
        if name.startswith('optimized/'):
            return settings.MEDIA_PUBLIC_BASE_URL.rstrip('/') + '/' + quote(name, safe='/')
        return super().url(name, parameters=parameters, expire=expire, http_method=http_method)

    def get_object_parameters(self, name):
        parameters = super().get_object_parameters(name)
        parameters['CacheControl'] = 'public, max-age=31536000, immutable' if name.startswith('optimized/') else 'private, no-store'
        return parameters
