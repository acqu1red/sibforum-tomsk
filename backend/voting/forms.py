from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet


class NomineePhotoFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        photos = [form for form in self.forms if form.cleaned_data
                  and not form.cleaned_data.get('DELETE') and form.cleaned_data.get('image')]
        if len(photos) > 10:
            raise ValidationError('Можно добавить не более 10 фотографий. Удалите лишние снимки перед сохранением.')
