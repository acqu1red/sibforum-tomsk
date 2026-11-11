"""Small, deterministic derivatives; originals remain available to the editor."""
import hashlib
import io

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError


def validate_image_upload(file):
    if file.size > 10 * 1024 * 1024:
        raise ValidationError('Размер изображения не должен превышать 10 МБ.')
    try:
        file.seek(0)
        with Image.open(file) as image:
            if image.width * image.height > 40_000_000:
                raise ValidationError('Изображение слишком большое: максимум 40 миллионов пикселей.')
            if image.format not in {'JPEG', 'PNG', 'WEBP'}:
                raise ValidationError('Выберите JPEG, PNG или WebP.')
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValidationError('Не удалось прочитать изображение. Выберите JPEG, PNG или WebP.') from error
    finally:
        file.seek(0)


def image_variants(field, previous=None):
    if not field:
        return {}
    if previous and previous.get('_source') == field.name:
        return previous
    field.open('rb')
    try:
        raw = field.read()
        digest = hashlib.sha256(raw).hexdigest()[:24]
        with Image.open(io.BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert('RGBA' if 'A' in source.getbands() or source.mode == 'P' else 'RGB')
            result = {'_source': field.name}
            for size in (160, 400, 960):
                version = image.copy()
                version.thumbnail((size, size), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                version.save(output, 'WEBP', quality=85, method=4)
                name = f'optimized/{digest}-{size}.webp'
                if not field.storage.exists(name):
                    field.storage.save(name, ContentFile(output.getvalue()))
                result[str(size)] = field.storage.url(name)
            return result
    finally:
        field.close()


def safe_public_link(value):
    from urllib.parse import urlparse
    if not value:
        return
    parsed = urlparse(value)
    local = (value.startswith(('/', '#')) and not value.startswith('//') and '\\' not in value)
    if not local and not (parsed.scheme in {'https', 'mailto', 'tel'} and (parsed.netloc or parsed.path)):
        raise ValidationError('Укажите адрес на сайте, ссылку https, mailto: или tel:.')
    if any(ord(c) < 32 for c in value):
        raise ValidationError('Ссылка содержит недопустимые символы.')


def public_asset(value, absolute=False):
    """Resolve bundled images consistently on the public and admin subdomains."""
    from django.conf import settings
    if value and value.startswith('/img/'):
        return (settings.PUBLIC_ASSET_BASE_URL or (settings.PUBLIC_SITE_URL if absolute else '')).rstrip('/') + value
    return value
